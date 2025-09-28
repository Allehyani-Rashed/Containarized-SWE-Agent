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
- A `.env` file based on `.env.example` with your GitLab project path, PAT, Codex token (or ChatGPT bundle), and `DOCKER_HOST` socket. By default the tooling reads a session bundle from `chatgpt_session_bundle.json`; override with `CHATGPT_SESSION_BUNDLE_PATH` or inline `CHATGPT_SESSION_BUNDLE`.

## First Run (about 5 minutes)
1. Copy and edit your config:
   ```bash
   cp .env.example .env
   # fill in GitLab host/project/token + Codex creds
   ```
2. Bootstrap everything:
   ```bash
   ./scripts/quickstart.sh
   ```
   This builds the Docker runner, installs backend/frontend dependencies, starts the Tinyproxy sidecar, and writes credentials from `.env` into the local database (PAT, Codex token, and optional ChatGPT session bundle).
3. Start the app servers:
   ```bash
   source .venv/bin/activate
   make dev  # FastAPI on :8000, Vite UI on :5173 (re-syncs credentials from .env)
   ```
4. Open the dashboard at <http://127.0.0.1:5173> (leave `make dev` running). Use the navigation bar to jump between Submit Task, Tasks, Projects, and Settings. The Projects view now surfaces a sortable overview (repository URL, host, default branch, allowlist status, credential signals, and last Codex activity) with quick actions to edit, delete, or open the per-project detail page.

## Register a Project
Use the Projects page in the UI for inline validation, credential indicators, and recent activity snapshots, or run the same API call by hand:
```bash
source .env
curl -sS -X POST "$BACKEND_API_BASE/projects" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "name": "${PROJECT_NAME}",
  "local_path": "${PROJECT_LOCAL_PATH}",
  "default_branch": "${PROJECT_DEFAULT_BRANCH}",
  "gitlab_host": "${GITLAB_HOST}",
  "gitlab_project_path": "${GITLAB_PROJECT_PATH}",
  "codex_token": "${CODEX_ACCESS_TOKEN}"
}
JSON
```
If `.env` already describes this project, `quickstart` creates it automatically and `make dev` keeps it in sync. Otherwise, record the `id` from the response (e.g. `export PROJECT_ID=1`) and open `/projects/${PROJECT_ID}` in the UI to review credentials, last activity, and recent task runs from the dedicated detail page.

## Run Your First Task
```bash
: "${TASK_PROMPT:=Quickstart sanity check}"
curl -sS -X POST "$BACKEND_API_BASE/tasks" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "project_id": ${PROJECT_ID},
  "prompt": "${TASK_PROMPT}",
  "allowlist": []
}
JSON
```
Watch the run live in the dashboard. When Docker is available the orchestrator spins up the runner image and streams its output; locally you can dry-run with `RUNNER_GIT_DRY_RUN=1`.
Provide `branch_name` and `codex_model` if you want Codex to work off a specific branch or model; the Tasks view surfaces those fields and the log snapshot API echoes them back for tooling like `scripts/test_docker_path.py`.

## Everyday Commands
- `make dev` – run backend + UI together.
- `make stop` – stop dev servers and compose sidecars.
- `make reset` – remove Codex containers, SQLite state, and sanitized workspaces.
- `python3 scripts/test_docker_path.py --disable-docker` – quick smoke test of the workflow.
- `make threat-scan` – verifies container guardrails and breakout probes.
- `scripts/codex pat store|clear|import-chatgpt` – manage GitLab PATs or Codex session bundles.

## Good To Know
- Tasks route through Tinyproxy with a deny-by-default allowlist. Adjust long-lived domains in `proxy/base_allowlist.conf`; use task-level `allowlist` entries for one-offs.
- The runner bundles the real Codex CLI. Skip installation only if you deliberately set `CODEX_ALLOW_STUB=1`.
- Large build artefacts can bloat sanitized workspaces—prune with `git clean -fdx` or update `.projectsanitize` (legacy `.codexignore`) before long runs.
- Log snapshots (`GET /tasks/{id}/logs?follow=0`) include the task status, branch, Codex model, and whether an abort was requested so operator tooling can annotate history without another API call.
- Use `python3 scripts/migrate_projectsanitize.py [path]` to rename legacy `.codexignore` files; the helper merges entries so sanitized workspaces stay lean.
- Threat model details and hardening expectations live in `THREAT_MODEL.md`.

## Project Map
- `app/` – FastAPI orchestrator and API tests.
- `ui/` – React + Vite client.
- `runner/` – Docker image and runtime scripts (`finish_task.sh`, `codex` bootstrap).
- `proxy/` – Tinyproxy configuration.
- `scripts/` – Automation helpers, including `quickstart.sh` and PAT tooling.
- `workspaces/` – Ephemeral sanitized task directories (ignored by git).

Have fun automating your repos! If something looks off, check the live task log stream, rerun with `--keep-workspace` on `scripts/test_docker_path.py`, and peek into the captured snapshot.
