#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
SYNC_SCRIPT="$ROOT_DIR/scripts/sync_credentials.py"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

REQUESTED_PYTHON=${PYTHON:-${PYTHON_BIN:-python3}}

resolve_python_bin() {
  local candidate
  for candidate in "$@"; do
    if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON_BIN=$(resolve_python_bin "$REQUESTED_PYTHON" python3 python); then
  echo "error: unable to find a Python interpreter (tried: $REQUESTED_PYTHON, python3, python)" >&2
  exit 1
fi

cleanup() {
  trap - INT TERM EXIT
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${UI_PID:-}" ]]; then
    kill "$UI_PID" >/dev/null 2>&1 || true
  fi
}

wait_for_any() {
  while true; do
    for pid in "$@"; do
      if [[ -z "$pid" ]]; then
        continue
      fi
      if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" 2>/dev/null || true
        return 0
      fi
    done
    sleep 1
  done
}

trap cleanup INT TERM EXIT

if [[ -f "$ENV_FILE" && -f "$SYNC_SCRIPT" ]]; then
  if ! "$PYTHON_BIN" "$SYNC_SCRIPT" --env-file "$ENV_FILE" --actor dev-sync >/dev/null; then
    echo "warning: failed to sync credentials from $ENV_FILE" >&2
  fi
fi

cd "$ROOT_DIR/app"
"$PYTHON_BIN" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

cd "$ROOT_DIR/ui"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run dev -- --host 127.0.0.1 &
UI_PID=$!

wait_for_any "$API_PID" "$UI_PID"

cleanup
