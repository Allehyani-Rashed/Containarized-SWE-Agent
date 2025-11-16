#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${CLAUDE_WORKDIR:-/work}"
INVOCATION_FLAGS_RAW="${CLAUDE_INVOCATION_FLAGS:---dangerously-skip-permissions}"
METADATA_FILE="${CLAUDE_METADATA_FILE:-CLAUDE_METADATA.json}"
MODEL="${CLAUDE_MODEL:-sonnet}"

if [[ -z "${CLAUDE_BIN_PATH:-}" && -x "/opt/claude-code/bin/claude" ]]; then
  CLAUDE_BIN="/opt/claude-code/bin/claude"
else
  CLAUDE_BIN="${CLAUDE_BIN_PATH:-claude}"
fi

# Check if binary exists
if [[ ! -x "${CLAUDE_BIN}" ]]; then
  echo "[claude-launch][error] Claude Code binary not found at ${CLAUDE_BIN}" >&2
  exit 96
fi

cd "${WORKDIR}"

echo "[claude-launch] Using workspace ${WORKDIR}" >&2
set +e
VERSION_OUTPUT="$(${CLAUDE_BIN} --version 2>&1 | head -n 1)"
VERSION_STATUS=$?
set -e
VERSION_FILE=${CLAUDE_VERSION_FILE:-/opt/claude-code/VERSION}
if [[ ${VERSION_STATUS} -ne 0 || -z "${VERSION_OUTPUT}" ]]; then
  if [[ -f "${VERSION_FILE}" ]]; then
    VERSION_OUTPUT=$(head -n 1 "${VERSION_FILE}" | tr -d '\r')
  else
    VERSION_OUTPUT="unknown"
  fi
fi
echo "[claude-launch] claude --version -> ${VERSION_OUTPUT}" >&2

export CLAUDE_METADATA_FILE="${METADATA_FILE}"
export CLAUDE_VERSION_OUTPUT="${VERSION_OUTPUT}"
export WORKDIR="${WORKDIR}"

FLAG_ARRAY=()
if [[ -n "${INVOCATION_FLAGS_RAW}" ]]; then
  # shellcheck disable=SC2206
  FLAG_ARRAY=(${INVOCATION_FLAGS_RAW})
fi

append_flag_if_missing() {
  local flag="$1"
  for existing in "${FLAG_ARRAY[@]}"; do
    if [[ "${existing}" == "${flag}" ]]; then
      return
    fi
  done
  FLAG_ARRAY+=("${flag}")
}

# Ensure critical flags are present
append_flag_if_missing "--dangerously-skip-permissions"

# Add model flag if specified
if [[ -n "${MODEL}" ]]; then
  # Check if --model flag already exists
  has_model_flag=0
  for flag in "${FLAG_ARRAY[@]}"; do
    if [[ "${flag}" == "--model" ]]; then
      has_model_flag=1
      break
    fi
  done

  if [[ ${has_model_flag} -eq 0 ]]; then
    FLAG_ARRAY+=("--model" "${MODEL}")
  fi
fi

export CLAUDE_INVOCATION_FLAGS="${FLAG_ARRAY[*]}"

python3 - <<'PY'
import json
import os
from pathlib import Path

workdir = Path(os.environ.get("WORKDIR", "/work"))
metadata_name = os.environ.get("CLAUDE_METADATA_FILE", "CLAUDE_METADATA.json")
if metadata_name:
    metadata_path = Path(metadata_name)
    if not metadata_path.is_absolute():
        metadata_path = workdir / metadata_path
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
else:
    metadata_path = workdir / "CLAUDE_METADATA.json"
flags = [flag for flag in os.environ.get("CLAUDE_INVOCATION_FLAGS", "").split() if flag]
version = os.environ.get("CLAUDE_VERSION_OUTPUT", "unknown")
model = os.environ.get("CLAUDE_MODEL", "sonnet")
payload = {"agent_version": version, "mode": "docker", "flags": flags, "model": model}
metadata_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
PY

# Claude Code uses ANTHROPIC_API_KEY environment variable for authentication
# If CLAUDE_API_KEY is provided, set it as ANTHROPIC_API_KEY
if [[ -n "${CLAUDE_API_KEY:-}" ]]; then
  export ANTHROPIC_API_KEY="${CLAUDE_API_KEY}"
  unset CLAUDE_API_KEY
fi

PROMPT_CONTENT="${CLAUDE_PROMPT:-}"

# Build the command
# Claude Code uses -p flag for non-interactive/headless mode
CLAUDE_CMD=("${CLAUDE_BIN}" "-p")

# Add flags
for flag in "${FLAG_ARRAY[@]}"; do
  CLAUDE_CMD+=("${flag}")
done

# Add the prompt as the last argument
if [[ -n "${PROMPT_CONTENT}" ]]; then
  CLAUDE_CMD+=("${PROMPT_CONTENT}")
  echo "[claude-launch] Executing Claude Code with prompt..." >&2
  "${CLAUDE_CMD[@]}"
else
  echo "[claude-launch][error] No prompt provided (CLAUDE_PROMPT is empty)" >&2
  exit 1
fi

/usr/local/bin/finish_task.sh
