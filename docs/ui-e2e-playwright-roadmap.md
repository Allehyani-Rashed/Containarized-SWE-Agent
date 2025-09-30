# UI E2E Automation Roadmap (Playwright + Real Codex CLI)

## Overview
The goal is to deliver a reproducible, scripted Playwright suite that drives the Containerized Codex Agent UI end-to-end while the backend executes real Codex CLI tasks against a dedicated GitLab test project. The roadmap breaks the effort into phases so we can stage infrastructure, secrets, tooling, and CI integration with clear checkpoints.

## Phase 0 – Preconditions & Environment Baseline
- [ ] Confirm availability of a disposable GitLab project and PAT with API + write_scopes; document repository URL and branch defaults.
- [ ] Capture a Codex API token dedicated to automation and store it in a secure secret manager (no hard-coding in repo).
- [ ] Validate Docker Desktop + Tinyproxy stack locally (`make dev`, `scripts/test_docker_path.py` with `--codex-token`).
- [ ] Ensure Vite dev proxy fix (`ui/vite.config.ts`) is present so deep-link routes serve the SPA shell for Playwright.
- [ ] Decide where secrets will live for local runs (e.g., `.env.e2e.local`, direnv, or 1Password CLI) and in CI (GitLab masked vars).
- [ ] Document cleanup expectations for GitLab branches/MRs so operators know what to prune post-run.

## Phase 1 – Local Runner Harness
- [ ] Add a `make e2e-ui` target that orchestrates:
  - exports required env vars (GitLab PAT, Codex token, Docker socket path)
  - ensures proxy stack is healthy (`ensure_proxy_stack`) and runner images are built
  - launches API + UI servers (can reuse `scripts/dev.sh` or spawn dedicated processes) with logging to files for troubleshooting
- [ ] Build a Playwright project scaffold (`ui/playwright.config.ts`, `ui/tests/e2e/` directory) with TypeScript + test runner integration.
- [ ] Pin browser downloads via `npx playwright install --with-deps chromium` and cache location under repo `.playwright` to avoid polluted user caches.
- [ ] Provide helper script (`scripts/e2e_env.sh`) that validates env vars and outputs sanitized summary before tests start.

## Phase 2 – Credential Seeding & Project Lifecycle
- [ ] Extend backend API helpers or add CLI hook to create/update projects via REST before the UI test runs (to avoid manual UI input when unstable).
- [ ] Implement Playwright fixture that drives the Settings page to store the PAT if the backend reports `configured=False`; fallback to API call when UI flow fails (keeps test deterministic).
- [ ] Add helper to ensure the GitLab test project is registered (POST `/projects`) with codex token and allowlist configured.
- [ ] Persist sanitized credentials to the sanitized workspace (`/work`) only for the test duration; ensure teardown wipes them (`git clean` in workspace, secret manager clear call).

## Phase 3 – Core Playwright Scenario
- [ ] Author primary test `ui/tests/e2e/task-smoke.spec.ts` to:
  1. Navigate to Submit Task, verify credential banners, and submit a task with unique prompt/branch.
  2. Poll the Tasks page until status transitions to `done` or `failed`, capturing streamed logs as attachments.
  3. Assert MR metadata appears when Codex pushes successfully; skip assertion if runner reports shim mode.
  4. Open task drawer, verify logs contain expected sentinel (e.g., `Codex SUCCESS`).
- [ ] Include retries/backoff for slow Codex runs (configurable timeout, default 15 minutes).
- [ ] Capture screenshots on failure and upload artifacts to `workspaces/snapshots/e2e/<timestamp>` (respect existing snapshot conventions).
- [ ] Gate tests behind feature flag `ENABLE_CI_E2E_UI` so day-to-day `npm test` stays fast.

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
- Do we need separate Codex tokens per environment (dev vs CI), or can we reuse one with IP restrictions?
- Should the Playwright suite also validate Tinyproxy allowlist enforcement (e.g., attempt blocked domain fetch)?
- How should we version-control Playwright screenshots/baselines—store in repo or auto-generate per run?

## Next Steps
1. Confirm PAT, GitLab repo, and Codex token details with the operator.
2. Decide on local secret storage strategy and produce `.env.e2e.example` for contributors.
3. Kick off Phase 1 implementation once secrets are ready and reviewers are aligned on tooling choices.
