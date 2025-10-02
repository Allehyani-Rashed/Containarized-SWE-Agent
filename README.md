# Containerized Codex Agent

A local-first playground for the Codex runner: give it a prompt, it sanitizes your repo, executes inside Docker with a locked-down proxy, and prepares a GitLab merge request.

## What You Get
- FastAPI backend that schedules/namespaces each task.
- Multipage React dashboard with dedicated Submit Task, Tasks, Projects, and Settings pages plus live log streaming.
- Task history supports status/model/branch filters, pagination-ready endpoints, loading skeletons, and accessible abort/delete flows; log snapshots now return branch/model/abort metadata for CLI consumers.
- Docker runner image with Tinyproxy enforcing deny-by-default egress.
- Helper scripts for PAT management, smoke tests, and threat scans.

## Before You Start
- Docker Engine ≥ 26 with Compose v2.24.
- Python 3.11.x, Node.js 22.x, npm 10.x, Git ≥ 2.44.
- A `.env` file based on `.env.example` with your GitLab project path, PAT, and ChatGPT session bundle plus `DOCKER_HOST` socket. By default the tooling reads a session bundle from `chatgpt_session_bundle.json`; override with `CHATGPT_SESSION_BUNDLE_PATH` or inline `CHATGPT_SESSION_JSON`.
- (Optional) `.env.e2e.local` copied from `.env.e2e.example` when you plan to run the Playwright UI smoke test—populate it with throwaway GitLab + Codex credentials.

## First Run (about 5 minutes)
1. Copy and edit your config:
   ```bash
   cp .env.example .env
   # fill in GitLab host/project/token + Codex creds
   ```
2. Bootstrap everything:
   ```bash
   make setup
   ```
   This invokes `scripts/quickstart.sh` to build the Docker runner, install backend/frontend dependencies, start the Tinyproxy sidecar, write credentials from `.env` into the local database (PAT plus ChatGPT session bundle), and clone your repository into `project-cache/<slug>/repo` when the cache is missing. The helper honours `PROJECT_CACHE_ROOT` so the entire cache tree stays under a predictable directory without asking for a local path.
3. Start the app servers:
   ```bash
   source .venv/bin/activate
   make dev  # FastAPI on :8000, Vite UI on :5173 (re-syncs credentials from .env)
   ```
4. Open the dashboard at <http://127.0.0.1:5173> (leave `make dev` running). Use the navigation bar to jump between Submit Task, Tasks, Projects, and Settings. The Projects view now surfaces a sortable overview (repository URL, host, default branch, allowlist status, credential signals, cache status/commit, and last Codex activity) with quick actions to edit, delete, copy a cache refresh CLI snippet, or open the per-project detail page.

## Register a Project
Use the Projects page in the UI for inline validation, credential indicators, and recent activity snapshots, or run the same API call by hand:
```bash
source .env
curl -sS -X POST "$BACKEND_API_BASE/projects" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "name": "${PROJECT_NAME}",
  "default_branch": "${PROJECT_DEFAULT_BRANCH}",
  "gitlab_host": "${GITLAB_HOST}",
  "gitlab_project_path": "${GITLAB_PROJECT_PATH}"
}
JSON
```
Optionally include `cache_quota_mb` (megabytes), `cache_prune_after_hours` (hours), or an `allowlist` array of domains to seed the project's outbound proxy rules. If `.env` already describes this project, `quickstart` creates it automatically, bootstraps `project-cache/<slug>/repo`, and `make dev` keeps it in sync. Otherwise, record the `id` from the response (e.g. `export PROJECT_ID=1`) and open `/projects/${PROJECT_ID}` in the UI to review credentials, cache path/status/commit metadata, configured allowlist domains, and recent task runs from the dedicated detail page (which also exposes a copy-ready cache refresh command).

## Run Your First Task
```bash
: "${TASK_PROMPT:=Quickstart sanity check}"
curl -sS -X POST "$BACKEND_API_BASE/tasks" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "project_id": ${PROJECT_ID},
  "prompt": "${TASK_PROMPT}",
  "mr_title": "Quickstart: ${TASK_PROMPT}"
}
JSON
```
Watch the run live in the dashboard. When Docker is available the orchestrator spins up the runner image and streams its output; locally you can dry-run with `RUNNER_GIT_DRY_RUN=1`.
Provide `target_branch` when you need to branch from something other than the project's default, `branch_name` to pin the generated task branch, `mr_title` to override the auto-generated merge request title, plus `codex_model` (defaults to `gpt-5-codex`) and `codex_reasoning_effort` (`low`/`medium`/`high`) if you want Codex to control the model or reasoning profile; the Tasks view surfaces those fields and the log snapshot API echoes them back for tooling like `scripts/test_docker_path.py`.

## Everyday Commands
- `make dev` – run backend + UI together.
- `make stop` – stop dev servers and compose sidecars.
- `make reset` – remove Codex containers, SQLite state, and sanitized workspaces.
- `make e2e-ui` – run the Playwright UI smoke (expects `scripts/e2e_env.sh` to resolve `E2E_*` secrets or exported equivalents).
- `make setup` – run the full quickstart bootstrap (build runner, install deps, start proxy).
- `python3 scripts/test_docker_path.py --disable-docker` – quick smoke test of the workflow.
- `make threat-scan` – verifies container guardrails and breakout probes.
- `scripts/codex pat store|clear|import-chatgpt` – manage GitLab PATs or Codex session bundles.
- `python3 scripts/project_cache.py --refresh --project-id <id>` – repair or refresh cached clones at `project-cache/<slug>/repo` without touching sanitised workspaces.

## Good To Know
- Tasks route through Tinyproxy with a deny-by-default allowlist. Adjust long-lived domains in `proxy/base_allowlist.conf` or update each project's allowlist from the Projects UI/API before submitting tasks.
- The runner bundles the real Codex CLI. Skip installation only if you deliberately set `CODEX_ALLOW_STUB=1`.
- Large build artefacts can bloat sanitized workspaces—prune with `git clean -fdx` or update `.projectsanitize` (legacy `.codexignore`) before long runs.
- Cache issues are resolved from the deterministic clone under `project-cache/<slug>/repo`; run `scripts/project_cache.py --refresh` (optionally with `--project-id`) to rebuild it instead of editing `.env` or exporting legacy path variables.
- Log snapshots (`GET /tasks/{id}/logs?follow=0`) include the task status, branch, base branch, Codex model, and whether an abort was requested so operator tooling can annotate history without another API call.
- The project cache is rewound to the task's base branch before each run. Switching between `main` and, say, `release` reuses the existing clone and only performs a fetch/reset for the requested branch.
- Use `python3 scripts/migrate_projectsanitize.py [path]` to rename legacy `.codexignore` files; the helper merges entries so sanitized workspaces stay lean.
- Threat model details and hardening expectations live in `THREAT_MODEL.md`.

## UI E2E Smoke Test
1. Copy the Playwright secret template and fill in throwaway credentials:
   ```bash
   cp .env.e2e.example .env.e2e.local
   # add GitLab PAT, session bundle, repo host/path, default branch
   ```
2. Execute the smoke:
   ```bash
   make e2e-ui
   ```
   The helper script sources `.env.e2e.local` (or exported `E2E_*` variables), masks values for confirmation, installs Playwright’s Chromium build into `.playwright/`, then launches FastAPI + Vite through `ui/playwright.config.ts`. The suite seeds `[E2E] Playwright Smoke Project` via the backend API, verifies credential banners on Submit Task, and exercises the Projects dashboard. Set `ENABLE_CI_E2E_UI=0` to skip the suite when invoking Playwright directly.

## Project Map
- `app/` – FastAPI orchestrator and API tests.
- `ui/` – React + Vite client.
- `runner/` – Docker image and runtime scripts (`finish_task.sh`, `codex` bootstrap).
- `proxy/` – Tinyproxy configuration.
- `scripts/` – Automation helpers, including `quickstart.sh` and PAT tooling.
- `workspaces/` – Ephemeral sanitized task directories (ignored by git).

Have fun automating your repos! If something looks off, check the live task log stream, rerun with `--keep-workspace` on `scripts/test_docker_path.py`, and peek into the captured snapshot.
