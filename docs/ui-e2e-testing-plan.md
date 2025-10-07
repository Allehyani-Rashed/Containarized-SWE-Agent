# UI E2E Testing Plan

## Objectives
- Validate that the Containerized Codex Agent UI supports end-to-end workflows for operators managing Codex tasks, projects, and credentials.
- Confirm navigation, data loading, real-time updates, and regression-sensitive flows behave correctly across supported browsers (primary target: Chromium via Playwright).
- Capture high-risk scenarios (credential gating, destructive actions, streaming logs) for repeatable automation and manual spot checks.

## Test Environment & Tooling
- Browser automation: Playwright MCP server (Chromium, headed and headless variants).
- Backend prerequisites: FastAPI API running locally on `http://127.0.0.1:8000` with seeded demo data or fixtures to create projects/tasks.
- Frontend prerequisites: Vite dev server on `http://127.0.0.1:5173` (built with Node 22) or production build served statically.
- Data assumptions:
  - At least one project with valid PAT/codex credentials to verify happy paths.
  - Ability to mock or seed task runs (pending, running, done, failed, aborted) for list/filter coverage.
  - Clipboard access permitted by the test runner to validate copy helpers (with fallbacks captured when blocked).
- The runner image now ships the real Codex CLI; flows that execute tasks should expect `codex exec --cd /work --skip-git-repo-check --yolo -` to appear in logs. Playwright assertions can key off the success/failure markers surfaced in streamed task logs.
- For component ownership and layout details, cross-reference `docs/ui-phase6-release-notes.md`—it documents the current `ProjectsPage`/`ProjectsDetail` architecture backed by `useProjectsData`.

## Global Navigation & Layout
1. **Primary nav renders and routes**
   - Verify AppShell header text, nav items, and default active state.
   - Click each nav item (Submit Task, Tasks, Projects, Settings) and ensure the route/content updates, URL matches, and active class toggles.
   - Direct navigation by URL (enter `/tasks`, `/projects`, `/projects/:id`, `/settings`) loads the correct view without errors.
2. **Unknown routes redirect**
   - Navigate to an unrecognized path (e.g., `/foo`) and confirm redirect to `/` (Submit Task).
3. **Responsive layout smoke**
   - Resize viewport to tablet/phone widths and confirm nav remains accessible (scroll, stacking, or hamburger if implemented).

## Submit Task Page
1. **Initial load state**
   - Projects drop-down populates with available entries (auto-select first project when none chosen).
   - Codex model selector loads defaults; description renders for selected model.
   - PAT warning banner appears when credentials missing; submission button disabled.
2. **Validation errors**
   - Submit with empty prompt → inline/global error `Project and prompt are required`.
   - Remove PAT via backend/API mock → attempt submit; expect `Configure a GitLab PAT before submitting tasks`.
   - Allowlist input trims and ignores empty values (verify payload via network request or backend logs).
3. **Successful submission**
   - Fill in prompt, allowlist, branch, codex model → submit.
   - Observe success notice, prompt clears, `View Task` button appears linking to Tasks page with focus state.
   - Confirm request payload matches UI inputs.
4. **Credential status panel**
   - Entries show formatted timestamps, verification labels, and refresh time updates on timer (15s interval).
   - Simulate verification success/failure to ensure message updates.

## Tasks Page
1. **Initial list & auto refresh**
   - Skeleton/loading indicator on first load; items sorted newest first.
   - Polling (5s) updates statuses; confirm running task transitions to done without manual reload.
2. **Filters panel**
   - Status multi-select toggles chips; filter results accordingly.
   - Codex model drop-down populates; branch text filter applies case-sensitive query.
   - Reset/clear filters returns to full list.
3. **Pagination / Load more**
   - `Load more` fetches next page until limit reached; disabled when no more pages.
4. **Task detail drawer**
   - Click task row to open drawer; verify metadata (branch, model, timestamps, allowlist size, project link).
   - Ensure `View logs` area streams logs with auto-scroll toggle (if present) and manual scroll behavior.
   - Copy logs button writes clipboard success toast; fallback prompt when clipboard blocked.
5. **Abort flow**
   - For running task: open Abort modal, confirm accessibility (focus trap, Esc closes), cancel, then confirm real abort.
   - Verify UI updates to aborted status, action notice displays, and list refreshes.
6. **Delete flow**
   - For completed task: trigger Delete modal, confirm button disables during API call, row removed after success.
   - Error handling when API fails (show error banner, modal stays open).
7. **Log snapshot metadata**
   - Ensure metadata summary renders branch/base branch/model/status/abort flags alongside credential availability timestamps when viewing logs of completed tasks.
8. **Deep linking**
   - Navigate to `/tasks` with state `focusTaskId`; confirm drawer auto-opens and highlighted row scrolls into view.

## Projects Page
All Projects page scenarios target the modern `ProjectsPage.tsx` implementation and the `ProjectsProvider`/`useProjectsData` hook. Legacy backups (`ProjectsPageOld.tsx`) were removed, so selectors should align with the new cards/table markup described in `docs/ui-phase6-release-notes.md`.
1. **Table presentation & sorting**
   - Columns render (host, branch, allowlist status, credential signals, last activity, actions).
   - Toggle sort on each column both directions; data reorders correctly.
2. **Credential gating banners**
   - PAT missing → warning banner linking to docs.
   - PAT present → success info, instructions hidden.
3. **Create project flow**
   - Validate required fields; ensure client-side validation messages per rule (host format, branch naming, numeric quotas).
   - Submit valid payload; success notice, table updates, form resets.
   - Server error simulation returns banner without duplication.
4. **Edit project flow**
   - Click row action to edit; modal/drawer pre-populates data; editing optional fields works.
   - Toggle `Clear Codex Token` checkbox updates payload and warning copy.
   - Save updates list, closes dialog, handles error states gracefully.
5. **Delete project**
   - Trigger delete action; confirm modal requires name/confirmation if applicable; removal updates table.
   - Handle failure (error banner, modal stays open).
6. **Retry refresh control**
   - When project load fails, `Retry` repopulates table.
7. **Navigation hand-off**
   - Clicking project name or detail action routes to `/projects/:id`.

## Project Detail Page
1. **Direct load**
   - Navigate directly with valid `projectId` (from Projects and manual URL). Data loads with spinner while fetching.
2. **Summary section**
   - Validate repository link, cache status badges, allowlist label, counts, and timestamps.
   - Buttons: `Edit Project` opens projects page with state, `Submit Task` routes to Task Submit with preselected project, `Copy Refresh CLI` writes command to clipboard (fallback prompt when blocked).
3. **Credential status**
   - Ensure GitLab PAT + session info reflects current backend state; change backend data to see updates.
4. **Recent tasks table**
   - Rows show truncated commit, allowlist counts, status badges, created/finished timestamps.
   - Empty state message when no tasks.
5. **Error handling**
   - Invalid project ID shows error banner and no crash.

## Further Reading
- `docs/ui-e2e-playwright-roadmap.md` for phased automation milestones.
- `docs/backend-route-catalogue.md` for API payload definitions used in mocked responses.
- `docs/operations/parallel-tasks.md` to understand concurrency controls that the Settings scenarios exercise.

## Settings Page
1. **Credential overview**
   - Status badges reflect PAT/session configuration; tooltips present; warning banner when PAT missing.
2. **Store PAT flow**
   - Require token input; success resets form and updates overview.
   - Server error surfaces as error banner without clearing form.
3. **Verify PAT**
   - Disabled when no PAT; on click, spinner while verifying; success/warning notices captured; failure message includes backend error text.
4. **Clear PAT**
   - Button opens confirmation modal; ensures tasks blocked warning shown afterwards.
5. **Import Session bundle**
    - Paste JSON into textarea or upload file; file picker reads content into form (filename recorded); success updates overview.
    - Reader errors handled gracefully.
6. **Global concurrency**
   - Card loads worker pool metadata (project limit, effective limit, pool size, parallel flag) without crashing when API errors occur.
   - Submitting a positive integer updates the limit, shows success toast/message, and refreshes the displayed values without stale numbers.
   - Invalid input (empty, non-integer, <1) returns inline validation, leaving existing data untouched.
7. **Clear Session**
   - Confirmation modal clears bundle, resets overview; ensures PAT overview unaffected.
8. **Periodic refresh**
   - Verify status auto-refresh (15s) updates timestamps without manual action (mock backend change mid-test).

## Cross-Cutting Quality Checks
- Keyboard accessibility: tab order, focus management in modals/forms, Enter key submission, Escape to close.
- ARIA roles/labels on navigation, tables, and modals.
- Form field persistence: leaving/returning to page resets state appropriately (where intended) and does not leak previous values.
- Error resilience: simulate network failures (500/timeout) for each API call and confirm UI surfaces recoverable state without blank screens.
- Visual regressions: capture Playwright screenshots at key states for baseline comparisons.
- Localization/readability: ensure all user-visible strings are plain ASCII, consistent tone, and punctuation.

## Prioritization
- **Critical path**: Submit Task (happy path + credential gating), Tasks (live monitoring, abort/delete), Projects (create/edit/delete), Settings (store/verify/clear PAT). Run on every release.
- **High importance**: Project detail actions, log streaming metadata, clipboard helpers, filtering/pagination. Run before GA/stable releases.
- **Regression sweep**: Responsive layout, skeleton states, error fallbacks, accessibility smoke. Run periodically or after major UI changes.

## Exit Criteria
- All critical and high-importance scenarios automated via Playwright and passing.
- Failures triaged with reproduction steps logged in findings report.
- Known issues documented with severity/workarounds ahead of release.
