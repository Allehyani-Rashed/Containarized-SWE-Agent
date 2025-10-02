# Phase 0 Baseline – UI/UX Initiative

## UI Flow Audit (`ui/src/App.tsx`)
- Single-page layout renders projects, task submission, task list, log viewer, and credential management in one component without routing; state is lifted into top-level hooks.
- Project creation form defaults `default_branch` to `main`, `gitlab_host` to `https://gitlab.com`, and expects allowlist input as newline-separated paths per the sanitizer workflow.
- Task submission relies on the selected project id, prompt textarea, and allowlist textarea; branch/model selection is absent, and allowlist normalization happens server-side.
- Task list renders newest-first via `orderTasks`; branch, MR URL, workspace path, Codex agent metadata, and credential status surface in detail modals but there is no filtering, pagination, or abort/delete controls yet.
- Credential management card drives PAT rotation, verification, and ChatGPT session import flows using `/integrations/pat` endpoints with optimistic UI state and modal confirmations.

## Backend DTO & API Audit (`app/app/schemas.py`, `app/app/main.py`)
- `ProjectCreate` persists project metadata only; Codex authentication now depends exclusively on ChatGPT session bundles managed through the integrations APIs.
- `TaskCreate` exposes `project_id`, `prompt`, `allowlist` only; the backend currently derives branch names internally and never captures a Codex model id.
- `TaskRead` includes branch, MR URL, workspace path, Codex agent metadata, but these fields are read-only.
- `GET /tasks` (not shown above) returns ordered tasks, while `POST /tasks` persists new tasks and enqueues them with `TaskQueueManager`.
- Worker `_process_task` pulls the project default branch as the target, synthesizes a task branch via `_generate_branch_name`, and calls `run_codex` with Codex/PAT credentials plus sanitized allowlists; there is no hook for operator-provided branch/model inputs yet.

## Task Schema Gaps & Observations
- No persistence for user-specified branch names or Codex model selection despite downstream task metadata fields.
- Allowlist is stored as JSON array but UI sends newline-delimited strings; validation lives in `allowlist.normalize_user_allowlist`, so changes to UI inputs must stay compatible.
- Credential errors (PAT, Codex token, ChatGPT session) fail tasks early; UI lacks surfaced reasons beyond log streaming, informing acceptance criteria for lifecycle and error UX improvements.

## Credential UX Guardrails (Phases 11–13 Reference)
- PAT storage is write-only with audit logging; verification endpoint records status, host, and timestamp without returning secrets.
- ChatGPT session bundles serve as fallback credentials; runner mounts bundles into `~/.codex/auth.json` and clears the base64 environment variables after use.
- UI tasks are gated on a configured PAT; queued tasks fail fast if the PAT is cleared while pending.
- Settings card must continue surfacing verification status, active credential (session vs missing), and destructive-clear flows with modal confirmations.

## Sanitizer Filename Decision
- Stakeholders (operations, security, runner maintainers) agree to rename `.codexignore` to `.projectsanitize` for clarity with sanitized workspaces.
- Backwards compatibility window: the sanitizer will continue honoring `.codexignore` for two minor releases after the rename (target removal no earlier than 2026-01-31) while emitting deprecation warnings.
- Documentation, quickstart scripts, and threat model updates must land alongside the rename to avoid inconsistent operator guidance.

## Acceptance Criteria for Upcoming Phases
- **Navigation & Layout (Phase 1):** Introduce React Router with an `AppShell` framing persistent navigation, responsive layout behavior (sidebar on desktop, top nav on mobile), and ensure `/` routes to the task submission page without breaking FastAPI static serving or `/healthz` checks.
- **Task Submission Revamp (Phase 2):** Deliver a dedicated submission card supporting prompt, allowlist, branch name, and model selection backed by new backend fields plus migrations and runner environment propagation.
- **Task Lifecycle Controls (Phase 3):** Provide task detail drawer/page with abort/delete actions, SSE log handling for abort markers, new backend endpoints (`/tasks/{id}/abort`, DELETE `/tasks/{id}`), and worker support for `TaskStatus.aborted`.
- Acceptance criteria extend to documentation refreshes (README, AGENTS, operator notes) whenever functionality shifts, ensuring parity between UI behavior and operational runbooks.

## Baseline Regression Runs
- To preserve current behavior as a benchmark for future phases, run: `make dev`, `npm --prefix ui run lint`, `python -m unittest app.tests.test_phase5`, `make threat-scan`, and `scripts/test_docker_path.py --prompt "noop" --disable-docker`. Recorded results live in the Phase 0 execution log for traceability.
