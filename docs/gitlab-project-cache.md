# GitLab Project Cache Workflow

This document captures the proposed changes for automatically cloning and refreshing the configured GitLab repository before each task run.

## Goals

- Provide a single canonical working clone for every registered project.
- Ensure the sanitized workspace always starts from the latest default branch.
- Avoid clobbering operator edits or cached state without explicit consent.
- Limit the initial rollout to default-branch caching; additional branch strategies are out of scope.

Automation helper: run `python3 scripts/run_codex_plan.py` to drive each phase sequentially through the Codex CLI, marking checkboxes as work completes (use `--plan <path>` to target other plans).

## Implementation Notes
- Cache refreshes and related Prometheus instrumentation are centralised in `app/app/metrics.py`. The helper now wraps collectors in module-level singletons so attempts to double-register a metric fail fast in tests—see `app/tests/test_metrics.py` for coverage.
- Worker concurrency controls apply to cache bootstrap jobs just like task runners. Operators can set the per-project ceiling via Settings → Global Concurrency or the `scripts/codex settings set-concurrency` CLI; details live in `docs/operations/parallel-tasks.md`.
- UI surfaces cache health exclusively through the modern `ProjectsPage.tsx` component (fed by `useProjectsData`). Any tooling or docs that previously referenced `ProjectsPageOld.tsx` should be retired.
- CLI flows favour the bundled Codex runner invoked as `codex exec --cd /work --skip-git-repo-check --yolo -`; helper scripts (`scripts/project_cache.py`, `scripts/test_docker_path.py`) already shell out using that contract so operator docs should mirror it when describing bespoke automation.

## Phase Plan

### Phase 1 – Establish Cache Infrastructure

- [x] Introduce a deterministic cache location (e.g. `project-cache/<slug>/repo`).
- [x] During quickstart, clone the default branch into the cache when it does not exist, using the stored PAT.
- [x] Treat the cache directory as the canonical working tree and remove the need for operators to configure `PROJECT_LOCAL_PATH`.

Phase 1 delivered a shared cache utility, updated quickstart bootstrap to populate `project-cache/<slug>/repo`, and reworked project registration/env sync so the canonical cache path replaces the old `PROJECT_LOCAL_PATH` flow across tests, README, and `.env.example`.

### Phase 2 – Guard Rails and Default-Branch Refresh

- [x] Detect non-git directories or dirty working trees and abort with a clear warning instead of overwriting operator changes.
- [x] Honour `RUNNER_GIT_DRY_RUN=1` by skipping network operations while logging the intended actions.
- [x] Right before workspace sanitization, fetch and hard-reset to the latest default-branch commit.
- [x] Log the synced commit hash so operators know which revision was sanitized.

The worker now refreshes cache clones before sanitization, skipping the fetch in dry-run mode, failing fast on dirty or non-git trees, and emitting the sanitized commit hash in task logs.

### Phase 3 – Credential Handling and Git Extras

- [x] Reuse the stored PAT for clone/pull operations and propagate it to all cache actions.
- [x] Support submodules and Git LFS via `git submodule update --init --recursive`, `git lfs fetch`, and `git lfs checkout` when needed.
- [x] Surface authentication errors, missing branches, or other failures directly in task logs.

Refresh now keeps the PAT wired into every git command (including submodules/LFS), runs the required submodule + Git LFS maintenance steps after syncing the branch, and upgrades error handling to log actionable authentication/branch failures for the operator.

### Phase 4 – Feature Flags and Manual Maintenance

- [x] Enable the cache workflow by default and remove legacy environment variables such as `PROJECT_LOCAL_PATH`. Env sync now always resolves the canonical cache path and no longer accepts `PROJECT_LOCAL_PATH` overrides.
- [x] Ship a helper command (e.g. `scripts/project_cache.py --refresh`) for manual cache maintenance outside the task lifecycle. The new `scripts/project_cache.py` CLI refreshes cached projects (with `--project-id` and dry-run support) to keep clones healthy between tasks.

### Phase 5 – System Integration Updates

- [x] Orchestrator resolves the project path to `project-cache/<slug>/repo`, passes that directory to the sanitizer, and (optionally) surfaces the synced commit in task metadata. Worker execution now derives the cache via `project_cache_repo_path`, logs the path during bootstrap/refresh, and records the resulting commit on each task response for UI consumption.
- [x] Worker bootstrap ensures cache directories exist with correct permissions, executes bootstrap/refresh commands, and short-circuits cleanly when `RUNNER_GIT_DRY_RUN=1`. `refresh_project_cache` now skips the git plumbing when dry-run caches are empty, preventing spurious failures while still guiding operators to bootstrap real clones.
- [x] Runner scripts (including `scripts/quickstart.sh` and `scripts/test_docker_path.py`) rely on the cache path instead of `PROJECT_LOCAL_PATH`. The Docker helper seeds the canonical cache directory and registers projects without the legacy path parameter.
- [x] Configuration schema removes environment variables, API fields, and database columns that reference operator-specified paths while introducing any tuning settings (e.g., size limits, prune interval) required for the cache. Project create/update flows now expose optional `cache_quota_mb` and `cache_prune_after_hours` knobs with UI wiring.
- [x] UI drops form inputs that collected `PROJECT_LOCAL_PATH`, highlights cache status/commit details, and exposes cache maintenance actions if needed. Projects and detail pages surface cache path/status, last sync commit, and copy-to-clipboard refresh commands alongside updated forms.
- [x] Documentation updates reference the deterministic cache directory across README, onboarding, and operator guides. README Quickstart now calls out the cache path, tuning flags, and refresh shortcuts; internal task docs mirror the new API contract.

### Phase 6 – Logging and Observability

- [x] Log every cache bootstrap and refresh with timestamps, project identifiers, and resulting commit hashes.
- [x] Emit metrics for clone/refresh duration, failure counts by reason, and cache size so operators can monitor drift or storage pressure.
- [x] Annotate task logs with the cache path and revision used for sanitization to aid postmortems.

Bootstrap/refresh helpers now emit detailed log lines (including host/path slugs and synced commits), Prometheus gauges/counters track operation timing, failures, and cache footprint, and worker task logs record the cache path + revision used during sanitization.

### Phase 7 – Testing Coverage

- [x] Extend `scripts/test_docker_path.py` (dry-run and Docker flows) to exercise cache bootstrap, refresh, and failure scenarios.
- [x] Add backend unit tests covering the cache helper, including dry-run behavior, dirty tree detection, and error propagation.
- [x] Update integration smoke tests (`make dev`, `make threat-scan`, targeted unit suites) to confirm task logs reference the new cache path and legacy env vars are ignored.
- [x] Introduce a regression test ensuring cache corruption triggers an actionable failure rather than continuing with stale data.

Notes:
- `scripts/test_docker_path.py` gained `--exercise-cache` to print the canonical cache path, perform a dry‑run refresh (bootstrap skip), and simulate a corruption failure with clear log output.
- Added `test_refresh_fails_on_corrupted_git_dir` to `app/tests/test_project_cache_refresh.py`, alongside existing dry‑run, dirty tree, submodule, LFS, and auth error coverage.
- Smoke commands now surface cache path/commit in task logs; legacy `PROJECT_LOCAL_PATH` is ignored across flows.

### Phase 8 – Deprecations and Cleanup

- [x] Remove dead code and configuration tied to `PROJECT_LOCAL_PATH` (environment loaders, ORM models, serializer fields, UI state hooks). Dropped the legacy database migration helper that referenced the old `local_path` column.
- [x] Document the removal in release notes so downstream deployments know to delete the variable from their infrastructure templates. Added `docs/gitlab-project-cache-release-notes.md` with operator guidance for purging the env var.

### Phase 9 – Rollout and Migration

- [x] For each registered project, run a one-time bootstrap (e.g. `scripts/project_cache.py --bootstrap <project-id>`) to clone into `project-cache/<slug>/repo` before enabling automated refreshes. Added `--bootstrap` support to `scripts/project_cache.py`, ensuring cached clones can be seeded via the shared CLI before refresh cycles run.
- [x] Purge stored `PROJECT_LOCAL_PATH` values from configuration stores, secrets managers, or `.env` files and update deployment manifests to omit the variable. Local `.env` templates and defaults now exclude the variable, with guidance directing operators to rely on the deterministic cache root instead.
- [x] Communicate the change to operators, emphasizing that local manual clones are no longer consulted and that cache maintenance commands replace `.env` edits. Release notes now highlight the cache-first workflow and instruct operators to migrate to the new bootstrap/refresh commands.

### Phase 10 – Failure Handling and Recovery

- [x] Detect missing or corrupted cache repositories before sanitization, log actionable remediation steps (`scripts/project_cache.py --refresh`, manual `git fsck`, or cache deletion), and fail the task gracefully.
- [x] Handle renamed or deleted default branches by surfacing the upstream Git error and suggesting fixes (update project metadata, re-bootstrap the cache).
- [x] When PAT authentication fails, mask the secret, show the host and branch involved, and recommend invoking `POST /integrations/pat/verify` (or the UI action) so operators can confirm credentials.
- [x] Preserve operator-modified caches by exiting with a warning if the working tree is dirty and require an explicit `--force` flag to overwrite local edits.

Phase 10 hardened cache refresh by running `git fsck` before sanitization, expanding friendly git error messaging (including masked PAT failures and branch guidance), and adding a force-aware refresh path so operators can explicitly discard local edits while default runs fail fast with remediation steps.

### Phase 11 – Future Considerations

- [x] Decide how to handle cache pruning or storage limits on long-lived hosts.
- [x] Decide whether caches should be snapshotted for auditability after each task run.
- [x] Determine if or when the cache design should expand beyond the default-branch workflow documented here.

Phase 11 now enforces per-project cache quotas and prune intervals during every refresh, captures git bundle snapshots (with retention windows and caps) for auditability, and introduces configurable additional-branch mirroring so caches can track default plus operator-specified branches.

### Immediate Follow-ups

- [x] Update `.env.example`, onboarding docs, and quickstart scripts to drop instructions for setting `PROJECT_LOCAL_PATH` and reference the deterministic cache directory instead. `.env.example` now highlights `PROJECT_CACHE_ROOT`, the README quickstart calls out the deterministic clone, and `scripts/quickstart.sh` prints the cached repo path alongside refresh guidance.
- [x] Remove backend or UI configuration fields that prompt operators for a local project path, including database columns, environment schemas, and settings forms. UI project forms now highlight the deterministic cache rather than requesting a local path, and backend schemas/tests confirm the legacy field is absent.
- [x] Refresh operator notes and troubleshooting guides so maintenance steps target `project-cache/<slug>/repo` (e.g. `scripts/project_cache.py --refresh`). README troubleshooting now references the deterministic cache and the quickstart emits refresh commands.
