# GitLab Project Cache Release Notes

## Highlights
- Removed the legacy `PROJECT_LOCAL_PATH` environment variable and associated configuration paths; all cache operations now rely exclusively on the deterministic cache directory returned by `project_cache_repo_path`.

## Migration Checklist
1. **Infrastructure templates:** delete any `PROJECT_LOCAL_PATH` entries from deployment manifests, container env blocks, or automation scripts to avoid setting unused variables.
2. **Credential sync jobs:** ensure env-sync flows no longer attempt to read or propagate `PROJECT_LOCAL_PATH`; the canonical cache location is resolved from `PROJECT_CACHE_ROOT` when overrides are required.
3. **Runtime validation:** restart long-lived services after purging the variable so process supervisors pick up the trimmed environment.

## Operator Guidance
- Run `python3 scripts/project_cache.py --bootstrap` for every registered project to seed `project-cache/<slug>/repo` before enabling automated refreshes. The CLI respects `RUNNER_GIT_DRY_RUN=1` for air-gapped rehearsals.
- Manual clones on local disks are ignored by the orchestrator. Future maintenance should rely on `scripts/project_cache.py --bootstrap/--refresh` instead of editing `.env` or exporting `PROJECT_LOCAL_PATH`.
- Share the updated quickstart with operators so they know existing `.env` files must drop `PROJECT_LOCAL_PATH`; cached repository health now lives entirely under the deterministic cache root. The helper now prints the resolved path and points to `scripts/project_cache.py --refresh` for future repairs.
