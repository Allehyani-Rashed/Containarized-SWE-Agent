#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[finish_task] %s\n' "$*"
}

error() {
  printf '[finish_task][error] %s\n' "$*" >&2
}

require_env() {
  local var_name=$1
  if [[ -z "${!var_name:-}" ]]; then
    error "Required environment variable ${var_name} is missing"
    exit 1
  fi
}

REQUIRED_VARS=(GITLAB_TOKEN GITLAB_HOST GITLAB_PROJECT_PATH TARGET_BRANCH BRANCH MR_TITLE CHANGE_MODE RUNNER_RESULT_FILE)
for var in "${REQUIRED_VARS[@]}"; do
  require_env "$var"
done

WORKDIR=$(pwd)
TASK_ID_LABEL=${TASK_ID:-unknown}
MODEL_ID=${CODEX_MODEL_ID:-}
MODEL_REASONING=${CODEX_MODEL_REASONING_EFFORT:-}

MODE_RAW=${CHANGE_MODE:-merge_request}
MODE_CANON=$(printf '%s' "${MODE_RAW}" | tr '[:upper:]' '[:lower:]')
MODE_CANON=${MODE_CANON//-/_}
case "${MODE_CANON}" in
  merge_request|branch_commit)
    ;;
  *)
    error "Unsupported change mode: ${CHANGE_MODE}"
    exit 1
    ;;
esac

CHANGE_MODE_CANON=${MODE_CANON}
export CHANGE_MODE_CANON

ABORT_FILE_RAW=${CODEX_ABORT_FILE:-}
if [[ -n "${ABORT_FILE_RAW}" ]]; then
  if [[ "${ABORT_FILE_RAW}" == /* ]]; then
    ABORT_FILE="${ABORT_FILE_RAW}"
  else
    ABORT_FILE="${WORKDIR}/${ABORT_FILE_RAW}"
  fi
else
  ABORT_FILE=""
fi

check_abort() {
  if [[ -n "${ABORT_FILE}" && -f "${ABORT_FILE}" ]]; then
    if grep -q 'abort' "${ABORT_FILE}" 2>/dev/null; then
      log "Abort marker detected at ${ABORT_FILE}; skipping finish_task actions"
      exit 0
    fi
  fi
}

check_abort

GITLAB_HOST_RAW=${GITLAB_HOST%/}
if [[ ! "${GITLAB_HOST_RAW}" =~ ^https?:// ]]; then
  GITLAB_BASE_URL="https://${GITLAB_HOST_RAW}"
else
  GITLAB_BASE_URL=${GITLAB_HOST_RAW}
fi
GITLAB_BASE_URL=${GITLAB_BASE_URL%/}
GITLAB_HOST_STRIPPED=${GITLAB_BASE_URL#*://}
GITLAB_HOST_STRIPPED=${GITLAB_HOST_STRIPPED%/}
PROJECT_PATH=${GITLAB_PROJECT_PATH#/}
BRANCH_NAME=${BRANCH}
TARGET_BRANCH_NAME=${TARGET_BRANCH}
MR_TITLE_TEXT=${MR_TITLE}
DRY_RUN=${RUNNER_GIT_DRY_RUN:-0}

log "Preparing git workspace for task ${TASK_ID_LABEL}"
if [[ -n "${MODEL_ID}" ]]; then
  log "Using Codex model ${MODEL_ID}"
fi
if [[ -n "${MODEL_REASONING}" ]]; then
  log "Using reasoning effort ${MODEL_REASONING}"
fi

git config --global user.name "${GIT_USER_NAME:-Codex Runner}"
git config --global user.email "${GIT_USER_EMAIL:-codex@gitlab.local}"
git config --global --add safe.directory "${WORKDIR}"
git config --global --add safe.directory "/work"
git config --global core.hooksPath /dev/null

export GIT_TERMINAL_PROMPT=0

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  error "Current directory is not a git repository: ${WORKDIR}"
  error "Branch context: BRANCH=${BRANCH_NAME:-} TARGET_BRANCH=${TARGET_BRANCH_NAME:-} DRY_RUN=${DRY_RUN}"
  if command -v ls >/dev/null 2>&1; then
    error "Workspace listing (truncated): $(ls -a | head -n 20 | tr '\n' ' ')"
  fi
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  if ! git fetch origin "${TARGET_BRANCH_NAME}" >/dev/null 2>&1; then
    log "Fetch of origin/${TARGET_BRANCH_NAME} skipped or failed"
  fi
  if [[ "${CHANGE_MODE_CANON}" == "branch_commit" ]]; then
    if ! git fetch origin "${BRANCH_NAME}" >/dev/null 2>&1; then
      log "Fetch of origin/${BRANCH_NAME} skipped or failed"
    fi
  fi
fi

if [[ "${CHANGE_MODE_CANON}" == "merge_request" ]]; then
  if git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH_NAME}"; then
    git checkout "${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout "${TARGET_BRANCH_NAME}"
  elif git show-ref --verify --quiet "refs/remotes/origin/${TARGET_BRANCH_NAME}"; then
    git checkout -B "${TARGET_BRANCH_NAME}" "origin/${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${TARGET_BRANCH_NAME}" "origin/${TARGET_BRANCH_NAME}"
  else
    error "Target branch ${TARGET_BRANCH_NAME} not found locally or on origin"
    exit 1
  fi

  git checkout -B "${BRANCH_NAME}" "${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${BRANCH_NAME}" "${TARGET_BRANCH_NAME}"
  log "Branch ${BRANCH_NAME} prepared for merge request"
else
  if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
    git checkout "${BRANCH_NAME}" >/dev/null 2>&1 || git checkout "${BRANCH_NAME}"
  elif git show-ref --verify --quiet "refs/remotes/origin/${BRANCH_NAME}"; then
    git checkout -B "${BRANCH_NAME}" "origin/${BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${BRANCH_NAME}" "origin/${BRANCH_NAME}"
  else
    log "Branch ${BRANCH_NAME} not found; bootstrapping from ${TARGET_BRANCH_NAME}"
    if git show-ref --verify --quiet "refs/remotes/origin/${TARGET_BRANCH_NAME}"; then
      git checkout -B "${BRANCH_NAME}" "origin/${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${BRANCH_NAME}" "origin/${TARGET_BRANCH_NAME}"
    elif git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH_NAME}"; then
      git checkout -B "${BRANCH_NAME}" "${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${BRANCH_NAME}" "${TARGET_BRANCH_NAME}"
    else
      error "Target branch ${TARGET_BRANCH_NAME} not found locally or on origin"
      exit 1
    fi
  fi
  log "Branch ${BRANCH_NAME} prepared for branch update"
fi

git add -A

git commit --allow-empty -m "${MR_TITLE_TEXT}" >/dev/null 2>&1 || git commit --allow-empty -m "${MR_TITLE_TEXT}"

if [[ "${CHANGE_MODE_CANON}" == "merge_request" ]]; then
  log "Commit created for merge request"
else
  log "Commit created for branch update"
fi

COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || printf '')
COMMIT_URL=""
if [[ -n "${COMMIT_SHA}" ]]; then
  COMMIT_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/commit/${COMMIT_SHA}"
  log "Commit SHA ${COMMIT_SHA}"
fi

check_abort

MR_URL=""
ASKPASS_SCRIPT=""
PUSH_OUTPUT_FILE=""
API_OUTPUT_FILE=""
cleanup() {
  if [[ -n "${ASKPASS_SCRIPT}" && -f "${ASKPASS_SCRIPT}" ]]; then
    rm -f "${ASKPASS_SCRIPT}" || true
  fi
  if [[ -n "${PUSH_OUTPUT_FILE}" && -f "${PUSH_OUTPUT_FILE}" ]]; then
    rm -f "${PUSH_OUTPUT_FILE}" || true
  fi
  if [[ -n "${API_OUTPUT_FILE}" && -f "${API_OUTPUT_FILE}" ]]; then
    rm -f "${API_OUTPUT_FILE}" || true
  fi
}
trap cleanup EXIT

if [[ "${DRY_RUN}" == "1" ]]; then
  if [[ "${CHANGE_MODE_CANON}" == "merge_request" ]]; then
    log "Dry run enabled; skipping git push and merge request creation"
    MR_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/merge_requests"
  else
    log "Dry run enabled; skipping git push for branch update"
    if [[ -z "${COMMIT_URL}" ]]; then
      COMMIT_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/tree/${BRANCH_NAME}"
    fi
  fi
else
  check_abort
  WORK_TMP_DIR="/work/tmp"
  if ! mkdir -p "${WORK_TMP_DIR}" 2>/dev/null; then
    WORK_TMP_DIR="${WORKDIR}/.codex-tmp"
    mkdir -p "${WORK_TMP_DIR}"
  fi
  ASKPASS_SCRIPT=$(mktemp -p "${WORK_TMP_DIR}" codex-askpass-XXXXXX)
  PUSH_OUTPUT_FILE=$(mktemp -p "${WORK_TMP_DIR}" codex-push-XXXXXX)
  if [[ "${CHANGE_MODE_CANON}" == "merge_request" ]]; then
    API_OUTPUT_FILE=$(mktemp -p "${WORK_TMP_DIR}" codex-api-XXXXXX)
    export API_OUTPUT_FILE
  else
    API_OUTPUT_FILE=""
  fi

  cat <<'SCRIPT' >"${ASKPASS_SCRIPT}"
#!/usr/bin/env bash
printf '%s' "${GITLAB_TOKEN}"
SCRIPT
  chmod 700 "${ASKPASS_SCRIPT}"

  export GIT_ASKPASS="${ASKPASS_SCRIPT}"
  export GIT_USERNAME="oauth2"
  REMOTE_URL="https://${GIT_USERNAME}@${GITLAB_HOST_STRIPPED}/${PROJECT_PATH}.git"

  if [[ "${CHANGE_MODE_CANON}" == "merge_request" ]]; then
    log "Pushing branch ${BRANCH_NAME} with merge request options"
    if ! git push \
      -o merge_request.create \
      -o merge_request.target="${TARGET_BRANCH_NAME}" \
      -o merge_request.title="${MR_TITLE_TEXT}" \
      "${REMOTE_URL}" "HEAD:${BRANCH_NAME}" >"${PUSH_OUTPUT_FILE}" 2>&1; then
      error "git push failed"
      if [[ -s "${PUSH_OUTPUT_FILE}" ]]; then
        cat "${PUSH_OUTPUT_FILE}" >&2
      fi
      exit 1
    fi

    if [[ -s "${PUSH_OUTPUT_FILE}" ]]; then
      while IFS= read -r line; do
        log "git: ${line}"
      done <"${PUSH_OUTPUT_FILE}"
    fi

    if command -v curl >/dev/null 2>&1; then
      PROJECT_ENCODED=$(python3 - <<'PY'
import os
import urllib.parse
print(urllib.parse.quote(os.environ["GITLAB_PROJECT_PATH"].lstrip('/'), safe=''))
PY
)
      BRANCH_ENCODED=$(python3 - <<'PY'
import os
import urllib.parse
print(urllib.parse.quote(os.environ["BRANCH"], safe=''))
PY
)
      API_URL="${GITLAB_BASE_URL}/api/v4/projects/${PROJECT_ENCODED}/merge_requests?source_branch=${BRANCH_ENCODED}&order_by=updated_at&sort=desc&per_page=1"
      if curl -sS --fail --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" "${API_URL}" >"${API_OUTPUT_FILE}" 2>/dev/null; then
        MR_URL=$(python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["API_OUTPUT_FILE"])
try:
    payload = json.loads(path.read_text(encoding='utf-8'))
except Exception:
    payload = []
if payload:
    print(payload[0].get('web_url', ''))
PY
)
      else
        log "Merge request lookup via API failed"
      fi
    else
      log "curl unavailable; skipping API merge request lookup"
    fi

    if [[ -z "${MR_URL}" && -s "${PUSH_OUTPUT_FILE}" ]]; then
      MR_URL=$(python3 - <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
if path.exists():
    content = path.read_text(encoding='utf-8', errors='ignore')
    matches = re.findall(r'https://[^\s]+/-/merge_requests/\d+', content)
    if matches:
        print(matches[-1])
PY
"${PUSH_OUTPUT_FILE}")
    fi
  else
    log "Pushing branch ${BRANCH_NAME} without merge request options"
    if ! git push "${REMOTE_URL}" "HEAD:${BRANCH_NAME}" >"${PUSH_OUTPUT_FILE}" 2>&1; then
      error "git push failed"
      if [[ -s "${PUSH_OUTPUT_FILE}" ]]; then
        cat "${PUSH_OUTPUT_FILE}" >&2
      fi
      exit 1
    fi

    if [[ -s "${PUSH_OUTPUT_FILE}" ]]; then
      while IFS= read -r line; do
        log "git: ${line}"
      done <"${PUSH_OUTPUT_FILE}"
    fi
  fi
fi

if [[ "${CHANGE_MODE_CANON}" == "merge_request" ]]; then
  if [[ -z "${MR_URL}" ]]; then
    MR_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/merge_requests"
    log "Merge request URL not found; defaulting to project MR list"
  fi
  log "Merge request available at ${MR_URL}"
else
  if [[ -z "${COMMIT_URL}" ]]; then
    if [[ -n "${COMMIT_SHA}" ]]; then
      COMMIT_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/commit/${COMMIT_SHA}"
    else
      COMMIT_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/tree/${BRANCH_NAME}"
    fi
  fi
  log "Branch ${BRANCH_NAME} updated; latest commit ${COMMIT_SHA:-unavailable}"
  log "Commit URL: ${COMMIT_URL}"
fi

export MR_URL
export COMMIT_SHA
export COMMIT_URL
python3 - <<'PY'
import json
import os
import pathlib

result_path = os.environ.get("RUNNER_RESULT_FILE", "CODEX_RESULT.json")
if not os.path.isabs(result_path):
    result_path = os.path.join(os.getcwd(), result_path)
path = pathlib.Path(result_path)
path.parent.mkdir(parents=True, exist_ok=True)
output = {
    "branch": os.environ.get("BRANCH", ""),
    "mr_url": os.environ.get("MR_URL", ""),
    "commit_sha": os.environ.get("COMMIT_SHA", ""),
    "commit_url": os.environ.get("COMMIT_URL", ""),
    "change_mode": os.environ.get("CHANGE_MODE_CANON", ""),
    "codex_model": os.environ.get("CODEX_MODEL_ID", ""),
    "codex_reasoning_effort": os.environ.get("CODEX_MODEL_REASONING_EFFORT", ""),
}
path.write_text(json.dumps(output) + "\n", encoding="utf-8")
PY

if [[ "${DRY_RUN}" == "1" ]]; then
  log "finish_task completed (dry run)"
else
  log "finish_task completed"
fi
