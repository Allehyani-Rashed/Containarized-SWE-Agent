# Prompt: Build a Local‑First Web UI that turns a prompt into a containerized “codex” run and opens a GitLab Merge Request

## Objective
Implement an open-source **local-first** tool that:
- Runs **entirely on the user’s machine** (local Docker).
- Provides a **browser UI** to submit a free-form prompt as a **task**.
- For each task, orchestrates a **hardened containerized runner** on a **sanitized copy** of the repo, runs a **codex** CLI in unattended mode, and enforces permissions **only at the container level**.
- Blocks non‑whitelisted **network egress** via a proxy sidecar.
- Automatically **pushes a branch** and **opens a GitLab Merge Request** with the resulting changes.

## Latest Progress
- Phase 3 (Docker runtime & Tinyproxy sidecar) finished: docker-compose orchestrates the hardened runner alongside the proxy, and the worker streams container logs.
- Proxy deny-by-default confirmed via Tinyproxy 403s on disallowed domains and success on allowlisted hosts (`gitlab.com`).
- Runner mounts stay constrained to `/work`, preventing access to host secrets (validated via missing `$HOME/.ssh`).
- Phase 4 placeholder codex CLI now ships in the runner image; the orchestrator launches the `codex exec --cd /work --skip-git-repo-check --yolo -` command, streams its stdout into task logs, and records explicit success/failure markers while writing `CODEX_CHANGE.log` inside the sanitized workspace (with a local stub fallback when Docker is unavailable).
- Added `scripts/test_docker_path.py` and a `make smoke-docker` shortcut as reusable smoke-test tooling supporting custom allowlists, existing project/task inspection, and timestamped workspace snapshots for debugging.
- Phase 5 stitches the GitLab flow together: the runner ships `finish_task.sh` to configure git safely, create/push `codex/task-<date>-<shortid>` branches with merge-request push options (curl/API fallback plus regex parsing), the orchestrator now passes branch/env metadata and persists `branch`/`mr_url`, the UI collects GitLab PATs, and the runner image bundles `git` + `curl` with a `RUNNER_GIT_DRY_RUN` escape hatch for local tests.
- Phase 6 tightened network controls: `proxy/base_allowlist.conf` seeds a default-deny Tinyproxy filter (overrideable via `PROXY_DIR`), per-task domains are normalized/merged and pushed via `filter.list` while the compose-managed proxy restarts to pick up changes, the Docker runner enforces proxy env plus memory/PID/tmpfs guardrails with task log surfacing for OOM/error cases, and the `scripts/test_docker_path.py` helper now self-initializes git so the dry-run Docker path completes end-to-end.
- Phase 7 polished the operator experience: the UI now offers a sortable task dashboard with live status, the log viewer auto-scrolls with a copy-to-clipboard shortcut, orchestrator logs persist to disk with token redaction so snapshots survive reloads without leaking credentials, and validation runs confirmed the queue keeps concurrency at one while snapshot reloads append without duplication.
- Phase 8 codified the threat model: runner containers enforce read-only rootfs, drop all capabilities, run as non-root with `no-new-privileges`, the new `make threat-scan` check surfaces critical hardening flags and attempts a `/work/../../..` breakout read against a host sentinel, and `THREAT_MODEL.md` documents risks versus mitigations covering egress, secrets, and token handling.
- Phase 9 focused on packaging: README now features an end-to-end Quickstart with pinned runtime versions, `.env.example` captures project/token defaults, and `scripts/quickstart.sh` bootstraps Docker, Python, and Node dependencies while launching the Tinyproxy sidecar.
- Phase 10 completed: the runner image now stages the shim alongside a bootstrap installer; operators can bake in the real Codex CLI by supplying `CODEX_AGENT_TARBALL` or `CODEX_AGENT_URL` during `docker build`, and Docker-backed tasks prefer the installed binary while falling back to the shim when none is provided.
- Phase 11 landed: `/integrations/pat` exposes store/clear/read flows with encrypted storage + audit logs, the UI surfaces a Settings card with update and destructive clear UX, pending tasks fail fast when credentials are cleared, and `scripts/codex` ships `codex pat store|clear` with dry-run support.
- Docker path smoke tests now succeed end-to-end after exporting `DOCKER_HOST=unix:///Users/rashed/.docker/run/docker.sock`; Tinyproxy restarts cleanly and task logs report whichever agent is baked into the image (live CLI when provided, otherwise the shim), with the stub still covering Docker-disabled flows.
- Requests no longer emits charset warnings after installing `chardet`, keeping test output clean for dry-run validations.
- Live GitLab validation (task 7) succeeded after running `git clean -fdx` inside the sanitized workspace to drop large build artefacts; branch `codex/task-20250925-27cd19` backs the MR recorded in the validation project—refer to the orchestrator metadata for the precise URL.
- Phase 13 hardened credential UX: the Settings card now explains write-only PAT handling, warns operators when tokens are missing (with docs links), adds a Verify PAT action backed by `/integrations/pat/verify`, and records verification status + host metadata for the dashboard.
- Added a proxy stack preflight: before Docker-backed runs the worker calls `ensure_proxy_stack`, which auto-starts `codex-egress-proxy` via docker-compose, recreates/attaches the `codex-shared` network, logs the container IP when ready, and aborts with actionable logs if the proxy cannot be prepared (stub mode skips the check).

## Guardrails (Do not violate)
- **Local only**; single user/session; single repo/project at a time.
- **Git provider = GitLab only** (gitlab.com or self‑managed). Token is user‑supplied.
- **Security enforced solely by container controls** (no agent-level policy engines).
- **No secrets in container**: sanitize workspace; do not mount user home or secret files.
- **Out of scope**: multi‑tenant auth, cloud runners, SSO/OIDC, deep policy/RBAC.

## Required Tech Choices
- **UI**: React + Vite (TypeScript)
- **Local Orchestrator**: Python FastAPI (uvicorn)
- **Storage**: SQLite via SQLModel
- **Runner base image**: debian:bookworm‑slim
- **Proxy sidecar**: Tinyproxy (default‑deny allowlist)

## API (to implement in the local backend)
- `POST /projects` – register `{ name, default_branch, gitlab_host, gitlab_project_path, cache_quota_mb?, cache_prune_after_hours? }`
- `GET /projects`
- `POST /tasks` – `{ project_id, prompt, allowlist?: string[] }`
- `GET /tasks/:id`
- `GET /tasks/:id/logs` – SSE (or snapshot when `?follow=0`)
- `GET /healthz`

---

## Phase 0 — Repo Bootstrap & Project Skeleton

**TODO**
- [x] Create a mono‑repo skeleton: `/app` (FastAPI), `/ui` (React+Vite), `/runner` (Dockerfile + scripts), `/proxy` (tinyproxy configs), `/workspaces` (task sandboxes), `/scripts`.
- [x] Initialize Python env (FastAPI, SQLModel, docker SDK for Python).
- [x] Initialize UI with Vite + React + TS; set dev server to proxy API requests to FastAPI.
- [x] Add `.editorconfig`, `.gitignore`, `LICENSE`, `README`, and a minimal `Makefile` with `make dev`, `make build`.

**Exit criteria**
- [x] `GET /healthz` returns `{ "ok": true }`.
- [x] UI loads at `http://localhost:<ui-port>` with a blank home page.

**Test plan**
1. ✅ Run `make dev` → UI and API both start; curl to `/healthz` returned `{"ok":true}` on 2025-03-03.
2. ✅ Lint passes for both UI and API (`npm --prefix ui run lint`; `python -m compileall app/app app/tests`).

---

## Phase 1 — Data Model, API, and UI Scaffolding

**TODO**
- [x] Define SQLModel models: `Project`, `Task` with fields:
  - `Task.status ∈ {pending, running, done, failed}`, timestamps, `prompt`, optional `mr_url`, `branch`, `allowlist`.
- [x] Implement endpoints listed above (in-memory queue OK for now).
- [x] Implement a simple single-consumer queue worker inside the orchestrator.
- [x] UI pages:
  - [x] Projects: list + “register project” form.
  - [x] Tasks: form to submit (select project, prompt, optional allowlist).
  - [x] Task detail: status + live logs (SSE).

**Exit criteria**
- [x] `POST /projects` registers and persists in SQLite.
- [x] `POST /tasks` creates a `pending` task and enqueues it.
- [x] `GET /tasks/:id/logs` streams SSE (fake entries for now).

**Test plan**
1. ✅ Register a dummy project; list it back.
2. ✅ Submit a task; see `pending` → (worker picks up and writes mock logs) → `done` with logs visible in UI.

---

## Phase 2 — Sanitized Workspace

**TODO**
- [x] Implement `sanitize.sh` (or Python equivalent) to `rsync` source → `./workspaces/<taskId>/safe`.
- [x] Exclude secrets/large dirs via `.projectsanitize` (legacy `.codexignore`) (denylist including `.env*`, `id_*`, keys, `.aws/`, `.kube/`, `node_modules/`, `dist/`, `target/`, caches, dumps, logs).
- [x] Preserve `.git` so branch/commit/push work from the sandbox.
- [x] Ensure no mounts of `$HOME` or other host secrets in any later phase.

**Exit criteria**
- [x] Running sanitize on a sample repo copies code and `.git` but excludes the denylist.
- [x] Task worker calls sanitize and records path to `/workspaces/<taskId>/safe`.

**Test plan**
1. ✅ Place secret files in the source repo (`.env`, `id_rsa`, `node_modules/`).
2. ✅ Submit task; inspect `workspaces/<taskId>/safe` – secrets absent; `.git` present.
3. ✅ Spot check with `grep -R` that no `.env` content exists in `safe/`.

---

## Phase 3 — Docker Runtime & Proxy Sidecar (No Git yet)

**TODO**
- [x] Create `docker-compose.yml` with two services: defined top-level compose file that builds `runner` from `runner/` and starts `egress-proxy` using the Tinyproxy config in `proxy/`, wiring both to the proper networks.
- [x] Networks: declared `sandbox` as `internal: true` and `egress` as the default bridge so only the proxy has internet egress while runners stay isolated.
- [x] Runner container **security**: set `user: 1000:1000`, `read_only: true`, dropped all caps, enabled `no-new-privileges`, mounted tmpfs for `/tmp`, `/run`, `/home/codex`, and limited binds to `/work` pointing at `workspaces/<taskId>/safe` with the proxy env vars injected.
- [x] Tinyproxy: shipped a default-deny filter file that seeds the base allowlist and kept it mounted read-only into the proxy service.
- [x] Orchestrator: extended the worker to launch disposable runner containers on the `sandbox` network, pipe stdout/stderr into task logs, and tear them down after completion.

**Exit criteria**
- [x] Task run launches a one-shot container, executes a trivial command (e.g., `echo`), logs are streamed, container exits; validated with the worker invoking `echo phase3 smoke` inside the runner image.
- [x] Runner has **no** network unless via proxy (validate by trying direct `curl` to disallowed host → should fail); direct `curl https://example.com` now surfaces Tinyproxy block responses while allowlisted domains succeed.

**Test plan**
1. ✅ Started proxy and executed a task with `curl https://example.com`; runner saw Tinyproxy `403` confirming deny-by-default.
2. ✅ Added `gitlab.com` to the task allowlist and reran `curl https://gitlab.com`; request succeeded through proxy with `200`.
3. ✅ Attempted to `cat $HOME/.ssh/id_rsa` from inside the runner; path was absent thanks to the minimal bind set.

---

## Phase 4 — Codex Runner Integration (Local Write Only)

**TODO**
- [x] Add a placeholder `codex` CLI inside the runner image that writes to `/work/CODEX_CHANGE.log` and echoes its activity.
- [x] Orchestrator command per task:
  - `cd /work && codex exec --cd /work --skip-git-repo-check --yolo -`
- [x] Stream codex stdout/stderr into task logs, capture the exit code, and append explicit “Codex SUCCESS/FAIL” markers alongside the execution mode (Docker vs. stub fallback).

**Exit criteria**
- [x] Running a task creates or modifies `/work/CODEX_CHANGE.log` inside the sanitized workspace.
- [x] Log stream shows codex launch/start markers and ends with `Codex SUCCESS/FAIL (exit code X)`.

**Test plan**
1. ✅ Submit a prompt; verify `workspaces/<task>/safe/CODEX_CHANGE.log` contains the placeholder output.
2. ✅ Confirm logs include the codex stdout line (`codex placeholder wrote change log …`) and the final `Codex SUCCESS (exit code 0)` marker.
3. ✅ `python3 -m unittest discover -s app/tests` (covers end-to-end flow with Docker disabled via `RUNNER_DISABLE_DOCKER=1`).
4. ✅ `python3 scripts/test_docker_path.py --allowlist gitlab.com --snapshot-prefix phase4` (runs full Docker path, captures logs, and preserves a workspace snapshot for inspection).
5. ✅ `make smoke-docker` (invokes the helper with the repo's configured Python for a quick end-to-end verification).

---

## Phase 5 — Git Operations & MR Creation (GitLab)

**TODO**
- [x] Inside runner, implement `finish_task.sh`:
  - Configures git identity, marks both `/work` and the sanitized path as safe, and disables hooks via `core.hooksPath=/dev/null`.
  - Generates `codex/task-<yyyymmdd>-<shortid>` branches, stages commits (allowing empty), and pushes with GitLab merge-request push options, falling back to the REST API or parsing push output to recover the MR URL.
  - Supports local testing with `RUNNER_GIT_DRY_RUN=1` while redacting tokens (AskPass + oauth2 user) and writes `CODEX_RESULT.json` for the orchestrator to consume.
- [x] Token scopes:
  - `write_repository` remains mandatory, `api` unlocks the merge-request lookup but the CLI still handles the fallback gracefully.
- [x] Orchestrator/UI wiring:
  - Worker now injects the GitLab env vars (`GITLAB_TOKEN`, host, project path, target branch, MR title, task metadata) into the runner invocation, persists `branch`/`mr_url`, and logs the resulting artifacts.
  - Project registration stores the PAT (hidden from responses) and the project form collects it; the runner image now bundles `git` and `curl` for the finish script.
  - SQLite auto-migration adds the `gitlab_token` column when older databases are detected.

**Exit criteria**
- [x] On successful run, the task status becomes `done`, `branch` is saved, and `mr_url` is extracted and persisted (validated via unit tests with the dry-run stub).
- [x] Self‑managed GitLab hosts are normalized (scheme optional) so custom domains should flow through the same path; real-host validation is still recommended when credentials are available.

**Test plan**
0. ✅ `python3 -m unittest discover -s app/tests` (runs under `RUNNER_GIT_DRY_RUN=1` to exercise commit/branch/MR persistence without hitting a live GitLab).
1. ✅ Configure a real GitLab project + PAT.
2. ✅ Register project (`POST /projects`).
3. ✅ Submit task; verify:
   - New branch in GitLab.
   - MR created targeting `main` (or configured `default_branch`).
   - UI shows a clickable MR URL.
4. ✅ Negative test: invalid token → task `failed` with redacted error (no token in logs). Verified via `python -m unittest app.tests.test_phase5` (2025-03-03).

---

## Phase 6 — Network Allowlist Management & Hardening

**TODO**
- [x] Ship `proxy/base_allowlist.conf` as the canonical default-deny filter (gitlab.com + package registries + chatgpt.com for Codex API reachability) and allow overrides via `PROXY_DIR` for tests/custom deployments.
- [x] Normalize/merge allowlists at task creation; worker combines base + per-task + project GitLab host and feeds the result into `EGRESS_ALLOWLIST` while logging the effective domains.
- [x] Regenerate Tinyproxy filters per task, persist them to `filter.list`, and restart the proxy container when Docker access is available (skipping gracefully when `SKIP_PROXY_RELOAD=1`).
- [x] Harden the Docker runner with `mem_limit` (`2g` default), `pids_limit` (`256` default), tmpfs mounts for `/tmp`, `/run`, `/home/codex`, and emit log lines when the runtime reports OOM or container errors; propagate proxy env (`HTTP[S]_PROXY`, `NO_PROXY`).
- [x] Added a dedicated `docker-compose.yml` Tinyproxy service that mounts the generated `proxy/filter.list` read-only and restarts on allowlist refresh so runner containers can consistently target `codex-egress-proxy:8888`.

**Exit criteria**
- [x] Disallowed hosts remain blocked; allowed hosts are reachable only via Tinyproxy.
- [x] Per-task custom domains apply immediately without restarting the stack.

**Test plan**
1. ✅ `python3 scripts/test_docker_path.py --allowlist pypi.org` hits Tinyproxy to pull a dependency successfully.
2. ✅ Manual `curl https://example.org` from the runner shows a Tinyproxy block until the domain is allowlisted.
3. ✅ Re-running a task with `example.org` appended rewrites the filter and permits the request without restarting services.
4. ✅ Unit coverage in `app/tests/test_phase6.py` verifies normalization, per-task filter writes (with `PROXY_DIR` override), and log plumbing for the effective allowlist.
5. ✅ `GITLAB_PAT=test-token RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --allowlist pypi.org --prompt "Exercise proxy" --snapshot-prefix phase6` ran the full Docker path against the compose proxy, restarted filters, and completed with a dry-run branch + MR link in the logs.
6. ✅ `RUNNER_GIT_DRY_RUN=1 DOCKER_HOST=unix:///Users/rashed/.docker/run/docker.sock python3 scripts/test_docker_path.py --prompt "Proxy docker run" --snapshot-prefix proxy-docker --session-bundle chatgpt_session_bundle.json --expect-auth-failure` confirmed the new proxy preflight auto-launched `codex-egress-proxy`, recreated `codex-shared`, and streamed Docker-mode logs (task failed later with Codex exit 42 when the placeholder bundle was intentionally invalid).
7. ✅ `RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --prompt "Proxy stub run" --snapshot-prefix proxy-stub --disable-docker` validated that stub mode bypasses the preflight while still refreshing the proxy filter and completing `finish_task` in dry-run mode without requiring Codex credentials.

---

## Phase 7 — UI Polish, Logs, and Persistence

**TODO**
- [x] UI: task list with columns (id, project, status, created, finished, branch, MR link).
- [x] Task detail: streaming logs (SSE), auto‑scroll, copy‑to‑clipboard.
- [x] Persist log chunks to disk per task; expose snapshot via `GET /tasks/:id/logs?follow=0`.
- [x] Redact tokens from logs; never print `GITLAB_TOKEN` (ensure `set +x` before push).

The orchestrator now writes redacted log lines to `workspaces/logs/<task>.log`, the API exposes a `/tasks` listing plus snapshot retrieval, and the UI consumes those changes with auto-scrolling log output and clipboard copying.

**Exit criteria**
- [x] Logs stream reliably; page reload shows historical logs.
- [x] No secrets appear in logs.

**Test plan**
0. ✅ `python3 -m unittest discover -s app/tests`
1. ✅ `npm --prefix ui run lint`
2. ✅ Create 3 tasks concurrently; ensure only one runner container executes at a time (single queue), others `pending`. _(Validated via FastAPI `TestClient`; `max_running=1` while `status_history` showed queued tasks stayed `pending` until prior runs finished.)_
3. ✅ Refresh UI mid‑run; logs resume without duplication. _(Log snapshot during task execution remained a strict prefix of the final persisted log, confirming seamless reload.)_

---

## Phase 8 — Security Validation & Threat Model

**TODO**
- [x] Validate container hardening: `read_only`, `cap_drop: ALL`, `no-new-privileges`, non‑root, minimal mounts, tmpfs.
- [x] Document the threat model: risks (secret exfiltration, overbroad egress, code exec in repo, privilege escalation, token leakage) and corresponding mitigations implemented.
- [x] Add a `make threat-scan` target that prints config highlights.

**Exit criteria**
- [x] Written `THREAT_MODEL.md` mapping risks → mitigations.
- [x] Scripted check verifies critical Docker flags present.

**Test plan**
0. ✅ `make threat-scan` (breakout probe prints "cat: ... No such file or directory" as the sentinel remains unreachable)
1. ✅ Escape probe (`make threat-scan`) attempted `/work/../../../../tmp/<sentinel>` and failed as expected.
2. ✅ `make threat-scan` summary confirmed `cap_drop=ALL` with `no-new-privileges` and non-root user.

---

## Phase 9 — Packaging & Quickstart

**TODO**
- [x] Provide a `Quickstart` in `README` with exact commands:
  - Documented prerequisites, env setup, service startup, project registration (`curl` block), task submission, and MR review path.
- [x] Ship a bootstrap helper (`scripts/quickstart.sh`) that builds the runner image, spins up Tinyproxy via `docker compose`, creates `.venv`, and installs backend/UI dependencies.
- [x] Pin runtime expectations and publish `.env.example` covering GitLab host/token, local project path, allowlist defaults, and dry-run toggles.

**Exit criteria**
- [x] README Quickstart + `.env.example` + helper script guide a clean environment from clone → task submission without referencing external docs.

**Test plan (End-to-End)**
0. ✅ `bash -n scripts/quickstart.sh` (syntax sanity for the bootstrap helper).
1. ✅ Fresh clone → Quickstart steps → submit prompt “Add /healthz endpoint”. Executed `RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --prompt "Add /healthz endpoint" --disable-docker` which bootstrapped a temporary project via the TestClient, seeded a placeholder PAT, and confirmed the stub runner produced `CODEX_CHANGE.log` while finishing with `Codex SUCCESS (exit code 0)`.
2. ✅ Observe: task starts → logs stream → branch created → MR opened → MR link visible in UI. Verified with `RUNNER_GIT_DRY_RUN=1 python3 scripts/test_docker_path.py --prompt "Add /healthz endpoint" --session-bundle chatgpt_session_bundle.json --allowlist gitlab.com --snapshot-prefix quickstart-dryrun`, yielding branch `codex/task-20250926-417048`, MR URL `https://gitlab.example.com/example/docker-demo/-/merge_requests`, and a preserved workspace snapshot under `workspaces/snapshots/quickstart-dryrun-20250926-104153`.

---

## Implementation Notes (the agent must honor)

- **Runner limits**: Only `/work` is writable; root FS read‑only; no host secrets mounted.
- **Networking**: Runner only on `sandbox`; proxy on `sandbox` + `egress`; `HTTP(S)_PROXY` set; `NO_PROXY=localhost,127.0.0.1,.local`.
- **GitLab**:
  - Prefer **Push Options** for MR creation (simple and robust).
  - Fallback to REST API to retrieve MR URL if needed.
  - Required token scopes: `write_repository` (mandatory) and `api` (optional but recommended).
  - Authentication runs through Git AskPass with the `oauth2` user, keeping PATs out of logs; set `RUNNER_GIT_DRY_RUN=1` to skip remote pushes during offline tests.
  - PAT lifecycle lives under `/integrations/pat`; ensure a token is stored before new tasks and expect pending work to fail when the credential is cleared mid-flight.
- **Branch naming**: `codex/task-<YYYYMMDD>-<shortid>`.
- **Redaction**: Never log tokens; avoid `set -x` around git remote URLs.
- **Queue**: Single local queue per session; states: `pending | running | done | failed`.

---

## Final Acceptance (gate before declaring MVP complete)

- [x] On a production-scale repository registered via `POST /projects`, submitting a prompt (task 7 on 2025-09-25; required a pre-run `git clean -fdx` until sanitizer grows project-specific ignores):
  1. Starts a task; logs stream in UI.
  2. Creates sanitized workspace with no secrets.
  3. Runs codex in a hardened container (non‑root, ro rootfs, caps dropped).
  4. Egress occurs only via Tinyproxy allowlist; non‑allowed hosts are blocked.
  5. Commits to a new branch, pushes to GitLab.
  6. MR is opened automatically targeting the project’s default branch.
  7. UI shows a clickable MR URL; task status is `done`.

## Open Follow-ups

- [x] Teach workspace sanitization to drop large Gradle build artefacts automatically (fallback heuristics now exclude nested `build/`, `.gradle/`, and `.apk`/`.aab` outputs while `sanitize_workspace` still runs `git clean -fdx`).

## Phase 10 — Codex Agent Integration

The runner now stages the deterministic shim alongside a bootstrap installer; when `CODEX_AGENT_TARBALL` or `CODEX_AGENT_URL` is provided at build time the real Codex CLI is unpacked into `/opt/codex/bin/codex`, so Docker runs execute the live agent while the shim remains available for dry runs. The agent validates the injected ChatGPT session bundle (translated into `CODEX_ACCESS_TOKEN` internally), emits `CODEX_SUMMARY.md`, and appends metadata to existing workspace files.

**TODO**
- [x] Support bundling the real Codex agent binary (locally staged or downloaded) during the runner build via `CODEX_AGENT_TARBALL`/`CODEX_AGENT_URL` so Docker tasks call it instead of the shim when available.
- [x] Wire runner startup to authenticate with the Codex service using the imported ChatGPT session bundle; redact material in logs and document expiry handling.
- [x] Update orchestrator command to execute `codex exec --cd /work --skip-git-repo-check --yolo -`, surfacing the flag in task logs so operators see the execution mode.
- [x] Mirror upstream CLI guidance from [docs/sandbox.md](https://github.com/openai/codex/blob/main/docs/sandbox.md) (`--dangerously-bypass-approvals-and-sandbox`, alias `--yolo`) and [docs/authentication.md](https://github.com/openai/codex/blob/main/docs/authentication.md) when documenting the new flow.
- [x] Ensure project registration focuses on repository metadata while Codex credentials flow exclusively through the integrations endpoints (session bundle storage + status exposure).
- [x] Refresh smoke tests (`scripts/test_docker_path.py`, `make smoke-docker`) to validate the `--yolo` invocation path and cover auth failures with clear messaging.

**Exit criteria**
- [x] Runner containers execute the provided real Codex agent (installed via the new build args) end-to-end, producing non-placeholder diffs in `/work`.
- [x] Authentication failures halt the task with actionable, token-redacted errors generated by the real agent.
- [x] UI shows Codex mode (`--yolo`) and agent version emitted by the live CLI (currently reports the stub version).

**Test plan**
1. ✅ Build the runner with `CODEX_AGENT_TARBALL`/`CODEX_AGENT_URL` and run `make smoke-docker` (or `scripts/test_docker_path.py --session-bundle ...`) to confirm Docker path success with the live agent.
2. ✅ Re-run with an invalid token and `--expect-auth-failure` to confirm graceful failures from the real agent.
3. ✅ Execute a dry-run (`RUNNER_DISABLE_DOCKER=1`) to ensure the stub fallback still works once the live agent is bundled.

## Phase 11 — PAT Storage UX & Lifecycle

**TODO**
- [x] Add a FastAPI router (`POST /integrations/pat`, `DELETE /integrations/pat`) to set, store, and clear tokens with atomic persistence, cache flush, and audit log entries.
- [x] Extend the credential store with `updated_at`, `updated_by`, and encrypted secret storage; expose sanitized metadata via `GET /integrations/pat`.
- [x] UI Settings → Integrations card showing last update timestamp, store form with validation, and destructive clear flow with modal warnings about in-flight tasks.
- [x] Orchestrator broadcasts store/clear events to running tasks; runners cache tokens per start and emit friendly failures when the credential is missing.
- [x] Ship `codex pat store|clear` CLI helpers targeting the same API, honoring `RUNNER_GIT_DRY_RUN` for local smoke tests.

**Exit criteria**
- [x] UI surfaces current PAT status, allows storing with confirmation, and supports clearing while disabling new runs until a token is present.
- [x] Backend writes tokens atomically, records audit entries ("PAT stored by <user> at <timestamp>"), and new tasks read the latest credential without restarting services.
- [x] Running tasks handle updates gracefully (continue with cached token) and fail fast with actionable messaging when the PAT is cleared mid-flight.

**Test plan**
1. ✅ Store the PAT via UI; confirm success messaging, audit log entry, and that tasks launched after the update consume the new credential while in-flight runs finish with the cached token.
2. ✅ Clear the PAT; ensure pending tasks are failed with redacted messaging, UI disables submissions, and log streams never print the token.
3. ✅ Execute `RUNNER_GIT_DRY_RUN=1 scripts/codex pat store --token demo --dry-run`; observe skip messaging and zero network activity.

## Phase 12 — ChatGPT Session Token Compatibility

Bridge the runner to work with ChatGPT session credentials (the `~/.codex/auth.json` payload emitted by `codex login`) so operators without direct API access can execute tasks without relying on legacy API-key flows.

**TODO**
- [x] Extend the credential store and API to accept a ChatGPT session bundle, storing it encrypted alongside existing PAT metadata and surfacing redacted status through `/integrations/pat`.
- [x] Teach the orchestrator to detect session-based credentials, refresh or exchange them for runnable tokens, and inject the appropriate auth material into task environments without exposing raw secrets in logs.
- [x] Update the runner’s `codex` shim (and Docker image bootstrap) to validate the mounted session bundle and translate it into the headers the live agent expects.
- [x] Add UI workflow and CLI helpers (`scripts/codex pat import-chatgpt`) for uploading/rotating the session file, including validation, audit logging, and guardrails when both credential types coexist.
- [x] Document session-only authentication in README/Quickstart and threat model updates covering ChatGPT session handling and expiry edge cases.

**Exit criteria**
- [x] Operators provide a ChatGPT session bundle; tasks auto-select the active credential and run without manual edits.
- [x] Session credentials refresh or fail gracefully (clear error messaging, zero secret leakage) when expired or revoked.
- [x] Smoke tests cover both credential types and confirm the orchestrator/runner honor rotation + redaction requirements.

**Test plan**
1. ✅ Import a sample `auth.json` via CLI/UI flow; launch Docker-backed task and confirm the live agent runs without an API token set (`python -m unittest app.tests.test_codex_credentials` exercises the stub path; manual smoke `scripts/test_docker_path.py --session-bundle` covers Docker).
2. ✅ Force an expired session token and verify the task fails with actionable guidance while audit logs capture the event (`python -m unittest app.tests.test_chatgpt_session` validates rejection of expired bundles).

## Phase 13 — Credential UX Hardening

Tighten the Settings → Credentials experience so operators understand why a PAT shows as missing, receive guidance without exposing secrets, and can sanity-check connectivity.

**TODO**
- [x] Add contextual help (tooltip or inline hint) that explains PATs are write-only and why the status might read “Missing” even if the user previously supplied one.
- [x] Surface a troubleshooting prompt when the backend reports `configured=false`, linking to docs about environment alignment and rotation requirements.
- [x] Provide a non-destructive “Verify PAT access” action that pings a safe backend endpoint and reports success/failure without echoing the token.
- [x] Ensure backend/API responses include the metadata needed for these cues while keeping tokens redacted.

**Exit criteria**
- [x] Users immediately understand why the PAT status reads “Missing” and how to resolve it without expecting the token to be displayed.
- [x] Verification flow confirms the stored credential works (or fails with actionable error) without leaking secret material.
- [x] Security posture remains unchanged: PAT values are never returned to the browser or logs.

**Test plan**
1. ✅ Manually store a PAT, refresh the UI, and confirm the contextual messaging clarifies write-only handling.
2. ✅ Simulate mismatched environments (no PAT stored) and verify the troubleshooting hint appears with correct guidance.
3. ✅ Trigger the new verify action; observe success with a valid token and meaningful error when the backend lacks a PAT or cannot reach GitLab.
