# Project-Scoped GitLab PAT Migration Plan

> **Status (2025-09-26): Archived.** After Phase 12 the team formalised a single global PAT plus encrypted ChatGPT session bundles. Project-scoped GitLab tokens were intentionally retired, so this plan is preserved only for historical context.

## Current Credential Strategy
- A single GitLab PAT is stored plaintext in the orchestrator database for local deployments, sourced from `.env` or the Settings → Integrations UI. `scripts/codex pat store|clear` (plus ChatGPT import helpers) manage the credential, and the Settings page offers a `Verify PAT access` action while blocking task submission when the PAT is missing.
- ChatGPT session bundles are encrypted at rest and staged into the runner workspace only for task execution. The runner clears the base64 env once the bundle is written to `~/.codex/auth.json`.
- Task logs, API responses, and Docker helper scripts surface credential status (configured/verified timestamps) so operators can audit runs without adopting per-project PAT management.

## Why Project-Scoped PATs Were Dropped
- Local operators overwhelmingly share a single GitLab project; duplicating secrets per project created more rotation overhead without stronger containment because the runner still executes inside the same sandbox.
- Phase 11–13 improvements (credential verification endpoints, Settings copy, PAT lifecycle blocking) eliminated the pain points that originally motivated per-project PAT storage.
- Tinyproxy allowlists and queue concurrency controls now gate egress per project, which addressed the audit concerns that sparked this plan.

Given those changes, we no longer plan to pursue per-project PAT storage. The phase breakdown below remains as a reference in case future deployments reintroduce multi-tenant requirements.

---

## Archived Phase Outline (Historical Reference)

### Phase 0 – Discovery & Alignment
1. Audit current credential flows: catalogue how `/integrations/pat`, `scripts/codex pat *`, runner startup, and task submission read/write the global PAT (env + persistence).
2. Confirm regulatory/security goals for per-project storage (encryption at rest, rotation expectations, access scoping) with stakeholders.
3. Document acceptance criteria: no global PAT fallback, backward-compatible CLI UX, and seamless migrations for existing operators.
4. Produce a sequence diagram of current vs. desired PAT retrieval during task execution to align backend/UI/runner expectations.

### Phase 1 – Data Model & Storage Strategy
1. Decide storage location for project PATs (e.g., new `project_gitlab_pat` table keyed by project id with encrypted secret + metadata).
2. Define encryption handling (reuse ChatGPT bundle vault or introduce per-project key wrapping; clarify key management + rotation APIs).
3. Update SQLModel definitions and Alembic migrations to add the new table/fields, including `created_at`, `updated_at`, `last_verified_at`, and optional `verification_status` fields.
4. Design migration script to import the existing global PAT into every project flagged as sharing it, storing provenance to support rollback.

### Phase 2 – Backend API & Service Updates
1. Introduce REST endpoints under `/projects/:id/pat` for store/clear/read/verify, mirroring the semantics of the current global endpoints while scoping access control.
2. Update task submission flow so runner selection loads PAT from the project record; remove global PAT lookups and return actionable errors if a project lacks credentials.
3. Adjust background workers: ensure docker preflight, branch rewinds, and GitLab MR automation fetch PAT from the project-specific store and mask in logs.
4. Update audit logging to record project id + operator identity when PAT operations occur.
5. Add rate limiting/CSRF enforcement adjustments for the new endpoints if required.

### Phase 3 – CLI & Runner Adjustments
1. Extend `scripts/codex` to accept `--project` flags for PAT operations, defaulting to interactive project selection when omitted.
2. Update runner bootstrap scripts (`scripts/quickstart.sh`, `runner/bin/finish_task.sh`) to request PATs per project, falling back to dry-run placeholders only when explicitly configured.
3. Ensure the docker path and smoke tests (`scripts/test_docker_path.py`, `make smoke-docker`) seed project PATs via the new APIs and fail when missing.
4. Remove references to `RUNNER_GIT_DRY_RUN` global PAT shortcuts, replacing them with project-level fixtures to keep dry-runs functional.

### Phase 4 – UI & UX Changes
1. Modify Settings → Integrations to remove the global PAT card; introduce project-scoped PAT forms within `/projects/:id` detail pages.
2. Update the Projects dashboard to surface PAT status (stored/verified/stale) per row, including bulk indicators for missing credentials.
3. Adjust task submission UI to block runs when the selected project lacks a PAT and link directly to the new credential form.
4. Refresh copy, tooltips, and docs links to explain project-level storage and rotation workflows.
5. Add success/error toasts aligned with the new API responses and ensure accessibility compliance (focus management, ARIA attributes).

### Phase 5 – Migration & Rollout
1. Write a one-shot migration command that copies the existing global PAT into each project, recording completion markers to avoid duplication.
2. Provide rollback tooling to clear or reapply the global PAT if unforeseen issues arise prior to full rollout.
3. Stage dual-write/dual-read period: continue serving PATs from the global store while populating project-level records, then flip read path to project-only once validation completes.
4. Ensure documentation for operators covers the cut-over timeline, required actions, and verification steps.

### Phase 6 – Testing & Validation
1. Expand backend unit/integration tests to cover new endpoints, permission checks, and task submission failures when PATs are absent.
2. Add runner integration tests (local + Docker path) that simulate multiple projects with distinct PATs and confirm MR branching uses the correct token.
3. Implement UI tests (Vitest/Playwright, if available) for PAT create/verify/clear flows and project dashboard status badges.
4. Perform security reviews: confirm secrets never leak via logs, responses, or snapshots; verify Tinyproxy allowlists cover new GitLab hosts if per-project tokens differ.
5. Conduct load/regression testing to ensure PAT verification and task start times remain acceptable.

### Phase 7 – Documentation & Operational Updates
1. Update README, Quickstart, and operator runbooks to describe project-scoped PAT management, including CLI/UI paths and API references.
2. Refresh `local-codex-mr_todo_prompt.md` (or successor docs) with QA steps for credential handling.
3. Provide troubleshooting guides for common issues (e.g., PAT revoked, project missing credentials, verify failures).
4. Announce the change internally with migration timelines, testing results, and support contacts.

### Phase 8 – Post-Cutover Monitoring
1. Monitor task dashboard and logs for PAT-related failures after rollout; add alerts for repeated credential errors per project.
2. Collect operator feedback on UX pain points and iterate quickly on copy or API ergonomics.
3. Schedule periodic credential health checks (e.g., nightly PAT verification) and track metrics to ensure tokens stay fresh.
4. Sunset unused global PAT code paths and delete environment variables/secrets once confidence is established.
