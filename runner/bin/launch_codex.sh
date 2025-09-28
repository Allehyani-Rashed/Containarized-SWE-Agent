#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${CODEX_WORKDIR:-/work}"
INVOCATION_FLAGS_RAW="${CODEX_INVOCATION_FLAGS:---yolo}"
METADATA_FILE="${CODEX_METADATA_FILE:-CODEX_METADATA.json}"
if [[ -z "${CODEX_BIN_PATH:-}" && -x "/opt/codex/bin/codex" ]]; then
  CODEX_BIN="/opt/codex/bin/codex"
else
  CODEX_BIN="${CODEX_BIN_PATH:-codex}"
fi

BIN_SIGNATURE=$(head -c 4 "${CODEX_BIN}" 2>/dev/null | od -An -tx1 | tr -d ' \n' || true)

cd "${WORKDIR}"

echo "[codex-launch] Using workspace ${WORKDIR}" >&2
set +e
VERSION_OUTPUT="$(${CODEX_BIN} --version 2>&1 | head -n 1)"
VERSION_STATUS=$?
set -e
VERSION_FILE=${CODEX_VERSION_FILE:-/opt/codex/VERSION}
if [[ ${VERSION_STATUS} -ne 0 || -z "${VERSION_OUTPUT}" ]]; then
  if [[ -f "${VERSION_FILE}" ]]; then
    VERSION_OUTPUT=$(head -n 1 "${VERSION_FILE}" | tr -d '\r')
  else
    VERSION_OUTPUT="unknown"
  fi
fi
echo "[codex-launch] codex --version -> ${VERSION_OUTPUT}" >&2

if [[ -n "${CODEX_MODEL_ID:-}" ]]; then
  echo "[codex-launch] Selected Codex model: ${CODEX_MODEL_ID}" >&2
fi

ALLOW_STUB=${CODEX_ALLOW_STUB:-0}
if [[ "${BIN_SIGNATURE}" != "7f454c46" ]]; then
  if [[ "${ALLOW_STUB}" != "1" ]]; then
    echo "[codex-launch][error] real Codex agent not installed (detected non-ELF codex binary)" >&2
    echo "[codex-launch][error] ensure install_codex_agent.sh succeeded or set CODEX_ALLOW_STUB=1 to proceed" >&2
    exit 96
  fi
  echo "[codex-launch] stub Codex agent in use" >&2
fi

export CODEX_METADATA_FILE="${METADATA_FILE}"
export CODEX_VERSION_OUTPUT="${VERSION_OUTPUT}"
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

append_flag_if_missing "--skip-git-repo-check"

export CODEX_INVOCATION_FLAGS="${FLAG_ARRAY[*]}"

python3 - <<'PY'
import json
import os
from pathlib import Path

workdir = Path(os.environ.get("WORKDIR", "/work"))
metadata_name = os.environ.get("CODEX_METADATA_FILE", "CODEX_METADATA.json")
if metadata_name:
    metadata_path = Path(metadata_name)
    if not metadata_path.is_absolute():
        metadata_path = workdir / metadata_path
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
else:
    metadata_path = workdir / "CODEX_METADATA.json"
flags = [flag for flag in os.environ.get("CODEX_INVOCATION_FLAGS", "").split() if flag]
version = os.environ.get("CODEX_VERSION_OUTPUT", "unknown")
payload = {"agent_version": version, "mode": "docker", "flags": flags}
model = os.environ.get("CODEX_MODEL_ID")
if model:
    payload["model"] = model
metadata_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
PY

if [[ -n "${CODEX_SESSION_BUNDLE_B64:-}" ]]; then
  export CODEX_SESSION_BUNDLE_PATH="${HOME}/.codex/auth.json"
  python3 - <<'PY'
import base64
import os
import sys
from pathlib import Path

bundle_b64 = os.environ.get("CODEX_SESSION_BUNDLE_B64", "")
target_path = Path(os.environ.get("CODEX_SESSION_BUNDLE_PATH", ""))
if not bundle_b64:
    raise SystemExit(0)
try:
    decoded = base64.b64decode(bundle_b64).decode("utf-8")
except Exception as exc:  # noqa: BLE001
    print(f"[codex-launch] failed to decode session bundle: {exc}", file=sys.stderr)
    raise SystemExit(96) from exc
if not target_path:
    print("[codex-launch] missing CODEX_SESSION_BUNDLE_PATH", file=sys.stderr)
    raise SystemExit(96)
target_path.parent.mkdir(parents=True, exist_ok=True)
target_path.write_text(decoded, encoding="utf-8")
os.chmod(target_path, 0o600)
print(f"[codex-launch] Session bundle staged at {target_path}", file=sys.stderr)
PY
  unset CODEX_SESSION_BUNDLE_B64
fi

PROMPT_CONTENT="${CODEX_PROMPT:-}"

CODEX_CMD=("${CODEX_BIN}" exec "--cd" "${WORKDIR}")
for flag in "${FLAG_ARRAY[@]}"; do
  CODEX_CMD+=("${flag}")
done

if [[ -n "${PROMPT_CONTENT}" ]]; then
  printf '%s' "${PROMPT_CONTENT}" | "${CODEX_CMD[@]}" -
else
  "${CODEX_CMD[@]}" ""
fi

/usr/local/bin/finish_task.sh
