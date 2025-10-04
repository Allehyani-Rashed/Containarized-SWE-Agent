# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Containerized Codex Agent is a local-first orchestrator that runs Codex agents inside Docker containers with network sandboxing. Tasks run in sanitized Git workspaces, execute inside locked-down containers routed through Tinyproxy (deny-by-default), and produce GitLab merge requests automatically.

**Core workflow**: User submits prompt → FastAPI backend queues task → Worker clones/sanitizes repo → Docker container executes Codex CLI → `finish_task.sh` creates branch/MR → UI streams logs and captures results.

## Architecture

### Backend (`app/`)
- **`main.py`**: FastAPI app with routes for projects, tasks, integrations (PAT/session management), and log streaming
- **`worker.py`**: `TaskQueueManager` — single-consumer queue that processes tasks sequentially, manages log storage/streaming, and handles credential caching
- **`codex_runner.py`**: Orchestrates Docker container lifecycle; falls back to local stub if Docker unavailable; streams logs and parses metadata
- **`project_cache.py`**: Manages deterministic Git clones under `project-cache/<slug>/repo`; supports branch rewinding, cache refresh, and quota enforcement
- **`sanitizer.py`**: Creates ephemeral workspaces by copying cached repo and filtering files via `.projectsanitize`
- **`integrations.py`**: Manages GitLab PATs sourced from `.env` (plaintext in DB) and encrypts ChatGPT session bundles; supports verification via GitLab API
- **`allowlist.py`**: Normalizes per-project domain allowlists and regenerates Tinyproxy `filter.list`
- **`proxy_runtime.py`**: Ensures `codex-egress-proxy` compose service and `codex-shared` network are running before tasks start
- **`database.py`**: SQLModel schema initialization; includes migrations for adding columns (e.g., `target_branch`, `allowlist`)
- **`models.py`**: SQLModel definitions for `Project`, `Task`, `AuditLog`, `IntegrationCredential`

### Frontend (`ui/src/`)
- **`App.tsx`**: React Router setup with navigation to Submit Task, Tasks, Projects, Settings
- **`pages/TaskSubmitPage.tsx`**: Form for prompt/branch/model/MR title submission; warns if PAT missing
- **`pages/TaskListPage.tsx`**: Paginated task table with status/model/branch filters, abort/delete modals, log viewer
- **`pages/ProjectsPage.tsx`**: Sortable project grid showing repository URL, default branch, allowlist status, credential signals, cache metadata
- **`pages/ProjectDetailPage.tsx`**: Per-project view with credential summary, recent tasks, cache refresh command
- **`pages/SettingsPage.tsx`**: PAT/session management with store/clear/verify flows and `.env`-backed guidance

### Runner (`runner/`)
- **`Dockerfile`**: Builds `local-codex-runner:latest` with hardened settings (read-only root, no-new-privileges, tmpfs mounts, dropped capabilities)
- **`bin/install_codex_agent.sh`**: Downloads/verifies pinned Codex CLI during image build; fails if binary missing
- **`bin/codex`**: Placeholder shim for Docker-free dry runs (only active when `CODEX_ALLOW_STUB=1`)
- **`bin/launch_codex.sh`**: Entrypoint that stages ChatGPT session bundle, invokes `codex exec`, then runs `finish_task.sh`
- **`bin/finish_task.sh`**: Stages changes, creates `codex/task-<date>-<id>` branch, pushes with merge-request push options or REST fallback

### Proxy (`proxy/`)
- **`base_allowlist.conf`**: Default Tinyproxy filter seeding GitLab hosts, package registries, `chatgpt.com`
- **`filter.list`**: Regenerated per-task with merged base + project-specific domains

## Common Development Tasks

### Build and run
```bash
# First-time setup (builds runner, installs deps, starts proxy)
make setup

# Start backend + UI (activates venv, syncs credentials from .env)
source .venv/bin/activate && make dev
# FastAPI: http://127.0.0.1:8000
# Vite UI: http://127.0.0.1:5173

# Backend only (for API work)
make api

# Frontend only (for UI iteration)
make ui
```

### Testing
```bash
# Run all backend tests
python3 -m unittest discover -s app/tests

# Run specific test module
python3 -m unittest app.tests.test_phase5

# Lint frontend
npm --prefix ui run lint

# Compile Python sources (catches syntax errors)
python3 -m compileall app/app app/tests

# UI end-to-end smoke test (requires .env.e2e.local)
make e2e-ui
```

### Docker smoke tests
```bash
# Local dry-run (no Docker)
python3 scripts/test_docker_path.py --disable-docker

# Full Docker path
python3 scripts/test_docker_path.py --prompt "Add healthz endpoint"

# With custom allowlist
python3 scripts/test_docker_path.py --allowlist="example.com,pypi.org"

# Keep workspace for inspection
python3 scripts/test_docker_path.py --keep-workspace
```

### Credential management
```bash
# Store GitLab PAT
scripts/codex pat store

# Clear PAT (fails pending tasks)
scripts/codex pat clear

# Import ChatGPT session bundle
scripts/codex pat import-chatgpt

# Clear session bundle
scripts/codex pat clear-chatgpt

# Dry-run mode (no API calls)
RUNNER_GIT_DRY_RUN=1 scripts/codex pat store
```

### Project cache operations
```bash
# Refresh cache for specific project
python3 scripts/project_cache.py --refresh --project-id 1

# Refresh all project caches
python3 scripts/project_cache.py --refresh

# Check cache status
python3 scripts/project_cache.py --status
```

### Other utilities
```bash
# Stop all services
make stop

# Reset containers, DB, and workspaces
make reset

# Run threat model validation
make threat-scan

# Migrate legacy .codexignore to .projectsanitize
python3 scripts/migrate_projectsanitize.py [path]
```

## Key Architecture Patterns

### Task Execution Flow
1. **Submission**: User POSTs to `/tasks` with `project_id`, `prompt`, optional `target_branch`/`branch_name`/`mr_title`
2. **Queue**: Worker picks task from queue, loads cached credentials (GitLab PAT + ChatGPT session)
3. **Cache**: `bootstrap_project_cache` clones repo to `project-cache/<slug>/repo` if missing; `snapshot_project_cache` rewinds to `target_branch`
4. **Sanitize**: `sanitize_workspace` copies cache to `workspaces/task-<id>`, filtering via `.projectsanitize`
5. **Allowlist**: Merges `proxy/base_allowlist.conf` + project allowlist → regenerates `proxy/filter.list`
6. **Docker**: Spins up hardened container with workspace mounted at `/work`, proxy env vars, memory/PID limits
7. **Execution**: Container runs `launch_codex.sh` → `codex exec` → `finish_task.sh` → creates branch/MR
8. **Finalize**: Worker parses `CODEX_RESULT.json` for branch/MR URL, persists to DB, marks task done/failed

### Credential Lifecycle
- **Storage**: GitLab PATs are loaded from `.env` and stored plaintext in the credential table for local deployments, while ChatGPT session bundles remain encrypted via Fernet.
- **Caching**: Worker loads credentials once at startup, invalidates on credential rotation events
- **Propagation**: Runner receives PAT via `GITLAB_TOKEN` env; session bundle base64-encoded in `CODEX_SESSION_BUNDLE_B64`
- **Verification**: `/integrations/pat/verify` tests PAT against GitLab API, records host/timestamp/status

### Project Cache Strategy
- **Path**: `project-cache/<gitlab_host>/<project_path>/repo` (normalized slug)
- **Rewind**: Before each task, `git fetch && git reset --hard origin/<target_branch>` ensures clean state
- **Quota**: Optional `cache_quota_mb` enforced via `enforce_cache_policy` (prunes `.git/objects`)
- **Locking**: File lock under `project-cache/<slug>/cache.lock` prevents concurrent modifications (180s timeout)

### Log Streaming Architecture
- **Capture**: Worker appends logs to in-memory buffer + redacted disk file (`workspaces/logs/<task_id>.log`)
- **Streaming**: `/tasks/{id}/logs?follow=1` returns SSE stream; clients poll via `asyncio` generator
- **Snapshot**: `/tasks/{id}/logs?follow=0` returns JSON with full history + task metadata (status, branch, model, abort flag)
- **Redaction**: `GITLAB_TOKEN=...` masked as `GITLAB_TOKEN=<redacted>` in stored logs

### Proxy Stack Management
- **Preflight**: Before each Docker task, `ensure_proxy_stack` calls `docker compose up -d codex-egress-proxy` and attaches `codex-shared` network
- **Reload**: After regenerating `filter.list`, worker exec's `docker compose restart codex-egress-proxy` to apply changes
- **Bypass**: Stub mode (`RUNNER_DISABLE_DOCKER=1`) skips proxy checks; network errors logged but don't block local runs

## Important Environment Variables

- `BACKEND_API_BASE`: Backend URL for scripts (default: `http://127.0.0.1:8000`)
- `DOCKER_HOST`: Docker socket path (e.g., `unix:///Users/rashed/.docker/run/docker.sock`)
- `RUNNER_DISABLE_DOCKER`: Set to `1` to skip Docker and use local stub runner
- `RUNNER_GIT_DRY_RUN`: Set to `1` to skip git pushes (for testing)
- `RUNNER_ALLOW_STUB_FALLBACK`: Set to `0` to fail tasks when Docker unavailable (default: `1`)
- `CODEX_ALLOW_STUB=1`: Permit placeholder codex binary (otherwise runner aborts if real CLI missing)
- `ENCRYPTION_SECRET_KEY`: Fernet key for credential encryption (auto-generated if missing)
- `PROJECT_CACHE_ROOT`: Override default `project-cache/` location
- `PROJECT_CACHE_LOCK_TIMEOUT_SECONDS`: File lock timeout for cache operations (default: 180)

## Code Style

### Python
- Follow PEP 8: `snake_case` for functions/variables, `PascalCase` for classes
- Use timezone-aware UTC timestamps: `datetime.now(timezone.utc)`
- Extend FastAPI via routers (see `integrations_router` in `main.py`)
- Raise `HTTPException` for API errors; log with `logging.getLogger(__name__)`
- Use `SQLModel` for DB models; migrations via `_ensure_*_columns` helpers in `database.py`

### TypeScript/React
- Colocate components in `ui/src/pages/` or `ui/src/components/`
- Use functional components with hooks; avoid class components
- Name component files `PascalCase.tsx`, utility files `camelCase.ts`
- Run `npm --prefix ui run lint` before committing

### General
- LF line endings, final newline (`.editorconfig`)
- 2-space indent for JS/TS/JSON, 4-space for Python

## Debugging Tips

### Task failures
1. Check task logs in UI or via `GET /tasks/{id}/logs?follow=0`
2. Look for `Codex FAIL (exit code 42)` → credential issue
3. Look for `docker: network 'codex-shared' not found` → run `make dev` to start proxy
4. Look for `OOMKilled` → increase `RUNNER_MEM_LIMIT` (default: `2g`)
5. Check workspace snapshot: `scripts/test_docker_path.py --keep-workspace --prompt "test"` leaves `workspaces/task-<id>` intact

### Cache issues
- Verify cache exists: `ls project-cache/<gitlab_host>/<project_path>/repo/.git`
- Refresh cache: `python3 scripts/project_cache.py --refresh --project-id <id>`
- Check lock contention: look for `project-cache/<slug>/cache.lock` held by stale process

### Proxy connectivity
- Ensure compose stack running: `docker compose ps` should show `codex-egress-proxy` up
- Check network: `docker network ls | grep codex-shared`
- Tail proxy logs: `docker compose logs -f codex-egress-proxy`
- Test allowlist: add domain to project allowlist in UI, submit task, check logs for denied hosts

### Credential errors
- Verify PAT: POST `/integrations/pat/verify` or use UI Settings → Verify PAT button
- Check encryption key: ensure `ENCRYPTION_SECRET_KEY` stable across restarts (stored in `.env`)
- Session bundle: ensure JSON valid; use `scripts/codex pat import-chatgpt` helper

## Git Workflow

- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`
- Keep commits scoped to single concern
- Run tests before pushing: `make test && npm --prefix ui run lint`
- For UI work: include screenshots in PR description
- Flag breaking changes to runner image (requires rebuild)
