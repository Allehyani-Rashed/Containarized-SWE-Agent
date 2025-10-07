# Parallel Task Execution

Parallel runs are enabled by default. This guide explains the configuration knobs, CLI helpers, observability signals, and rollback plan for tuning concurrency or reverting to serial execution.

## 1. Enable the Worker Pool

1. Pick a global pool size via `WORKER_MAX_CONCURRENCY` (defaults to `10`).
2. Leave `WORKER_ENABLE_PARALLEL` unset (or set it to `1`) to keep the default parallel pool. Export `WORKER_ENABLE_PARALLEL=0` if you need to force serial execution.
3. Optionally tune the per-project fallback with `PROJECT_MAX_CONCURRENCY_DEFAULT` (also defaults to `10`). Project-specific overrides still win.
4. Restart the backend to pick up environment changes.

## 2. Global Project Limit

- The worker enforces a single per-project concurrency limit stored in `/settings/concurrency`. When unset the runner falls back to the `PROJECT_MAX_CONCURRENCY_DEFAULT` environment variable (defaults to `10`).
- Use whichever interface is most convenient:
  - Settings UI → Global Concurrency card.
  - PATCH `/settings/concurrency` with `{ "project_limit": 3 }`.
  - CLI: `scripts/codex settings concurrency` to inspect the current limit and `scripts/codex settings set-concurrency --project-limit 3` to update it (`--project-limit 10` restores the default behaviour).

The worker continues to write the most recent runtime count into `last_active_count` so dashboards can see how many threads were actually busy per project.

## 3. Inspect Runtime State

- CLI status: `scripts/codex tasks status` prints runtime worker counts and configured limits per project (`--json` for raw data, `--project-id` to filter).
- API: GET `/settings/concurrency` returns the configured project limit, effective runtime limit, and worker pool size. GET `/projects` or `/projects/{id}` continues to expose `last_active_count` alongside task totals.
- Metrics: `/metrics` already exports queue depth and active task gauges; combine them with the new database field to catch hotspots.
- Log snapshot metadata (`GET /tasks/{id}/logs?follow=0`) echoes branch/model plus the credential snapshot that was active during the capture. The Tasks drawer in the UI renders the same information alongside the streaming logs.
- UI data flow: `useProjectsData` powers `ProjectsPage.tsx` and the project detail view so operators always see the latest concurrency limits without juggling legacy components. The hook polls the same `/settings/concurrency` endpoint described above.
- For endpoint specifics (query parameters, field descriptions), see `docs/backend-route-catalogue.md`.

## 4. Rollback Plan

1. Clear any project overrides if you want everything to use the fallback: `scripts/codex projects set-limit --project-id <id> --max default`.
2. Set `WORKER_ENABLE_PARALLEL=0` (or remove the variable entirely) and restart the backend to force serial execution. The worker immediately snaps back to single-task mode and keeps honoring queued jobs.
3. Optional: unset `WORKER_MAX_CONCURRENCY`/`PROJECT_MAX_CONCURRENCY_DEFAULT` to restore the defaults.

Projects and tasks retain their history regardless of the flag. The UI displays the stored limits even if the runtime is serial so operators can re-enable parallelism later without reconfiguring each project.

## 5. Quick Checklist

- [ ] Decide on a global pool size, export `WORKER_MAX_CONCURRENCY`, and ensure `WORKER_ENABLE_PARALLEL` is unset (or explicitly `1`) unless you need serial execution.
- [ ] Audit projects and set per-project limits where necessary (UI/API/CLI).
- [ ] Update dashboards/alerts to include `last_active_count` and the CLI status output.
- [ ] Communicate the rollback steps (unset flag → restart) to operators.
- [ ] (Optional) Extend smoke tests – `python3 scripts/test_docker_path.py` prints credentials and concurrency metadata for quick verification.

Once the flag is flipped the worker will happily schedule multiple Codex runs at once while keeping per-project throttles and the existing audit trail intact.
