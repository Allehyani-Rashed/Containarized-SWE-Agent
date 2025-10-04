# Codex Operator UI Redesign Brief

## Objective
Modernize the Containerized Agent Runner UI across all operator-facing views while preserving existing backend flows, form payloads, and navigation. The React/Vite frontend communicates with FastAPI endpoints; redesigned layouts must remain compatible with current data contracts.

## Scope
- Refresh visual language (layout, color, typography, component styling) for:
  - Submit Task
  - Tasks (including log drawer)
  - Projects
  - Project Detail
  - Settings (Credentials & Integrations)
- Allow updates to navigation, card structure, and component styling, provided all existing fields, labels, and actions remain present.
- Support desktop-first layouts with responsive behaviors down to tablet widths. Mobile parity is a stretch goal; document priorities if additional work is required.
- Uphold accessibility targets (WCAG AA contrast, non-color status cues, keyboard-friendly controls and focus states).

## Design Context
Current UI uses a dark navy gradient background (#0f172a → #172554), frosted glass panels, Inter typography, hero header "Containerized Agent Runner", and a left-hand navigation stack (Submit Task, Tasks, Projects, Settings) that collapses to top-aligned links on narrow viewports. Status is conveyed through pill badges (`done`, `failed`, `running`, `pending`, `aborted`, `live`). Error banners, success notices, skeleton loaders, empty-state copy, and disabled buttons are already wired into orchestration logic and must remain visually distinct.

## Screen Requirements

### Submit Task
- Hero header + lead copy.
- **Task Submission** panel:
  - Project selector (populated from `/projects`).
  - Base branch input with async suggestions (`listProjectBranches` datalist).
  - Optional branch name textbox.
  - Required merge request title (max 240 chars).
  - Prompt textarea for task instructions.
  - Model dropdown (`listCodexModels`) with default fallbacks.
  - Reasoning effort select (`low|medium|high`) plus explanatory hint text.
  - Warning notice when GitLab PAT missing.
  - Primary button `Create Task`; disabled during submission or missing dependencies.
- **Credential Status** panel:
  - Shows PAT configured/missing, last update, verification status, timestamps, active project name.
  - Ghost button linking to the newly created task (navigates to Tasks with focus).
  - Success message `Task {id} created...`; inline error banner reuses global style.

### Tasks
- Intro header + description.
- **Filters** panel:
  - Status chips for `pending`, `running`, `done`, `failed`, `aborted` (multi-select).
  - Model dropdown (All models + specific options).
  - Branch substring text field.
  - `Apply filters` (secondary button) and `Reset` (ghost button). Disabled states reflect unchanged drafts.
- **Task History** table panel:
  - Columns: ID, Project, Status badge, Created, Finished, Agent Invocation text, Model, Reasoning, Branch, Base Branch, Merge Request link.
  - Skeleton table during load (5 rows, 11 columns) and empty-state copy when no results.
  - `Load more` button for pagination; highlights when API window limit reached.
  - Active row highlight (ties into drawer selection).
- **Task Detail** panel:
  - Numeric input for direct task lookup + submit button.
  - Reminder banner when a task is selected; ghost button reopens drawer if closed.
- **Task Drawer** (slides from right, fixed position):
  - Header: Task ID, status pill, optional `Abort requested` badge, created timestamp, project name.
  - Action buttons: `Abort task` (pending/running), `Delete task` (terminal statuses); disabled states for pending confirmations.
  - Detail grid: prompt text, branch, base branch, agent model, reasoning effort, MR URL, agent runtime metadata.
  - Logs section: live indicator, `Copy logs` button with success/failure feedback, log metadata (status at capture, branch, base branch, model, reasoning, abort flag), scrollable monospace log output, empty-state copy.
  - Confirmation overlays for abort/delete with focus trap, descriptive copy, primary danger button + ghost cancel.

### Projects
- Header + description.
- Two-column layout (stacked on small screens).
- **Register Project** form card:
  - Fields: Name, Default branch, GitLab host URL, GitLab project path, optional allowlist textarea (one domain per line or comma-separated), optional cache quota (MB) and prune interval (hours).
  - Inline validation errors and helper text for repo path and allowlist formatting.
  - Submit button `Register Project` with loading state.
- **Project Overview** card:
  - Table with sortable columns: Name, Host, Default Branch, Allowlist status (`custom|empty|unknown`), Last Activity (status badge + timestamp), Active Tasks.
  - Additional columns: Repository URL, cache status summary, credential badge.
  - Row actions: `View` (routes to detail), `Edit` (prefills edit panel), `Copy Refresh CLI` (copies `python3 scripts/project_cache.py --refresh --project-id <id>`), `Delete` (disabled when active_task_count > 0).
  - Error banner with `Retry` button when API errors bubble up, success notice after create/update/delete.
- **Edit Project** panel (conditionally visible):
  - Mirrors create form fields, includes `Save Changes` (loading state) and `Cancel` (ghost) buttons.
- **Delete Project** confirmation panel:
  - Shows project name, warning copy, `Confirm Deletion` and `Cancel` buttons; surfaces errors inline.

### Project Detail
- Back button (`← Back to Projects`).
- Summary panel:
  - Fields: Repository link, GitLab host, default branch, allowlist status label, allowlist domains (comma-separated), cache quota/prune interval, total tasks, active tasks, last activity timestamp.
  - Buttons: `Edit Project` (routes to Projects with state), `Submit Task` (prefills root form), `Copy Refresh CLI`.
- Credential status panel (mirrors Settings overview values, including PAT/session configured and verification metadata).
- Recent tasks panel:
  - Table columns: ID, Status badge, Branch, Base Branch, Model, Reasoning effort, Cache commit short hash, Created, Finished.
  - Empty-state copy when no tasks.
  - Loading and error messages already provided by backend.

### Settings (Credentials & Integrations)
- Header copy emphasizing credential management.
- Global error banner, success notices for PAT and session actions, verification notice (success or warning).
- **Credential Overview** panel:
  - Summary rows for GitLab PAT (configured/missing, last update timestamp, updated-by), PAT verification status + host + timestamp + error copy, ChatGPT session status, session updated-by, active credential label (“ChatGPT session bundle” or “None”), status refreshed timestamp.
  - Warning notice when PAT missing; helper copy explaining write-only handling.
- **GitLab Personal Access Token** panel:
  - Form: password field (token), optional actor, `Store Token` button.
  - Action block: `Verify PAT access` (disabled when token missing), `Clear PAT` (danger button triggering modal), explanatory hint about task impact.
  - Modal: title "Clear GitLab PAT?", optional "Cleared By" input, ghost cancel + danger confirm (`Clear Token`), includes consequence copy.
- **ChatGPT Session Bundle** panel:
  - Form: textarea for JSON bundle, file upload (shows filename), optional actor input, `Import Session` button.
  - Helper copy for CLI commands (macOS, Linux, Windows) to copy bundle, caution regarding CLI installation.
  - `Clear Session Bundle` button (danger) triggering modal with optional actor input and warning about Docker-backed runs.
  - Modal mirrors PAT clear flow (`Clear Session`).

## Functional Constraints
- Do not change form field names, button labels, or validation logic; backend expects current payloads.
- Navigation routes (`/`, `/tasks`, `/projects`, `/projects/:id`, `/settings`) must remain discoverable.
- Preserve log streaming UI contract (fixed drawer, live indicator, auto-scroll, copy feedback) so existing code continues to map to design.
- Maintain clear affordances for status badges, filter chips, disabled controls, and notices without relying on color alone.
- Ensure tables remain legible and actionable at narrower breakpoints (consider horizontal scroll wrappers or responsive stacking).

## Deliverables
1. High-fidelity Figma (or equivalent) frames for each screen (desktop primary) plus responsive notes for tablet/mobile transformations.
2. Updated component library specs covering navigation shell, hero, panels/cards, form controls, tables, chips, badges, modals, drawers, log viewer, buttons, skeleton loaders, notices.
3. Interaction documentation: hover/focus/active states, loading/disabled behavior, error/success messaging, log streaming indicator motion, modal and drawer transitions, focus management cues.
4. Risk & assumptions list highlighting any brand decisions (palette, typography), unresolved information architecture questions, or backend constraints requiring validation before implementation.

Use this brief to craft a cohesive, contemporary visual system that supports operator efficiency, emphasizes task status clarity, and slots into the current FastAPI + React workflow without additional backend development.
