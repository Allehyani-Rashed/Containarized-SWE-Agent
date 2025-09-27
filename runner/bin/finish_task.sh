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

REQUIRED_VARS=(GITLAB_TOKEN GITLAB_HOST GITLAB_PROJECT_PATH TARGET_BRANCH BRANCH MR_TITLE RUNNER_RESULT_FILE)
for var in "${REQUIRED_VARS[@]}"; do
  require_env "$var"
done

WORKDIR=$(pwd)
TASK_ID_LABEL=${TASK_ID:-unknown}

GITLAB_HOST_RAW=${GITLAB_HOST%/}
if [[ ! "$GITLAB_HOST_RAW" =~ ^https?:// ]]; then
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

git config --global user.name "${GIT_USER_NAME:-Codex Runner}"
git config --global user.email "${GIT_USER_EMAIL:-codex@gitlab.local}"
git config --global --add safe.directory "${WORKDIR}"
git config --global --add safe.directory "/work"
git config --global core.hooksPath /dev/null

export GIT_TERMINAL_PROMPT=0

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  error "Current directory is not a git repository: ${WORKDIR}"
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  if ! git fetch origin "${TARGET_BRANCH_NAME}" >/dev/null 2>&1; then
    log "Fetch of origin/${TARGET_BRANCH_NAME} skipped or failed"
  fi
fi

if git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH_NAME}"; then
  git checkout "${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout "${TARGET_BRANCH_NAME}"
elif git show-ref --verify --quiet "refs/remotes/origin/${TARGET_BRANCH_NAME}"; then
  git checkout -B "${TARGET_BRANCH_NAME}" "origin/${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${TARGET_BRANCH_NAME}" "origin/${TARGET_BRANCH_NAME}"
else
  error "Target branch ${TARGET_BRANCH_NAME} not found locally or on origin"
  exit 1
fi

git checkout -B "${BRANCH_NAME}" "${TARGET_BRANCH_NAME}" >/dev/null 2>&1 || git checkout -B "${BRANCH_NAME}" "${TARGET_BRANCH_NAME}"

log "Branch ${BRANCH_NAME} prepared"

git add -A

git commit --allow-empty -m "${MR_TITLE_TEXT}" >/dev/null 2>&1 || git commit --allow-empty -m "${MR_TITLE_TEXT}"

log "Commit created for merge request"

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
  log "Dry run enabled; skipping git push and merge request creation"
  MR_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/merge_requests"
else
  WORK_TMP_DIR="/work/tmp"
  if ! mkdir -p "${WORK_TMP_DIR}" 2>/dev/null; then
    WORK_TMP_DIR="${WORKDIR}/.codex-tmp"
    mkdir -p "${WORK_TMP_DIR}"
  fi
  ASKPASS_SCRIPT=$(mktemp -p "${WORK_TMP_DIR}" codex-askpass-XXXXXX)
  PUSH_OUTPUT_FILE=$(mktemp -p "${WORK_TMP_DIR}" codex-push-XXXXXX)
  API_OUTPUT_FILE=$(mktemp -p "${WORK_TMP_DIR}" codex-api-XXXXXX)
  export API_OUTPUT_FILE

  cat <<'SCRIPT' >"${ASKPASS_SCRIPT}"
#!/usr/bin/env bash
printf '%s' "${GITLAB_TOKEN}"
SCRIPT
  chmod 700 "${ASKPASS_SCRIPT}"

  export GIT_ASKPASS="${ASKPASS_SCRIPT}"
  export GIT_USERNAME="oauth2"
  REMOTE_URL="https://${GIT_USERNAME}@${GITLAB_HOST_STRIPPED}/${PROJECT_PATH}.git"

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
fi

if [[ -z "${MR_URL}" ]]; then
  MR_URL="${GITLAB_BASE_URL}/${PROJECT_PATH}/-/merge_requests"
  log "Merge request URL not found; defaulting to project MR list"
fi

export MR_URL
log "Merge request available at ${MR_URL}"

python3 - <<'PY'
import json
import os
import pathlib

result_path = os.environ.get("RUNNER_RESULT_FILE", "CODEX_RESULT.json")
if not os.path.isabs(result_path):
    result_path = os.path.join(os.getcwd(), result_path)
path = pathlib.Path(result_path)
path.parent.mkdir(parents=True, exist_ok=True)
output = {"branch": os.environ.get("BRANCH", ""), "mr_url": os.environ.get("MR_URL", "")}
path.write_text(json.dumps(output) + "\n", encoding="utf-8")
PY

if [[ "${DRY_RUN}" == "1" ]]; then
  log "finish_task completed (dry run)"
else
  log "finish_task completed"
fi
