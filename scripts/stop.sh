#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
  printf '[stop] %s\n' "$1"
}

kill_pattern() {
  local pattern="$1"
  if pgrep -af "$pattern" >/dev/null 2>&1; then
    log "Stopping processes matching: $pattern"
    pkill -f "$pattern" >/dev/null 2>&1 || true
  fi
}

kill_port() {
  local port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  local pids
  pids=$(lsof -t -i tcp:"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    log "Freeing TCP port $port"
    while read -r pid; do
      [[ -z "$pid" ]] && continue
      kill "$pid" >/dev/null 2>&1 || true
    done <<< "$pids"
  fi
}

log "Stopping developer processes"
kill_pattern "scripts/dev.sh"
kill_pattern "uvicorn app.main:app"
kill_pattern "npm run dev -- --host 127.0.0.1"
kill_pattern "vite dev --host 127.0.0.1"
kill_port 8000
kill_port 5173

if command -v docker >/dev/null 2>&1; then
  log "Bringing down docker compose services"
  (cd "$ROOT_DIR" && docker compose down --remove-orphans >/dev/null 2>&1 || true)

  codex_containers=$(docker ps -aq --filter "name=codex" 2>/dev/null || true)
  if [[ -n "$codex_containers" ]]; then
    log "Removing stale docker containers"
    while IFS= read -r container_id; do
      [[ -z "$container_id" ]] && continue
      docker rm -f "$container_id" >/dev/null 2>&1 || true
    done <<< "$codex_containers"
  fi

  if docker network inspect codex-shared >/dev/null 2>&1; then
    log "Removing docker network codex-shared"
    docker network rm codex-shared >/dev/null 2>&1 || true
  fi
else
  log "Docker not found; skipping container cleanup"
fi

log "Workspace services stopped"
