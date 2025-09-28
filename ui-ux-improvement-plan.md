# UI/UX Improvement Plan

## Phase 0 – Alignment & Guardrails
- [x] Audit `ui/src/App.tsx` and backend DTOs (`app/app/schemas.py`, `app/app/main.py`) to confirm current flows, default branch logic, and task schema gaps; capture constraints documented through Phase 13 credential UX (see `ui-ux-phase0-baseline.md`).
- [x] Stakeholder sign-off on new sanitized file name `.projectsanitize` (keeps intent clear); decide on interim backwards compatibility window (documented in `ui-ux-phase0-baseline.md`).
- [x] Document acceptance criteria covering multipage navigation, task submission bundle (prompt + branch + model), abort/delete semantics, project CRUD, and credential surfaces to ensure development stays aligned with operating requirements (recorded in `ui-ux-phase0-baseline.md`).
- [x] Snapshot baseline behaviour by running `make dev`, `npm --prefix ui run lint`, `python -m unittest app.tests.test_phase5`, `make threat-scan`, and `scripts/test_docker_path.py --prompt "noop" --disable-docker`; commands executed (Python invocations used `python3` and `python3 scripts/test_docker_path.py` due to environment defaults).

## Phase 1 – Navigation & Layout Scaffold
- [x] Introduce React Router in `ui/src/main.tsx`; split the monolithic `App.tsx` into an `AppShell` layout with persistent navigation and routed pages (`TaskSubmitPage`, `TaskListPage`, `ProjectsPage`, `SettingsPage`).
- [x] Implement responsive navigation (sidebar for desktop, top nav for narrow viewports) using the existing CSS tokens; ensure `/` defaults to the Task submission route.
- [x] Extract current fetch logic into shared services under `ui/src/api/` before splitting pages to avoid regression when components remount.
- [x] Verify FastAPI static serving still delivers the SPA entry point; confirm `/healthz` remains unaffected. *(Validated via `make dev` smoke run; backend served `/tasks` and `/integrations/pat` during startup.)*
- [x] Update documentation references that describe the UI as a single page (README, AGENTS) so they match the new layout baseline.
- [x] Regression check: `npm --prefix ui run lint` and a `make dev` smoke run to validate client-side routing. *(Lint passes; `make dev` launched API + Vite and was terminated after confirming healthy responses.)*

## Phase 2 – Task Submission Revamp
- [x] Build a dedicated `TaskSubmissionCard` that groups prompt, allowlist, new branch-name input, and Codex model selector (initial options sourced from a backend `/models` endpoint or a vetted static list).
- [x] Extend `TaskCreate` in `app/app/schemas.py` with optional `branch_name` and `codex_model`; add nullable columns to `Task` in `app/app/models.py`.
- [x] Implement an idempotent startup migration (e.g., in `app/app/database.py`) that `ALTER TABLE task ADD COLUMN` only when missing, preserving existing deployments.
- [x] Update `/tasks` POST handler in `app/app/main.py` to persist `branch` and `codex_model`, including validation (branch hygiene, known model ids) and clearer error responses.
- [x] Honor provided branch/model during execution: update `TaskQueueManager._process_task` to use `task.branch` when set, enrich logging, and pass the selected model to `run_codex` so runner env exposes `CODEX_MODEL_ID`.
- [x] Adjust runner scripts (`runner/bin/launch_codex.sh`, `finish_task.sh`) to consume `CODEX_MODEL_ID` without breaking current flows when unset.
- [x] Surface branch/model metadata in task listings and detail views.
- [x] Regression check: extend backend tests (clone `app.tests.test_phase5` coverage for new fields) and run `scripts/test_docker_path.py --prompt "test" --codex-token sk-test --branch custom --codex-model gpt-4o-mini`. *(Backend suite added `app/tests/test_phase2_submission.py`; Docker-path command fails with the placeholder token because the real Codex CLI cannot authenticate against OpenAI, but the stub path via `--disable-docker` succeeded and confirmed branch/model propagation.)*

## Phase 3 – Task Lifecycle Controls
- [x] Create a task detail drawer/page showing status, logs, branch, model, and add `Abort` (pending/running) plus `Delete` (completed/failed) actions with confirmation modals. *(Implemented drawer overlay with action buttons, confirmations, and log copy controls.)*
- [x] Backend: add `/tasks/{id}/abort` to set an abort flag the worker respects prior to launching Codex and while streaming logs. *(Added API endpoint, worker abort signaling, and audit logging.)*
- [x] Add `TaskStatus.aborted`; ensure worker transitions tasks accordingly, stops streaming, and persists outcome. *(Worker now tracks abort signals, surfaces SSE `aborted`, and marks terminal events.)*
- [x] Provide `/tasks/{id}` DELETE that removes task metadata, log snapshots, and sanitized workspaces while respecting guardrails in `workspaces/`. *(API removes DB record, sanitized workspace, and log files via worker helpers.)*
- [x] Update SSE log handling to close gracefully on abort/delete, broadcasting explicit markers to the UI. *(SSE now emits `aborted`/`deleted` events consumed by the drawer.)*
- [x] Expand tests to cover abort/delete plus proxy-preflight skip scenarios; verify audit logging where applicable. *(New `app/tests/test_phase3_task_controls.py` exercises pending/running aborts, deletion, and audit entries.)*
- [x] Regression check: full unit suite and `make threat-scan` to confirm container guardrails stay intact. *(Executed `python3 -m unittest discover -s app/tests` and `make threat-scan`.)*

## Phase 4 – Project Management Overhaul
- [x] Build `ProjectsPage` with a sortable overview (repository URL, host, default branch, allowlist status, credential indicators, last activity) and action menu per project. *(Table now supports keyboard-accessible sorting, inline credential badges, and per-row View/Edit/Delete actions with branch/host validation feedback.)*
- [x] Introduce `/projects/:id` detail page summarizing configuration, recent tasks, and credential state drawn from PAT/session APIs. *(Detail view links back to Projects and Tasks, surfaces codex/PAT status, and lists recent runs with status badges.)*
- [x] Implement Add/Edit forms reusing backend DTOs; add PATCH `/projects/{id}` and DELETE endpoints with validation (block deletion if tasks running or document cascade behaviour). *(Backend now exposes `/projects/{id}` GET/PATCH/DELETE`, serves derived metrics, enforces branch/model validation, and records audit events. New `app/tests/test_projects_crud.py` covers CRUD behaviour.)*
- [x] Wire UI to use SWR-like caching so project updates propagate consistently; include inline validation for branch and host fields. *(Shared `ProjectsProvider` powers Submit, Tasks, Projects, and Detail pages; forms validate host/branch immediately and share success/error state.)*
- [x] Update README Quickstart and AGENTS operator notes to describe the richer project experience. *(Docs mention sortable dashboard, per-project detail view, and updated registration workflow.)*
- [x] Regression check: `npm --prefix ui run lint`, targeted Vitest suites (if added), plus smoke tests for project CRUD. *(Executed `npm --prefix ui run lint` and `python3 -m unittest app.tests.test_projects_crud`.)*

## Phase 5 – `.projectsanitize` Rename & Compatibility
- [x] Rename repository root `.codexignore` to `.projectsanitize`; update `app/app/sanitizer.py` to prefer `.projectsanitize` while logging a deprecation warning when falling back to `.codexignore`. *(Root `.projectsanitize` is tracked, `app/app/sanitizer.py` warns on legacy fallback, and `app/tests/test_sanitizer_files.py` covers both paths.)*
- [x] Replace references across docs (`README.md`, `AGENTS.md`, `local-codex-mr_todo_prompt.md`, `THREAT_MODEL.md`) and scripts (including `scripts/test_docker_path.py` and runner installers) to default to `.projectsanitize`. *(Docs and helpers call out `.projectsanitize` as the default denylist, with legacy `.codexignore` only noted as fallback; the Docker smoke helper seeds a `.projectsanitize` sample project.)*
- [x] Update packaging/build tooling (Dockerfile, compose mounts, quickstart script) to seed `.projectsanitize` in new workspaces. *(Runner builds now stage the template via `runner/Dockerfile`, the Tinyproxy compose stack exposes it read-only, and `scripts/quickstart.sh` creates the denylist when missing.)*
- [x] Provide a helper migration script or guide instructing operators to rename their sanitizer files; highlight impact on sanitized workspace size. *(`scripts/migrate_projectsanitize.py` offers dry-run/force paths and docs flag the workspace bloat risks.)*
- [x] Adjust `.gitignore` and any CI configs to cover the new filename. *(`.gitignore` now keeps `.projectsanitize` under version control alongside workspace ignores.)*
- [x] Regression check: dry-run and Docker smoke tests ensuring sanitizer picks up the new name and falls back cleanly when the old file exists. *(Executed `python3 -m unittest app.tests.test_sanitizer_files`, `RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --prompt "Phase5 dry-run post-update" --disable-docker --branch phase5-dry2 --codex-model gpt-4o-mini`, and `DOCKER_HOST=unix:///Users/rashed/.docker/run/docker.sock RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --prompt "Phase5 docker post-update" --codex-token sk-test --codex-model gpt-4o-mini --branch phase5-docker2 --expect-auth-failure`.)*

## Phase 6 – Polish, Telemetry & Documentation
- [x] Add filters/search to the task list (status/model/branch) and ensure pagination-ready data handling. *(Backend `/tasks` accepts status/model/branch filters with limit/offset metadata; UI wires filters with pagination-aware polling and new tests live in `app/tests/test_task_filters.py`.)*
- [x] Improve empty states, loading skeletons, and accessibility (ARIA labels, focus traps in modals) across new pages. *(Tasks table shows skeleton rows, filter summaries, and abort/delete confirmations now use a focus trap + labelled alertdialog markup.)*
- [x] Update snapshot/history APIs and UI to include model/branch/abort metadata while preserving prefix guarantees for in-progress logs. *(`TaskLogSnapshot` schema, the Tasks drawer, and `scripts/test_docker_path.py` all surface branch/model/abort details without altering log ordering.)*
- [x] Refresh documentation (README, AGENTS, Threat Model, operator scripts) with multipage navigation, abort/delete behaviour, and `.projectsanitize` usage. *(README, AGENTS, and THREAT_MODEL gained notes on filters, snapshot metadata, and `.projectsanitize`; CLI helper output description updated.)*
- [x] Final regression suite: `make dev`, `npm --prefix ui run lint`, `python -m compileall app/app app/tests`, `python -m unittest app.tests`, `make smoke-docker`, `make threat-scan`. *(Executed all commands; `make dev` run was started and shut down after launch, lint/tests/smoke/threat scans passed.)*
- [x] Draft release notes and migration checklist covering branch/model inputs, abort/delete controls, project CRUD, and sanitizer rename. *(See `docs/ui-phase6-release-notes.md` for highlights and operator checklist.)*
