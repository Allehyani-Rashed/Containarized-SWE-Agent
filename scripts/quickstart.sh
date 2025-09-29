#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
DEFAULT_PY_BIN="python3.11"
SYNC_SCRIPT="$ROOT_DIR/scripts/sync_credentials.py"
PROJECT_CACHE_LAST_PATH=""

usage() {
  cat <<'USAGE'
Usage: ./scripts/quickstart.sh [command]

Commands:
  setup   (default) build images, install dependencies, and start the proxy sidecar
  help    show this message
USAGE
}

if [[ ${1:-setup} == "help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: .env file not found. Copy .env.example and populate it before running this script." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a

PYTHON_BIN=${PYTHON_BIN:-$DEFAULT_PY_BIN}
PYTHON_VERSION_EXPECTED=${PYTHON_VERSION:-}
NODE_VERSION_EXPECTED=${NODE_VERSION:-}
DOCKER_VERSION_EXPECTED=${DOCKER_VERSION:-}

require_cmd() {
  local cmd=$1
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: required command '$cmd' not found in PATH" >&2
    exit 1
  fi
}

warn_if_version_differs() {
  local name=$1
  local expected=$2
  local actual=$3
  if [[ -n "$expected" && -n "$actual" && "$expected" != "$actual" ]]; then
    echo "warning: $name version $actual detected (expected $expected)." >&2
  fi
}

version_python() {
  "$1" --version 2>&1 | awk '{print $2}'
}

version_node() {
  node --version 2>/dev/null | sed 's/^v//'
}

version_docker() {
  docker --version 2>/dev/null | awk '{print $3}' | sed 's/,//'
}

ensure_projectsanitize() {
  local sanitizer="$ROOT_DIR/.projectsanitize"
  if [[ -f "$sanitizer" ]]; then
    return
  fi

  cat <<'EOF' >"$sanitizer"
# Files and directories to exclude from sanitized task workspaces
# Secrets
.env
.env.*
*.env
*.env.*

# Cloud credentials and configs
.aws/
.kube/

# Build artifacts and dependencies
node_modules/
dist/
build/
target/
out/
coverage/
__pycache__/
*.pyc
*.pyo

# Logs and caches
logs/
*.log
*.cache
.cache/
.tmp/
*.tmp

# Tooling metadata
.vscode/
.idea/
.DS_Store

# Internal workspaces
workspaces/
venv/
.venv/
EOF
  echo "seeded default .projectsanitize denylist at $sanitizer"
}

ensure_python_bin() {
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "warning: '$PYTHON_BIN' not found, falling back to python3" >&2
    PYTHON_BIN=python3
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      echo "error: python3 not found in PATH" >&2
      exit 1
    fi
  fi
}

ensure_python_env() {
  local venv_dir="$ROOT_DIR/.venv"
  ensure_python_bin
  local py_version
  py_version=$(version_python "$PYTHON_BIN")
  warn_if_version_differs "Python" "$PYTHON_VERSION_EXPECTED" "$py_version"

  if [[ ! -d "$venv_dir" ]]; then
    echo "creating virtualenv at $venv_dir"
    "$PYTHON_BIN" -m venv "$venv_dir"
  fi

  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
  "$venv_dir/bin/pip" install --upgrade -r "$ROOT_DIR/app/requirements.txt"
}

ensure_node_env() {
  require_cmd node
  require_cmd npm
  local node_version
  node_version=$(version_node)
  warn_if_version_differs "Node.js" "$NODE_VERSION_EXPECTED" "$node_version"

  echo "installing UI dependencies"
  (cd "$ROOT_DIR/ui" && npm install --loglevel error)
}

ensure_docker_setup() {
  require_cmd docker
  require_cmd git
  local docker_version
  docker_version=$(version_docker)
  warn_if_version_differs "Docker" "$DOCKER_VERSION_EXPECTED" "$docker_version"

  echo "building runner image (local-codex-runner:latest)"
  local build_args=()
  if [[ -n "${CODEX_AGENT_TARBALL:-}" && -n "${CODEX_AGENT_URL:-}" ]]; then
    echo "error: set either CODEX_AGENT_TARBALL or CODEX_AGENT_URL (not both)" >&2
    exit 1
  fi
  if [[ -n "${CODEX_AGENT_TARBALL:-}" ]]; then
    echo "  • staging Codex agent tarball: ${CODEX_AGENT_TARBALL}"
    build_args+=(--build-arg "CODEX_AGENT_TARBALL=${CODEX_AGENT_TARBALL}")
  fi
  if [[ -n "${CODEX_AGENT_URL:-}" ]]; then
    echo "  • downloading Codex agent from: ${CODEX_AGENT_URL}"
    build_args+=(--build-arg "CODEX_AGENT_URL=${CODEX_AGENT_URL}")
  fi
  docker build "${build_args[@]}" -f "$ROOT_DIR/runner/Dockerfile" -t local-codex-runner:latest "$ROOT_DIR"

  echo "starting Tinyproxy sidecar"
  (cd "$ROOT_DIR" && docker compose up -d codex-egress-proxy)
}

resolve_python() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "$ROOT_DIR/.venv/bin/python"
  else
    echo "$PYTHON_BIN"
  fi
}

resolve_project_cache_repo_path() {
  local python_exec
  python_exec=$(resolve_python)
  "$python_exec" - <<'PY'
import os
from app.app.project_cache import project_cache_repo_path

host = os.environ.get("GITLAB_HOST")
path = os.environ.get("GITLAB_PROJECT_PATH")
if not host or not path:
    raise SystemExit(1)
print(project_cache_repo_path(host, path), end="")
PY
}

build_git_remote_url() {
  local python_exec
  python_exec=$(resolve_python)
  "$python_exec" - <<'PY'
import os
from urllib.parse import quote, urlparse, urlunparse

host = os.environ.get("GITLAB_HOST")
path = os.environ.get("GITLAB_PROJECT_PATH")
if not host or not path:
    raise SystemExit(1)
base = host.rstrip("/") + "/" + path.strip("/") + ".git"
pat = os.environ.get("GITLAB_PAT")
if pat:
    parsed = urlparse(base)
    token = quote(pat, safe="")
    netloc = f"oauth2:{token}@{parsed.netloc}"
    url = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
else:
    url = base
print(url, end="")
PY
}

ensure_project_cache_clone() {
  local host="${GITLAB_HOST:-}"
  local project_path="${GITLAB_PROJECT_PATH:-}"
  local branch="${PROJECT_DEFAULT_BRANCH:-}"
  if [[ -z "$host" || -z "$project_path" ]]; then
    echo "warning: skipping project cache bootstrap (set GITLAB_HOST and GITLAB_PROJECT_PATH)" >&2
    return
  fi
  if [[ -z "$branch" ]]; then
    echo "warning: PROJECT_DEFAULT_BRANCH not set; defaulting to 'main'" >&2
    branch="main"
  fi

  local repo_dir
  if ! repo_dir=$(resolve_project_cache_repo_path); then
    echo "warning: unable to resolve project cache path; skipping clone" >&2
    return
  fi

  PROJECT_CACHE_LAST_PATH="$repo_dir"

  if [[ -d "$repo_dir/.git" ]]; then
    echo "project cache already present at $repo_dir"
    echo "  • refresh with 'python3 scripts/project_cache.py --refresh' if it looks stale"
    return
  fi

  if [[ -z "${GITLAB_PAT:-}" ]]; then
    echo "warning: GITLAB_PAT is empty; skipping cache bootstrap" >&2
    return
  fi

  local remote_url
  if ! remote_url=$(build_git_remote_url); then
    echo "warning: failed to construct Git remote URL; skipping cache bootstrap" >&2
    return
  fi

  mkdir -p "$(dirname "$repo_dir")"
  echo "Bootstrapping project cache at $repo_dir"
  GIT_TERMINAL_PROMPT=0 git clone --branch "$branch" --single-branch "$remote_url" "$repo_dir"
  echo "  • rerun 'python3 scripts/project_cache.py --refresh' to repair this cache later"
}

run_setup() {
  ensure_projectsanitize
  ensure_python_env
  ensure_node_env
  ensure_docker_setup

  if [[ -f "$ENV_FILE" && -f "$SYNC_SCRIPT" ]]; then
    local python_exec="$ROOT_DIR/.venv/bin/python"
    if [[ ! -x "$python_exec" ]]; then
      python_exec="$PYTHON_BIN"
    fi
    echo "syncing credentials from $ENV_FILE"
    if ! "$python_exec" "$SYNC_SCRIPT" --env-file "$ENV_FILE" --actor quickstart; then
      echo "warning: credential sync failed; run $SYNC_SCRIPT manually after updating .env" >&2
    fi
  fi

  ensure_project_cache_clone

  cat <<'SUMMARY'

Bootstrap complete ✅
Next steps:
  1. source .venv/bin/activate
  2. run 'make dev' to launch the API (port 8000) and UI (port 5173)
  3. in another terminal, follow the Quickstart section in README.md to register a project and submit a task

SUMMARY

  if [[ -n "$PROJECT_CACHE_LAST_PATH" ]]; then
    cat <<SUMMARY_EXTRA

Cache tips:
  • Clones live at $PROJECT_CACHE_LAST_PATH (under PROJECT_CACHE_ROOT)
  • Use 'python3 scripts/project_cache.py --refresh' to rebuild the cache if it drifts

SUMMARY_EXTRA
  fi
}

case ${1:-setup} in
  setup)
    run_setup
    ;;
  *)
    echo "error: unknown command '${1}'" >&2
    usage
    exit 1
    ;;
 esac
