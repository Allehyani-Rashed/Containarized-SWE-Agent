#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
DEFAULT_PY_BIN="python3.11"
SYNC_SCRIPT="$ROOT_DIR/scripts/sync_credentials.py"

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

  local venv_python="$venv_dir/bin/python"
  if [[ -d "$venv_dir" ]]; then
    local pip_shebang=""
    if [[ -f "$venv_dir/bin/pip" ]]; then
      pip_shebang=$(head -n 1 "$venv_dir/bin/pip" 2>/dev/null || true)
    fi
    if [[ ! -x "$venv_python" ]] || [[ -n "$pip_shebang" && "$pip_shebang" != "#!$venv_python" ]]; then
      echo "removing stale virtualenv at $venv_dir"
      rm -rf "$venv_dir"
    fi
  fi

  if [[ ! -d "$venv_dir" ]]; then
    echo "creating virtualenv at $venv_dir"
    "$PYTHON_BIN" -m venv "$venv_dir"
  fi

  "$venv_python" -m pip install --upgrade pip >/dev/null
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

  if docker image inspect local-codex-runner:latest >/dev/null 2>&1; then
    echo "removing cached runner image"
    docker image rm -f local-codex-runner:latest >/dev/null 2>&1 || true
  fi

  echo "building runner image (local-codex-runner:latest)"
  local -a build_args=()
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
  docker build ${build_args[@]+"${build_args[@]}"} -f "$ROOT_DIR/runner/Dockerfile" -t local-codex-runner:latest "$ROOT_DIR"

  echo "starting Tinyproxy sidecar"
  (cd "$ROOT_DIR" && docker compose up -d codex-egress-proxy)
}

run_setup() {
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

  cat <<'SUMMARY'

Bootstrap complete ✅
Next steps:
  1. source .venv/bin/activate
  2. run 'make dev' to launch the API (port 8000) and UI (port 5173)
  3. in another terminal, follow the Quickstart section in README.md to register a project and submit a task

SUMMARY
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
