# UI/UX Phase 6 Release Notes

## Highlights
- Task history now exposes status/model/branch filters backed by the paginated `/tasks` endpoint, with loading skeletons and accessible modal flows so operators can triage runs without losing context.
- Log snapshots (`GET /tasks/{id}/logs?follow=0`) include task status, branch, base branch, Codex model, abort-request metadata, and credential availability timestamps; both the Tasks UI and `scripts/test_docker_path.py` surface the snapshot summary ahead of the raw log lines.
- `scripts/test_docker_path.py` prints the snapshot metadata in addition to log lines so dry-run smoke tests mirror the Tasks view.

## Migration Checklist
1. **Project metadata:** ensure each registered project tracks `.projectsanitize` (legacy `.codexignore` entries should be migrated with `python3 scripts/migrate_projectsanitize.py`).
2. **Credential posture:** confirm GitLab PATs and optional ChatGPT session bundles are present before enabling task submission—the dashboard now blocks work when credentials are missing.
3. **Branch/model inputs:** communicate the new `branch_name` and `codex_model` fields to operators; downstream automation now records both fields in task listings, log snapshots, and workspace metadata.
4. **Abort/delete controls:** verify abort endpoints are wired for any custom orchestration tooling—aborted runs emit `status=aborted` and `abort_requested=true` in snapshot responses, while delete operations still require tasks to finish before clearing state.
5. **Project CRUD:** re-sync documentation and onboarding scripts with the multipage Projects dashboard (sortable overview, per-project detail page) so teams retire bespoke tooling.
6. **Automation hooks:** update any log consumers or integrations to read the new snapshot metadata fields; the arrays remain a prefix of the final logs, preserving previously documented guarantees.
