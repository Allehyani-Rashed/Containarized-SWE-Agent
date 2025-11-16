#!/usr/bin/env bash
set -euo pipefail

TARBALL_PATH=${1:-}
DOWNLOAD_URL=${2:-}
DEST_ROOT="/opt/claude-code"
EXTRACT_DIR="${DEST_ROOT}/dist"
BIN_DIR="${DEST_ROOT}/bin"
BOOTSTRAP_DIR="${DEST_ROOT}/bootstrap"
VERSION_FILE="${DEST_ROOT}/VERSION"
PROFILE_SNIPPET="/etc/profile.d/claude-code.sh"

# Auto-fetch defaults (override with environment variables if needed).
# Note: Claude Code is distributed via npm, so we'll install it using npm
PINNED_VERSION=${CLAUDE_CODE_PINNED_VERSION:-"latest"}
AUTO_DOWNLOAD_ENABLED=${CLAUDE_CODE_AUTO_DOWNLOAD:-1}
DOWNLOAD_CACHE_DIR="${DEST_ROOT}/downloads"

cleanup_tmp() {
  :  # No-op for now, can be extended if needed
}

trap cleanup_tmp EXIT

install_via_npm() {
  local version=$1

  echo "[install_claude_code] installing Claude Code ${version} via npm" >&2

  # Install nodejs and npm if not already installed
  if ! command -v npm >/dev/null 2>&1; then
    echo "[install_claude_code] npm not found, installing nodejs and npm" >&2
    apt-get update -qq
    apt-get install -y -qq nodejs npm
  fi

  # Create bin directory
  mkdir -p "${BIN_DIR}"

  # Install @anthropic-ai/claude-code globally to our custom location
  if [[ "${version}" == "latest" ]]; then
    npm install -g --prefix="${DEST_ROOT}" @anthropic-ai/claude-code
  else
    npm install -g --prefix="${DEST_ROOT}" "@anthropic-ai/claude-code@${version}"
  fi

  # Find the installed binary
  BINARY_PATH=$(find "${DEST_ROOT}" -name "claude" -type f -executable | head -n 1)

  if [[ -z "${BINARY_PATH}" ]]; then
    echo "[install_claude_code] failed to find claude binary after npm install" >&2
    return 1
  fi

  # Create symlink
  ln -sf "${BINARY_PATH}" "${BIN_DIR}/claude"
  ln -sf "${BIN_DIR}/claude" "/usr/local/bin/claude"

  # Get installed version
  local installed_version=$(claude --version 2>&1 | head -n 1 || echo "unknown")

  VERSION_LABEL=${CLAUDE_CODE_VERSION_LABEL:-"claude-code ${installed_version}"}
  printf '%s\n' "${VERSION_LABEL}" >"${VERSION_FILE}"
  chmod 0644 "${VERSION_FILE}"

  mkdir -p "$(dirname "${PROFILE_SNIPPET}")"
  cat <<EOF >"${PROFILE_SNIPPET}"
export CLAUDE_CODE_VERSION_LABEL="${VERSION_LABEL}"
EOF
  chmod 0644 "${PROFILE_SNIPPET}"

  echo "[install_claude_code] Claude Code installed to ${BIN_DIR}/claude" >&2
  return 0
}

if [[ "${AUTO_DOWNLOAD_ENABLED}" == "1" ]]; then
  if install_via_npm "${PINNED_VERSION}"; then
    echo "[install_claude_code] installation successful" >&2
    exit 0
  else
    echo "[install_claude_code] installation failed" >&2
    exit 1
  fi
else
  echo "[install_claude_code] auto-download disabled; skipping installation" >&2
  exit 0
fi
