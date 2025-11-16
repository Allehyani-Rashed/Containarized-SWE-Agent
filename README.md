# Containerized AI Agent Runner

A local-first playground for AI coding agents: give it a prompt, it sanitizes your repo, executes inside Docker with a locked-down proxy, and prepares a GitLab merge request. Supports both **Codex CLI** and **Claude Code**.

## What You Get
- **Dual AI Agent Support**: Choose between Codex CLI or Claude Code for each task
- FastAPI backend that schedules/namespaces each task
- React dashboard with agent/model selection and live log streaming
- Docker runner image with Tinyproxy enforcing deny-by-default egress
- Helper scripts for PAT management, smoke tests, and threat scans

## Supported AI Agents

### **Codex CLI** (OpenAI)
- Authentication: API token or ChatGPT session bundle
- Use for OpenAI-powered coding tasks

### **Claude Code** (Anthropic)
- Authentication: Claude subscription session or ANTHROPIC_API_KEY
- Models: **Sonnet 4.5** (best performance) or **Haiku 4.5** (faster, cost-efficient)
- Use for Anthropic-powered coding tasks

## Before You Start
- Docker Engine ≥ 26 with Compose v2.24
- Python 3.11.x, Node.js 22.x, npm 10.x, Git ≥ 2.44
- A `.env` file based on `.env.example` with your GitLab project path, PAT, and agent credentials:
  - **For Codex**: `CODEX_ACCESS_TOKEN` or ChatGPT session bundle
  - **For Claude Code**: `ANTHROPIC_API_KEY` or Claude session bundle from `~/.claude/auth.json`
  - `DOCKER_HOST` socket path

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
   This builds the Docker runner (always forcing a fresh `local-codex-runner:latest` image), installs backend/frontend dependencies, starts the Tinyproxy sidecar, and writes credentials from `.env` into the local database (PAT, Codex token, and optional ChatGPT session bundle). Stale virtualenvs are rebuilt automatically if your Python path changes.
3. Start the app servers:
   ```bash
   source .venv/bin/activate
   make dev  # FastAPI on :8000, Vite UI on :5173 (re-syncs credentials from .env)
   ```
4. Open the dashboard at <http://127.0.0.1:5173> (leave `make dev` running).

## Register a Project
You can use the UI Settings panel or run the same API call by hand:
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
  "gitlab_token": "${GITLAB_PAT}",
  "codex_token": "${CODEX_ACCESS_TOKEN}"
}
JSON
```
If `.env` already describes this project, `quickstart` creates it automatically and `make dev` keeps it in sync. Otherwise, record the `id` from the response (e.g. `export PROJECT_ID=1`).

## Run Your First Task

### Using the UI
1. Open the dashboard at <http://127.0.0.1:5173>
2. Select your project
3. Choose an agent: **Codex CLI** or **Claude Code**
4. For Claude Code, select a model: **Sonnet 4.5** or **Haiku 4.5**
5. Enter your prompt and submit

### Using the API

**With Codex CLI:**
```bash
: "${TASK_PROMPT:=Quickstart sanity check}"
curl -sS -X POST "$BACKEND_API_BASE/tasks" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "project_id": ${PROJECT_ID},
  "prompt": "${TASK_PROMPT}",
  "agent_type": "codex",
  "allowlist": []
}
JSON
```

**With Claude Code (Sonnet 4.5):**
```bash
: "${TASK_PROMPT:=Quickstart sanity check}"
curl -sS -X POST "$BACKEND_API_BASE/tasks" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "project_id": ${PROJECT_ID},
  "prompt": "${TASK_PROMPT}",
  "agent_type": "claude-code",
  "model": "sonnet",
  "allowlist": []
}
JSON
```

**With Claude Code (Haiku 4.5):**
```bash
: "${TASK_PROMPT:=Quickstart sanity check}"
curl -sS -X POST "$BACKEND_API_BASE/tasks" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "project_id": ${PROJECT_ID},
  "prompt": "${TASK_PROMPT}",
  "agent_type": "claude-code",
  "model": "haiku",
  "allowlist": []
}
JSON
```

Watch the run live in the dashboard. When Docker is available the orchestrator spins up the runner image and streams its output; locally you can dry-run with `RUNNER_GIT_DRY_RUN=1`.

## Everyday Commands
- `make dev` – run backend + UI together.
- `make stop` – stop dev servers and compose sidecars.
- `make reset` – remove Codex containers, SQLite state, sanitized workspaces, and the cached `local-codex-runner:latest` image so the next quickstart rebuilds the runner.
- `python3 scripts/test_docker_path.py --disable-docker` – quick smoke test of the workflow.
- `make threat-scan` – verifies container guardrails and breakout probes.
- `scripts/codex pat store|clear|import-chatgpt` – manage GitLab PATs or Codex session bundles.
- The backend re-syncs `.env` credentials on startup. Override the env file via `APP_ENV_FILE=/path/to/.env` or disable auto sync with `APP_ENV_SYNC_DISABLE=1`.

## Good To Know
- **Agent Selection**: Tasks default to `codex` if no `agent_type` is specified. The UI provides dropdowns for easy selection.
- **Claude Code Models**:
  - **Sonnet 4.5** (`claude-sonnet-4-5-20250929`): Best coding performance, strongest for complex agents
  - **Haiku 4.5** (`claude-haiku-4-5-20251001`): Faster execution, 1/3 the cost, near-frontier performance
- **Authentication**:
  - Codex: API token or ChatGPT session bundle
  - Claude Code: Claude subscription session (recommended) or ANTHROPIC_API_KEY
- Tasks route through Tinyproxy with a deny-by-default allowlist. Adjust long-lived domains in `proxy/base_allowlist.conf`; use task-level `allowlist` entries for one-offs.
- The runner bundles both Codex CLI and Claude Code. Skip Codex installation only if you deliberately set `CODEX_ALLOW_STUB=1`.
- Large build artefacts can bloat sanitized workspaces—prune with `git clean -fdx` or update `.codexignore` before long runs.
- Threat model details and hardening expectations live in `THREAT_MODEL.md`.

## Project Map
- `app/` – FastAPI orchestrator and API tests
- `ui/` – React + Vite client with agent/model selection
- `runner/` – Docker image and runtime scripts for both Codex and Claude Code
  - `launch_codex.sh` – Codex CLI launcher
  - `launch_claude_code.sh` – Claude Code launcher
  - `install_codex_agent.sh` – Codex CLI installer
  - `install_claude_code.sh` – Claude Code installer (via npm)
  - `finish_task.sh` – Git/GitLab automation
- `proxy/` – Tinyproxy configuration
- `scripts/` – Automation helpers, including `quickstart.sh` and PAT tooling
- `workspaces/` – Ephemeral sanitized task directories (ignored by git)

Have fun automating your repos! If something looks off, check the live task log stream, rerun with `--keep-workspace` on `scripts/test_docker_path.py`, and peek into the captured snapshot.
