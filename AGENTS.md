# Repository Guidelines

## Current Status
- Live GitLab run on 2025-09-25 succeeded after pruning build artefacts (see task 7 workspace); branch `codex/task-20250925-27cd19` and the associated GitLab MR remain open for review—see the orchestrator's stored metadata for the project-specific URL.
- Phase 3 (Docker runtime + proxy sidecar) is complete; see `local-codex-mr_todo_prompt.md` for implementation details and verified tests.
- Runner containers now launch via docker-compose with Tinyproxy enforcing deny-by-default egress.
- Orchestrator streams logs from ephemeral containers and honors the sanitized workspace mount at `/work`.
- Phase 4 landed: the runner image now bundles a placeholder `codex` CLI, the orchestrator executes `codex exec --cd /work --skip-git-repo-check --yolo -` inside the sanitized workspace (falls back to the local stub when Docker is disabled), task logs include streamed codex output plus explicit success/failure markers, and the repo ships `scripts/test_docker_path.py`/`make smoke-docker` to exercise Docker runs with custom allowlists, project reuse, and snapshot captures.
- Phase 5 GitLab automation is wired up: `runner/bin/finish_task.sh` stages commits, creates `codex/task-<date>-<shortid>` branches, pushes via merge-request push options (REST/regex fallback), the orchestrator persists branch + MR URLs, the UI collects PATs, and the runner image now includes `git`/`curl` with a `RUNNER_GIT_DRY_RUN=1` shortcut for local tests.
- Phase 6 tightened network controls: `proxy/base_allowlist.conf` seeds a default-deny Tinyproxy filter (overrideable via `PROXY_DIR`) covering GitLab, package registries, and `chatgpt.com` so the live Codex agent can reach its API; per-task domains are normalized/merged and pushed via `filter.list` while the compose-managed proxy restarts to pick up changes, the Docker runner enforces proxy env plus memory/PID/tmpfs guardrails with task log surfacing for OOM/error cases, and the `scripts/test_docker_path.py` helper now self-initializes git so the dry-run Docker path completes end-to-end.
- Phase 7 added a task dashboard, auto-scrolling logs with clipboard support, and disk-backed redacted log storage exposed via `/tasks` and snapshot endpoints so operators retain history across reloads; queue and snapshot checks confirm only one task runs at a time and mid-run snapshots remain a prefix of final logs.
- UI navigation now splits Submit Task, Tasks, Projects, and Settings into dedicated pages so operators can manage credentials and task history without juggling a single long view.
- Projects dashboard now surfaces sortable repository metadata (host, branch, allowlist coverage, credential signals, last Codex activity) and per-row actions for detail, edit, and delete. The `/projects/:id` view summarizes credentials alongside recent task runs so operators can audit before triggering new work.
- Phase 8 codified the threat model, shipped `THREAT_MODEL.md`, and introduced `make threat-scan`, which validates container hardening flags and executes a `/work/../../..` breakout probe that now fails as expected against a host sentinel file.
- Phase 9 packaged the project for newcomers with a README Quickstart, pinned toolchain versions, a `.env.example` template for GitLab/project defaults, and `scripts/quickstart.sh` to bootstrap dependencies, build the runner image, and launch the Tinyproxy sidecar.
- Docker path smoke tests now succeed end-to-end after exporting `DOCKER_HOST=unix:///Users/rashed/.docker/run/docker.sock`; proxy reloads succeed and task logs now report the real Codex release by default (the shim only appears when operators explicitly opt in with `CODEX_ALLOW_STUB=1`).
- Local smoke runs install `chardet` so Requests stops warning about missing charset detection support.
- Phase 10 completed: the runner image now stages the shim alongside a bootstrap installer; the build auto-installs the pinned Codex CLI (or a provided tarball/URL) and fails if the binary is missing, while operators can still disable auto-download for air-gapped tests and acknowledge the shim via `CODEX_ALLOW_STUB=1` at runtime.
- Repository now vendors `codex-x86_64-unknown-linux-gnu.tar.gz` at the project root so default runner builds succeed offline while still verifying the archive checksum.
- Phase 11 delivered PAT lifecycle management: `/integrations/pat` supports store/clear/read with plaintext storage sourced from `.env`, audit logging remains in place, the UI ships a Settings → Integrations card with update + destructive clear flows that gate task submission, pending tasks fail fast when the PAT is cleared, and `scripts/codex` exposes `codex pat store|clear` with dry-run support.
- Phase 12 finalized Codex auth around ChatGPT session bundles: the backend encrypts imported bundles while the GitLab PAT stays plaintext for local deployments, project-scoped API tokens were retired, the runner stages bundles into `~/.codex/auth.json` while clearing the base64 env, stub runs tolerate missing credentials, and the UI + `scripts/codex` expose `pat import-chatgpt|clear-chatgpt` helpers with updated copy.
- Phase 13 hardened credential UX: the Settings card now explains `.env`-backed PAT handling, warns operators when tokens are missing (with docs links), adds a Verify PAT action backed by `/integrations/pat/verify`, and persists last verification status + host metadata for the dashboard.
- Phase 14 refreshed task history: the `/tasks` endpoint now responds with paginated payloads and filters (status/model/branch), the Tasks page layers in loading skeletons plus accessible abort/delete modals, and log snapshots return status/branch/model/abort metadata that both the UI and `scripts/test_docker_path.py` surface downstream.
- Project allowlists moved to the project record: the API and UI now persist normalized domains per project, tasks inherit those entries automatically, and `scripts/test_docker_path.py` manages allowlists via `/projects` instead of per-task payloads.
- Task submission now supports per-run base branch overrides: the backend persists each task's `target_branch`, UI/CLI expose a "Base Branch" selector, and worker logs call out when a run diverges from the project default; the project cache is rewound to the requested branch before sanitization so branch hopping only incurs an incremental fetch/reset.
- Worker now performs a Docker Tinyproxy preflight before each task: `ensure_proxy_stack` autostarts the `codex-egress-proxy` compose service, recreates/attaches the `codex-shared` network, and fails fast with explicit log guidance when the proxy stack is unavailable (stub mode skips the check).
- 2025-09-26 validation: `make dev` + `/healthz` check, `npm --prefix ui run lint`, `python -m compileall app/app app/tests`, `python -m unittest app.tests.test_phase5`, and `make threat-scan` all pass; Phase 9 Quickstart now succeeds offline via `RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --prompt "Add /healthz endpoint" --disable-docker` and the Docker path runs with a placeholder `sk-test` token (`--codex-token`) while emitting branch/MR metadata and capturing `workspaces/snapshots/quickstart-dryrun-<timestamp>`.

### Operator Notes
- Some upstream projects lack a `.projectsanitize` (or legacy `.codexignore`); without manual cleanup the sanitized workspace can balloon to multiple gigabytes and cause `git push` OOM failures. Run `git clean -fdx` (or add a project-specific ignore list) inside the sanitized workspace before starting the runner when dealing with large build artefacts.
- Run `python3 scripts/migrate_projectsanitize.py [path]` to move existing `.codexignore` files forward—the helper merges entries so sanitized workspaces stay small during the transition window.
- Official Codex CLI docs (including `--yolo` semantics and auth commands) live upstream at https://github.com/openai/codex/tree/main/docs; consult `sandbox.md` and `authentication.md` when wiring the real agent.
- Export `DOCKER_HOST=unix:///Users/rashed/.docker/run/docker.sock` (or the appropriate socket) before running Docker-backed tasks so Tinyproxy reloads can reach Docker Desktop; `.env` now includes this default for local smoke tests.
- Provide a Codex access token that begins with `sk-`; the bundled agent exits with `Codex FAIL (exit code 42)` when the token is missing or malformed, and the orchestrator surfaces the failure in task logs.
- Runner launches now abort if the shim binary is detected; set `CODEX_ALLOW_STUB=1` only when you intentionally want the placeholder behaviour (for example, during air-gapped dry runs).
- The runner image now tracks `debian:testing-slim` so the real Codex binary sees glibc ≥ 2.39; if you customize the base image, confirm `codex --version` succeeds before wiring it into production.
- `scripts/quickstart.sh` calls `runner/bin/install_codex_agent.sh`, which auto-installs Codex CLI 0.42.0 (SHA-256 `0b87da1b...b2f8`) unless you override it. Set `CODEX_AGENT_PINNED_VERSION|URL|SHA256` to pin a different release, flip `CODEX_AGENT_AUTO_DOWNLOAD=0` to stay on the shim, or `CODEX_AGENT_FORCE_DOWNLOAD=1` to refresh the cache. Air-gapped builds still accept `CODEX_AGENT_TARBALL` / `CODEX_AGENT_URL` at build time; the archive must contain the `codex-x86_64-unknown-linux-gnu` binary or the build fails. The vendored tarball at the repo root keeps offline installs working by default.
- Use `scripts/codex pat store|clear` to manage GitLab PATs from the shell; pass `BACKEND_API_BASE` to target non-default hosts and `RUNNER_GIT_DRY_RUN=1` to exercise flows without touching the API. The UI now blocks task submission until a PAT is configured and fails queued work whenever the credential is cleared mid-flight.
- Use `scripts/codex pat import-chatgpt|clear-chatgpt` to manage session bundles; both commands honor `RUNNER_GIT_DRY_RUN` and mirror the UI flows for importing, rotating, and revoking ChatGPT sessions.
- `scripts/test_docker_path.py` now seeds a placeholder PAT automatically when `RUNNER_GIT_DRY_RUN=1`; pass `--gitlab-token` to exercise live pushes against a real GitLab project.
- Log snapshots (`GET /tasks/{id}/logs?follow=0`) include status, branch, model, and abort metadata; the Tasks UI and `scripts/test_docker_path.py` surface those fields so operators can audit runs without juggling extra API calls.
- Use the new Verify PAT access button (or POST `/integrations/pat/verify`) after rotating credentials to confirm connectivity; the backend records the host, timestamp, and result without ever returning the secret.
- Ensure `docker compose` (or `docker-compose`) is available for the proxy preflight; the worker will attempt to launch `codex-egress-proxy` automatically, but repeated failures leave tasks in `failed` status until the compose stack and `codex-shared` network are healthy or `RUNNER_DISABLE_DOCKER=1` is set.
- Worker restarts now fail any pending or running tasks that predate the reboot and log the recovery; heavy cache operations acquire a file lock with a configurable timeout via `PROJECT_CACHE_LOCK_TIMEOUT_SECONDS` (default 180 s) so operators should re-run the queue after resolving lock contention.

## Project Structure & Module Organization
- `app/` – FastAPI orchestrator; main entrypoint `app/app/main.py`.
- `ui/` – React + TypeScript Vite client under `ui/src`.
- `scripts/` – Automation helpers; `scripts/dev.sh` launches API and UI together.
- `proxy/` – Tinyproxy configuration consumed by the runner images.
- `runner/` – Container build context and runtime scripts (placeholder `codex`, `finish_task.sh`, Dockerfile updates); keep task assets here.
- `workspaces/` – Git-ignored per-task sandboxes; never commit contents.
- `.projectsanitize` – Deny list consumed by the sanitizer to filter secrets/artifacts when creating task workspaces (legacy `.codexignore` files emit a warning but are still honored for the transition window).

## Build, Test, and Development Commands
- `make dev` – Starts both services via `scripts/dev.sh`; installs UI deps on first run.
- `make api` – Runs the FastAPI server locally on `0.0.0.0:8000` for backend work.
- `make ui` – Boots the Vite dev server with hot reload on `127.0.0.1`.
- `make build` – Compiles Python bytecode and produces a production UI bundle (use Node 22 via `nvm use 22` beforehand).
- `npm --prefix ui run lint` – ESLint pass for the frontend TypeScript sources.
- `python3 -m unittest discover -s app/tests` – Execute backend regression tests.

## Coding Style & Naming Conventions
- Honor `.editorconfig`: LF endings, final newline, 2-space indent except 4 for Python files.
- Python: follow PEP 8, prefer `snake_case` for functions, `PascalCase` for classes, and extend `app/main.py` via FastAPI routers.
- TypeScript: colocate components in `ui/src`, prefer functional React components, name files `PascalCase.tsx` for components and `camelCase.ts` for utilities.
- Run ESLint before pushing; add future formatters alongside this config rather than overriding it.
- When persisting timestamps, prefer timezone-aware UTC values (e.g., `datetime.now(timezone.utc)`).

## Testing Guidelines
- Add backend tests in `app/tests/` using `unittest` + `fastapi.testclient.TestClient` to cover API routes and SQLModel interactions; isolate DBs with `APP_DATABASE_URL` overrides per test.
- Frontend tests should live in `ui/src/__tests__/` using Vitest + Testing Library; wire them into `package.json` when introduced.
- Target coverage of task execution flows and proxy interactions; document known gaps in pull requests.
- SQLModel emits metadata warnings if models are imported multiple times; clear `SQLModel.metadata` in test fixtures when reloading modules.
- When exercising GitLab flows locally, export `RUNNER_GIT_DRY_RUN=1` to skip remote pushes while still exercising `finish_task.sh` and MR persistence.

## Commit & Pull Request Guidelines
- The workspace lacks shared git history; adopt Conventional Commits (`feat:`, `fix:`, `chore:`) to ease future automation.
- Keep commits scoped to a single concern with passing tests or lint output included in the diff description.
- Pull requests must describe the change, include reproduction steps or screenshots for UI work, reference related issues, and flag breaking runner changes.
- Request review from both backend and frontend owners when touching cross-cutting code.
