# GitLab Project Cache Workflow

This document captures the proposed changes for automatically cloning and refreshing the configured GitLab repository before each task run.

## Goals

- Provide a single canonical working clone for every registered project.
- Ensure the sanitized workspace always starts from the latest default branch.
- Avoid clobbering operator edits or cached state without explicit consent.
- Limit the initial rollout to default-branch caching; additional branch strategies are out of scope.

Automation helper: run `python3 scripts/run_codex_plan.py` to drive each phase sequentially through the Codex CLI, marking checkboxes as work completes (use `--plan <path>` to target other plans).

## Phase Plan

### Phase 1 – Establish Cache Infrastructure

- [ ] Introduce a deterministic cache location (e.g. `project-cache/<slug>/repo`).
- [ ] During quickstart, clone the default branch into the cache when it does not exist, using the stored PAT.
- [ ] Treat the cache directory as the canonical working tree and remove the need for operators to configure `PROJECT_LOCAL_PATH`.

### Phase 2 – Guard Rails and Default-Branch Refresh

- [ ] Detect non-git directories or dirty working trees and abort with a clear warning instead of overwriting operator changes.
- [ ] Honour `RUNNER_GIT_DRY_RUN=1` by skipping network operations while logging the intended actions.
- [ ] Right before workspace sanitization, fetch and hard-reset to the latest default-branch commit.
- [ ] Log the synced commit hash so operators know which revision was sanitized.

### Phase 3 – Credential Handling and Git Extras

- [ ] Reuse the stored PAT for clone/pull operations and propagate it to all cache actions.
- [ ] Support submodules and Git LFS via `git submodule update --init --recursive`, `git lfs fetch`, and `git lfs checkout` when needed.
- [ ] Surface authentication errors, missing branches, or other failures directly in task logs.

### Phase 4 – Feature Flags and Manual Maintenance

- [ ] Enable the cache workflow by default and remove legacy environment variables such as `PROJECT_LOCAL_PATH`.
- [ ] Ship a helper command (e.g. `scripts/project_cache.py --refresh`) for manual cache maintenance outside the task lifecycle.

### Phase 5 – System Integration Updates

- [ ] Orchestrator resolves the project path to `project-cache/<slug>/repo`, passes that directory to the sanitizer, and (optionally) surfaces the synced commit in task metadata.
- [ ] Worker bootstrap ensures cache directories exist with correct permissions, executes bootstrap/refresh commands, and short-circuits cleanly when `RUNNER_GIT_DRY_RUN=1`.
- [ ] Runner scripts (including `scripts/quickstart.sh` and `scripts/test_docker_path.py`) rely on the cache path instead of `PROJECT_LOCAL_PATH`.
- [ ] Configuration schema removes environment variables, API fields, and database columns that reference operator-specified paths while introducing any tuning settings (e.g., size limits, prune interval) required for the cache.
- [ ] UI drops form inputs that collected `PROJECT_LOCAL_PATH`, highlights cache status/commit details, and exposes cache maintenance actions if needed.
- [ ] Documentation updates reference the deterministic cache directory across README, onboarding, and operator guides.

### Phase 6 – Logging and Observability

- [ ] Log every cache bootstrap and refresh with timestamps, project identifiers, and resulting commit hashes.
- [ ] Emit metrics for clone/refresh duration, failure counts by reason, and cache size so operators can monitor drift or storage pressure.
- [ ] Annotate task logs with the cache path and revision used for sanitization to aid postmortems.

### Phase 7 – Testing Coverage

- [ ] Extend `scripts/test_docker_path.py` (dry-run and Docker flows) to exercise cache bootstrap, refresh, and failure scenarios.
- [ ] Add backend unit tests covering the cache helper, including dry-run behavior, dirty tree detection, and error propagation.
- [ ] Update integration smoke tests (`make dev`, `make threat-scan`, targeted unit suites) to confirm task logs reference the new cache path and legacy env vars are ignored.
- [ ] Introduce a regression test ensuring cache corruption triggers an actionable failure rather than continuing with stale data.

### Phase 8 – Deprecations and Cleanup

- [ ] Remove dead code and configuration tied to `PROJECT_LOCAL_PATH` (environment loaders, ORM models, serializer fields, UI state hooks).
- [ ] Document the removal in release notes so downstream deployments know to delete the variable from their infrastructure templates.

### Phase 9 – Rollout and Migration

- [ ] For each registered project, run a one-time bootstrap (e.g. `scripts/project_cache.py --bootstrap <project-id>`) to clone into `project-cache/<slug>/repo` before enabling automated refreshes.
- [ ] Purge stored `PROJECT_LOCAL_PATH` values from configuration stores, secrets managers, or `.env` files and update deployment manifests to omit the variable.
- [ ] Communicate the change to operators, emphasizing that local manual clones are no longer consulted and that cache maintenance commands replace `.env` edits.

### Phase 10 – Failure Handling and Recovery

- [ ] Detect missing or corrupted cache repositories before sanitization, log actionable remediation steps (`scripts/project_cache.py --refresh`, manual `git fsck`, or cache deletion), and fail the task gracefully.
- [ ] Handle renamed or deleted default branches by surfacing the upstream Git error and suggesting fixes (update project metadata, re-bootstrap the cache).
- [ ] When PAT authentication fails, mask the secret, show the host and branch involved, and recommend invoking `POST /integrations/pat/verify` (or the UI action) so operators can confirm credentials.
- [ ] Preserve operator-modified caches by exiting with a warning if the working tree is dirty and require an explicit `--force` flag to overwrite local edits.

### Phase 11 – Future Considerations

- [ ] Decide how to handle cache pruning or storage limits on long-lived hosts.
- [ ] Decide whether caches should be snapshotted for auditability after each task run.
- [ ] Determine if or when the cache design should expand beyond the default-branch workflow documented here.

### Immediate Follow-ups

- [ ] Update `.env.example`, onboarding docs, and quickstart scripts to drop instructions for setting `PROJECT_LOCAL_PATH` and reference the deterministic cache directory instead.
- [ ] Remove backend or UI configuration fields that prompt operators for a local project path, including database columns, environment schemas, and settings forms.
- [ ] Refresh operator notes and troubleshooting guides so maintenance steps target `project-cache/<slug>/repo` (e.g. `scripts/project_cache.py --refresh`).
