#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
  printf '[reset] %s\n' "$1"
}

log "Stopping running services"
if [[ -x "$ROOT_DIR/scripts/stop.sh" ]]; then
  "$ROOT_DIR/scripts/stop.sh"
else
  log "stop.sh not found; skipping process shutdown"
fi

if command -v docker >/dev/null 2>&1; then
  log "Resetting docker compose stack"
  docker compose -f "$ROOT_DIR/docker-compose.yml" down --remove-orphans --volumes >/dev/null 2>&1 || true

  codex_containers=$(docker ps -aq --filter "name=codex" 2>/dev/null || true)
  if [[ -n "$codex_containers" ]]; then
    log "Removing docker containers with codex prefix"
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

log "Pruning SQLite database files"
db_files=$(find "$ROOT_DIR/app" -maxdepth 1 -type f -name '*.db' -print 2>/dev/null || true)
if [[ -n "$db_files" ]]; then
  while IFS= read -r db_file; do
    [[ -z "$db_file" ]] && continue
    rm -f "$db_file"
  done <<< "$db_files"
else
  log "No SQLite database files found"
fi

workspace_dir="$ROOT_DIR/workspaces"
if [[ -d "$workspace_dir" ]]; then
  log "Clearing sanitized workspaces"
  find "$workspace_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
else
  log "Workspace directory not present; skipping"
fi

log "Reset complete"
