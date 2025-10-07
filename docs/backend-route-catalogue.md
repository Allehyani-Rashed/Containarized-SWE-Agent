# FastAPI Route Catalogue

The previous monolithic `app/app/main.py` bundled helper functions, router wiring, and endpoint logic for the orchestrator. The routes are now grouped into domain modules under `app/app/api/`. The table below summarises each router, its focus, and the key helpers it depends on.

| Router module | Path prefix | Primary responsibilities | Shared dependencies & helpers |
| --- | --- | --- | --- |
| `api.integrations` | `/integrations` | GitLab PAT lifecycle, ChatGPT session bundle management, PAT verification | `integrations.py` credential CRUD, `services.audit` for actor normalisation + audit events, optional `TaskQueueManager` notifications |
| `api.settings` | `/settings` | Project concurrency settings (read/update) | `settings_store.py` persistence, `services.audit.normalize_actor`, `TaskQueueManager` pool metadata |
| `api.models` | `/models` | Codex model catalogue exposure | `codex_models.py` (iterators, defaults) |
| `api.projects` | `/projects` | Project CRUD, GitLab branch listing, detail metrics | `services.validators` for branch/host/path checks, `services.projects` metrics + cache summaries, `services.gitlab` token + URL helpers, `allowlist.py`, `services.audit`, `services.workspaces.remove_workspace`, `TaskQueueManager` (deletes) |
| `api.tasks` | `/tasks` | Task submission, listing, detail, abort/delete, log streaming | `services.validators` (branch/model/title/change mode), `services.tasks.task_to_read`, `integrations.get_gitlab_pat_status`, `services.audit`, `services.workspaces.remove_workspace`, `TaskQueueManager` orchestration |
| `api.diagnostics` | _none_ | Health and Prometheus metrics | `prometheus_client.generate_latest` |

Shared dependencies are provided via `app/app/dependencies.py`, which now owns the global `TaskQueueManager` accessor originally declared in `main.py`. Helpers that were previously private to `main.py` have been relocated into `app/app/services/` packages:

- `services.validators` centralises branch, MR title, and Codex model validation logic used by both project and task flows.
- `services.tasks.task_to_read` hydrates `TaskRead` payloads with default change mode, Codex model defaults (via `codex_models.py`), and credential snapshots from the worker.
- `services.projects` generates cache metadata, allowlist summaries, and audit-friendly repository URLs without duplicating logic across endpoints.
- `services.audit` provides audit event persistence plus actor/reason trimming, replacing bespoke copies in `main.py` and `integrations.py`.
- `services.gitlab` wraps GitLab branch URL construction and PAT lookup so both project endpoints and credential flows operate on the same helpers.
- `services.workspaces` owns the repository/workspace root constants and cleanup helper referenced by task/project deletion paths.

The new module boundaries keep route handlers thin while still reusing existing integrations and settings utilities. Metrics, health, and concurrency wiring remain exposed through the same HTTP paths, ensuring UI and worker tests continue to exercise the same behaviour.
