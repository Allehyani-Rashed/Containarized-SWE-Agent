#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${E2E_ENV_FILE:-$ROOT_DIR/.env.e2e.local}"

if [[ -f "$ENV_FILE" ]]; then
  echo "info: loading E2E overrides from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

mask_token() {
  local value="$1"
  local length=${#value}
  if [[ $length -le 8 ]]; then
    printf '***'
    return
  fi
  local prefix=${value:0:4}
  local suffix=${value: -4}
  printf '%s…%s (len=%d)' "$prefix" "$suffix" "$length"
}

ensure_var() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    echo "error: required environment variable $name is not set" >&2
    return 1
  fi
  return 0
}

resolve_and_export() {
  local target="$1"
  local fallback="$2"
  local current="${!target:-}"
  if [[ -n "$current" ]]; then
    export "$target"="$current"
    return
  fi
  local fallback_value="${!fallback:-}"
  if [[ -n "$fallback_value" ]]; then
    export "$target"="$fallback_value"
  fi
}

resolve_and_export GITLAB_PAT E2E_GITLAB_PAT
resolve_and_export CHATGPT_SESSION_BUNDLE_PATH E2E_CHATGPT_SESSION_BUNDLE_PATH
resolve_and_export CHATGPT_SESSION_JSON E2E_CHATGPT_SESSION_JSON

if [[ -n "${CHATGPT_SESSION_BUNDLE:-}" ]]; then
  echo "warning: CHATGPT_SESSION_BUNDLE is deprecated; set CHATGPT_SESSION_JSON instead" >&2
fi
if [[ -n "${E2E_CHATGPT_SESSION_BUNDLE:-}" ]]; then
  echo "warning: E2E_CHATGPT_SESSION_BUNDLE is deprecated; set E2E_CHATGPT_SESSION_JSON instead" >&2
fi

missing=()
for var in GITLAB_PAT E2E_GITLAB_HOST E2E_GITLAB_PROJECT_PATH E2E_DEFAULT_TARGET_BRANCH; do
  if ! ensure_var "$var"; then
    missing+=("$var")
  fi
done

if [[ -z "${CHATGPT_SESSION_BUNDLE_PATH:-}" && -z "${CHATGPT_SESSION_JSON:-}" ]]; then
  missing+=("CHATGPT_SESSION_BUNDLE_PATH or CHATGPT_SESSION_JSON")
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "" >&2
  echo "Populate the missing variables in $ENV_FILE (or export them) before running the UI E2E suite." >&2
  exit 1
fi

API_BASE="${E2E_API_BASE_URL:-http://127.0.0.1:8000}"
UI_BASE="${E2E_UI_BASE_URL:-http://127.0.0.1:5173}"
export E2E_API_BASE_URL="$API_BASE"
export E2E_UI_BASE_URL="$UI_BASE"

require_real_stack="${E2E_REQUIRE_REAL_STACK:-0}"
if [[ "$require_real_stack" =~ ^(1|true|yes|on)$ ]]; then
  export RUNNER_DISABLE_DOCKER=0
  export RUNNER_ALLOW_STUB_FALLBACK=0
  export CODEX_ALLOW_STUB=0
  export RUNNER_GIT_DRY_RUN=0
  export E2E_BOOTSTRAP_DRY_RUN=0
  mode_display="real Codex stack (Docker)"
else
  export RUNNER_DISABLE_DOCKER=1
  export RUNNER_ALLOW_STUB_FALLBACK=1
  export CODEX_ALLOW_STUB=1
  export RUNNER_GIT_DRY_RUN=1
  export E2E_BOOTSTRAP_DRY_RUN=0
  mode_display="local stub (Docker disabled)"
fi

if [[ -n "${E2E_DOCKER_HOST:-}" ]]; then
  export DOCKER_HOST="$E2E_DOCKER_HOST"
fi

if [[ -n "${CHATGPT_SESSION_BUNDLE_PATH:-}" ]]; then
  session_display="path: ${CHATGPT_SESSION_BUNDLE_PATH}"
elif [[ -n "${CHATGPT_SESSION_JSON:-}" ]]; then
  session_display="inline json: $(mask_token "${CHATGPT_SESSION_JSON}")"
else
  session_display='--'
fi

cat <<SUMMARY
UI E2E environment ready:
  GitLab PAT: $(mask_token "$GITLAB_PAT")
  Session bundle: $session_display
  GitLab host: $E2E_GITLAB_HOST
  Project path: $E2E_GITLAB_PROJECT_PATH
  Target branch: $E2E_DEFAULT_TARGET_BRANCH
  API base URL: $E2E_API_BASE_URL
  UI base URL: $E2E_UI_BASE_URL
  Runner mode: $mode_display
SUMMARY

echo "info: After the suite finishes, open the report with 'npx playwright show-report ui/playwright-report'"
