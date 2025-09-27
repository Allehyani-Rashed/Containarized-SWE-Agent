#!/usr/bin/env bash
set -euo pipefail

TARBALL_PATH=${1:-}
DOWNLOAD_URL=${2:-}
DEST_ROOT="/opt/codex"
EXTRACT_DIR="${DEST_ROOT}/dist"
BIN_DIR="${DEST_ROOT}/bin"
BOOTSTRAP_DIR="${DEST_ROOT}/bootstrap"
VERSION_FILE="${DEST_ROOT}/VERSION"
PROFILE_SNIPPET="/etc/profile.d/codex-agent.sh"

# Auto-fetch defaults (override with environment variables if needed).
PINNED_AGENT_VERSION=${CODEX_AGENT_PINNED_VERSION:-"0.42.0"}
PINNED_AGENT_URL=${CODEX_AGENT_PINNED_URL:-"https://github.com/openai/codex/releases/download/rust-v${PINNED_AGENT_VERSION}/codex-x86_64-unknown-linux-gnu.tar.gz"}
PINNED_AGENT_SHA256=${CODEX_AGENT_PINNED_SHA256:-"0b87da1bd496bdc8638053adab5718b4edd271c8415d171b70cbf1149e47b2f8"}
AUTO_DOWNLOAD_ENABLED=${CODEX_AGENT_AUTO_DOWNLOAD:-1}
AUTO_FORCE_DOWNLOAD=${CODEX_AGENT_FORCE_DOWNLOAD:-0}
DOWNLOAD_CACHE_DIR="${DEST_ROOT}/downloads"
TMP_TARBALL=""
DOWNLOADED_TARBALL=""

cleanup_tmp() {
  if [[ -n "${TMP_TARBALL:-}" && -f "${TMP_TARBALL}" ]]; then
    rm -f "${TMP_TARBALL}"
  fi
}

trap cleanup_tmp EXIT

fetch_pinned_agent() {
  local url=$1
  local version=$2
  local sha256_expected=$3
  local force=$4

  if [[ -z "${url}" ]]; then
    return 1
  fi

  mkdir -p "${DOWNLOAD_CACHE_DIR}"
  local target="${DOWNLOAD_CACHE_DIR}/codex-agent-${version}.tar.gz"

  if [[ ! -f "${target}" || "${force}" == "1" ]]; then
    echo "[install_codex_agent] downloading Codex agent ${version} from ${url}" >&2
    if ! curl -fsSL "${url}" -o "${target}.partial"; then
      echo "[install_codex_agent] failed to download ${url}" >&2
      rm -f "${target}.partial"
      return 1
    fi
    mv "${target}.partial" "${target}"
  else
    echo "[install_codex_agent] reusing cached Codex agent ${version}" >&2
  fi

  if [[ -n "${sha256_expected}" ]]; then
    if command -v sha256sum >/dev/null 2>&1; then
      if ! echo "${sha256_expected}  ${target}" | sha256sum --check --status; then
        echo "[install_codex_agent] checksum verification failed for ${target}" >&2
        return 1
      fi
    else
      echo "[install_codex_agent] sha256sum unavailable; skipping checksum validation" >&2
    fi
  fi

  DOWNLOADED_TARBALL="${target}"
  return 0
}

if [[ -n "${DOWNLOAD_URL}" ]]; then
  TMP_TARBALL=$(mktemp /tmp/codex-agent.XXXXXX)
  echo "[install_codex_agent] downloading Codex agent from ${DOWNLOAD_URL}" >&2
  curl -fsSL "${DOWNLOAD_URL}" -o "${TMP_TARBALL}"
  TARBALL_PATH="${TMP_TARBALL}"
fi

if [[ -z "${TARBALL_PATH}" && -z "${DOWNLOAD_URL}" ]]; then
  if [[ "${AUTO_DOWNLOAD_ENABLED}" == "1" ]]; then
    if fetch_pinned_agent "${PINNED_AGENT_URL}" "${PINNED_AGENT_VERSION}" "${PINNED_AGENT_SHA256}" "${AUTO_FORCE_DOWNLOAD}"; then
      TARBALL_PATH="${DOWNLOADED_TARBALL}"
    else
      echo "[install_codex_agent] auto-download failed" >&2
      exit 1
    fi
  else
    echo "[install_codex_agent] auto-download disabled; keeping bootstrap shim" >&2
    exit 0
  fi
fi

if [[ -n "${TARBALL_PATH}" && ! -f "${TARBALL_PATH}" ]]; then
  RELATIVE_CANDIDATE="${BOOTSTRAP_DIR}/${TARBALL_PATH}"
  if [[ -f "${RELATIVE_CANDIDATE}" ]]; then
    TARBALL_PATH="${RELATIVE_CANDIDATE}"
  fi
fi

if [[ ! -f "${TARBALL_PATH}" ]]; then
  echo "[install_codex_agent] tarball not found: ${TARBALL_PATH}" >&2
  exit 1
fi

echo "[install_codex_agent] installing Codex agent from ${TARBALL_PATH}" >&2
rm -rf "${EXTRACT_DIR}"
mkdir -p "${EXTRACT_DIR}" "${BIN_DIR}"

if ! tar -xzf "${TARBALL_PATH}" -C "${EXTRACT_DIR}" 2>/dev/null; then
  tar -xf "${TARBALL_PATH}" -C "${EXTRACT_DIR}"
fi

BINARY_PATH=""
codex_like=""
first_exec=""
while IFS= read -r -d '' candidate; do
  name=$(basename "${candidate}")
  if [[ "${name}" == "codex" ]]; then
    BINARY_PATH="${candidate}"
    break
  fi
  if [[ -z "${codex_like}" && "${name}" == codex-* ]]; then
    codex_like="${candidate}"
    continue
  fi
  if [[ -z "${first_exec}" ]]; then
    first_exec="${candidate}"
  fi
done < <(find "${EXTRACT_DIR}" -type f -perm -u+x -print0)

if [[ -z "${BINARY_PATH}" ]]; then
  if [[ -n "${codex_like}" ]]; then
    BINARY_PATH="${codex_like}"
  elif [[ -n "${first_exec}" ]]; then
    BINARY_PATH="${first_exec}"
  fi
fi

if [[ -z "${BINARY_PATH}" ]]; then
  echo "[install_codex_agent] extracted archive does not contain an executable" >&2
  exit 1
fi

install -m 0755 "${BINARY_PATH}" "${BIN_DIR}/codex"
ln -sf "${BIN_DIR}/codex" "/usr/local/bin/codex"

VERSION_LABEL=${CODEX_AGENT_VERSION_LABEL:-}
if [[ -z "${VERSION_LABEL}" ]]; then
  if [[ -n "${PINNED_AGENT_VERSION}" ]]; then
    VERSION_LABEL="codex-cli ${PINNED_AGENT_VERSION}"
  else
    VERSION_LABEL="codex (custom)"
  fi
fi
printf '%s\n' "${VERSION_LABEL}" >"${VERSION_FILE}"
chmod 0644 "${VERSION_FILE}"
mkdir -p "$(dirname "${PROFILE_SNIPPET}")"
cat <<EOF >"${PROFILE_SNIPPET}"
export CODEX_AGENT_VERSION_LABEL="${VERSION_LABEL}"
EOF
chmod 0644 "${PROFILE_SNIPPET}"

if [[ -d "${EXTRACT_DIR}" ]]; then
  echo "[install_codex_agent] Codex agent installed to ${BIN_DIR}/codex" >&2
fi
