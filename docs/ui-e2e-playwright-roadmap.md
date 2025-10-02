# UI E2E Automation Roadmap (Playwright + Real Codex CLI)

## Overview
The goal is to deliver a reproducible, scripted Playwright suite that drives the Containerized Codex Agent UI end-to-end while the backend executes real Codex CLI tasks against a dedicated GitLab test project. The roadmap breaks the effort into phases so we can stage infrastructure, secrets, tooling, and CI integration with clear checkpoints.

Baseline automation is now in place:
- `make e2e-ui` orchestrates environment validation, dependency installation, browser provisioning, and the Playwright run.
- `scripts/e2e_env.sh` + `.env.e2e.example` define how contributors load GitLab + Codex secrets without leaking them into the repo, printing a masked summary before tests start.
- `ui/playwright.config.ts` launches both FastAPI and Vite through Playwright’s `webServer` hooks, pins downloads under `.playwright/`, and skips the suite unless `ENABLE_CI_E2E_UI` is set.
- `ui/tests/e2e/task-smoke.spec.ts` seeds a project via the backend API, verifies credential banners on Submit Task, stubs branch lookups, and exercises the Projects dashboard.

The remaining phases focus on covering more workflows (Settings, Tasks, MR metadata), hardening secrets handling, and wiring the suite into GitLab CI.

## Phase 0 – Preconditions & Environment Baseline
- [ ] Confirm availability of a disposable GitLab project and PAT with API + write scopes; document repository URL and branch defaults.
- [ ] Capture a dedicated ChatGPT session bundle for automation and store it in a secure secret manager (no hard-coding in repo).
- [ ] Validate Docker Desktop + Tinyproxy stack locally (`make dev`, `scripts/test_docker_path.py` with `--session-bundle` or export `CHATGPT_SESSION_BUNDLE_PATH`/`CHATGPT_SESSION_JSON`).
- [x] Ensure Vite dev proxy fix (`ui/vite.config.ts`) is present so deep-link routes serve the SPA shell for Playwright.
- [x] Decide where secrets will live for local runs (e.g., `.env.e2e.local`, direnv, or 1Password CLI) and in CI (GitLab masked vars).
  - `.env.e2e.example` plus `scripts/e2e_env.sh` load contributor secrets, expose `GITLAB_PAT`/ChatGPT session bundles, and reject missing inputs with guidance.
- [ ] Document cleanup expectations for GitLab branches/MRs so operators know what to prune post-run.

## Phase 1 – Local Runner Harness
- [x] Add a `make e2e-ui` target that orchestrates:
  - exports required env vars (GitLab PAT, ChatGPT session bundle, optional Docker socket path)
  - installs UI dependencies and provisions browsers into `.playwright/`
  - runs `npm --prefix ui run test:e2e` with `ENABLE_CI_E2E_UI=1`
- [x] Build a Playwright project scaffold (`ui/playwright.config.ts`, `ui/tests/e2e/` directory) with TypeScript + test runner integration.
  - Config spins up FastAPI (`uvicorn`) and Vite via Playwright `webServer`, reusing servers locally when possible.
- [x] Pin browser downloads via `npm --prefix ui exec -- playwright install --with-deps chromium` and cache location under repo `.playwright` to avoid polluted user caches.
- [x] Provide helper script (`scripts/e2e_env.sh`) that validates env vars and outputs sanitized summary before tests start.
  - Script sources `.env.e2e.local` when present, normalizes overrides, and exports `E2E_API_BASE_URL`/`E2E_UI_BASE_URL` defaults.

## Phase 2 – Credential Seeding & Project Lifecycle
- [ ] Extend backend API helpers or add CLI hook to create/update projects via REST before the UI test runs (to avoid manual UI input when unstable).
- [ ] Implement Playwright fixture that drives the Settings page to store the PAT if the backend reports `configured=False`; fallback to API call when UI flow fails (keeps test deterministic).
- [x] Add helper to ensure the GitLab test project is registered (POST `/projects`) with allowlist configured.
  - `task-smoke.spec.ts` seeds/updates a deterministic `[E2E] Playwright Smoke Project` via the FastAPI `/projects` endpoint and reuses it across runs.
- [ ] Persist sanitized credentials to the sanitized workspace (`/work`) only for the test duration; ensure teardown wipes them (`git clean` in workspace, secret manager clear call).

## Phase 3 – Core Playwright Scenario
- [x] Author primary test `ui/tests/e2e/task-smoke.spec.ts` to:
  1. Navigate to Submit Task, verify credential banners, and assert seeded project availability.
  2. Switch to the Projects dashboard and confirm repo metadata / credentials render.
- [ ] Extend the smoke path to submit a task with unique prompt/branch and wait for Codex completion (stub mode fallback allowed).
- [ ] Include retries/backoff for slow Codex runs (configurable timeout, default 15 minutes).
- [ ] Capture screenshots on failure and upload artifacts to `workspaces/snapshots/e2e/<timestamp>` (respect existing snapshot conventions).
- [x] Gate tests behind feature flag `ENABLE_CI_E2E_UI` so day-to-day `npm test` stays fast.

## Phase 4 – Additional Coverage & Tooling
- [ ] Add secondary spec covering Projects page CRUD (create/edit/delete) with the real repo to ensure form integrations stay healthy.
- [ ] Implement Settings verification spec that exercises PAT verify + session import flows (using mock bundle if real session not available).
- [ ] Provide utility to randomize branch names but record them in test artifacts for manual review.
- [ ] Hook up clipboard mocks in Playwright to validate copy-to-clipboard actions (fall back to prompt when denied).
- [ ] Add accessibility snapshot checks (axe-core) on key pages to catch regressions.

## Phase 5 – CI Integration (GitLab Pipelines)
- [ ] Create GitLab CI job `ui:e2e` that:
  - pulls secrets from masked variables
  - runs `make e2e-ui` inside the Docker runner environment
  - uploads Playwright HTML reports and log bundles as pipeline artifacts
- [ ] Ensure job runs in a nightly schedule and on-demand (manual) pipeline, not on every commit (to conserve Codex quota).
- [ ] Add notification hook (Slack/email) when E2E fails, including MR/branch details produced by Codex.
- [ ] Update `README.md` and operator docs with instructions for triggering the job and interpreting results.

## Phase 6 – Hardening & Cleanup
- [ ] Build teardown script that closes open merge requests/branches older than N days (optional manual flag).
- [ ] Add metrics around test runtime, Codex success rate, and GitLab API usage; surface in dashboard or logs.
- [ ] Document troubleshooting guide for common failures (token expired, Docker unavailable, proxy misconfigured).
- [ ] Review security posture: ensure secrets never leak into Playwright trace files; scrub logs before storing.

## Deliverables & Owners
- Playwright project scaffold checked into repo with lint/test integration.
- `make e2e-ui` command documented and usable locally with provided secrets.
- CI job definition and documentation for nightly/on-demand runs.
- Runbook for operators describing setup, execution, teardown, and cleanup processes.

## Open Questions
- Which environment should host the dedicated GitLab repo (self-managed vs gitlab.com) and what rate limits apply?
- How do we manage session bundle rotation across environments (dev vs CI) without leaking long-lived tokens?
- Should the Playwright suite also validate Tinyproxy allowlist enforcement (e.g., attempt blocked domain fetch)?
- How should we version-control Playwright screenshots/baselines—store in repo or auto-generate per run?

## Next Steps
1. Promote the Playwright helper routines into shared fixtures (or a lightweight CLI) so CI jobs can seed PATs and projects without copying test logic.
2. Expand the smoke to submit a Codex task end-to-end (stub-friendly), capturing streamed logs and snapshots for later assertions.
3. Prototype the Settings/PAT verification journey to ensure UI flows stay stable before wiring a nightly GitLab CI job.
