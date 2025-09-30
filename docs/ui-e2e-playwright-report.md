# Playwright UI E2E Session Notes (2025-09-29)

## Scenarios Exercised
- Navigated core routes (Submit Task, Tasks, Projects, Settings) and verified global navigation state.
- Seeded credentials via Settings → "Store Token" and confirmed backend `/integrations/pat` reflects configuration.
- Worked through Submit Task form validation (empty prompt / missing PAT) and attempted successful submission.
- Seeded tasks via API, then exercised Tasks list filters (status checkboxes, model select, branch filter) and detail drawer (log viewing, abort, delete, log copy).
- Simulated abort + delete flows for running/completed tasks, including abort confirmation modal and delete confirmation.
- Verified drawer lookup control (`Inspect Task ID`) and deep linking by task selection.
- Resized viewport to tablet and phone dimensions to spot responsive rendering issues.
- Populated Projects table and exercised register project form inputs (visual inspection only).

## Notable Findings
1. **Submit Task still blocks submission after storing PAT**
   - Even after storing a PAT successfully (Settings updates and `/integrations/pat` returns `configured: true`), the Submit Task page continues to show `Personal access token missing` and leaves the `Create Task` button disabled. Reproduced across reloads (`/integrations/pat` fetch within page returns configured=true). This prevents any UI-driven task submission once the PAT is set. (Observed at `ui/src/pages/TaskSubmitPage.tsx` rendered state.)

2. **Credential status panel on Submit Task never reflects configured state**
   - The credential status definitions (`<dt>GitLab PAT</dt>`) remain `Missing` even while the backend indicates the PAT is present. Suggests the polling hook or mapping in `TaskSubmitPage` isn’t wiring the `configured` flag to the detail view, compounding issue #1.

3. **Task drawer blocks interacting with filters/table**
   - When the task detail drawer is open, its backdrop intercepts clicks on filters (e.g., attempting to toggle filters or reset fails until closing the drawer). This makes multi-task triage cumbersome. (Snapshot references `TaskListPage` drawer overlay.)

4. **Log copy button lacks user feedback**
   - Clicking "Copy logs" performs the clipboard write but provides no toast/toastless acknowledgement. Accessibility guidance suggests a status toast or tooltip; lacking feedback makes it unclear whether the action succeeded. (Drawer logs section in `TaskListPage`.)

5. **Log stream shows duplicated lines for completed tasks**
   - For done tasks the log panel rendered duplicate entries (`Unable to decrypt stored ChatGPT session bundle` repeated twice). Needs investigation to prevent repeat lines (likely merging live stream + snapshot). Observed on task #3.

6. **Load more button only appears after closing drawer (discoverability issue)**
   - When the drawer is open the Load more control isn’t accessible (covered by drawer). Closing the drawer exposes the button, but the table footer lacks sticky positioning, so users must scroll fully past the drawer-height content. Consider surfacing pagination outside the scroll-blocking area or duplicating controls above the table.

7. **Aborted task banner text persists after completion**
   - After an abort completes, the drawer still shows `Abort requested; waiting for runner to stop` even though status has flipped to `aborted`. Should clear or replace with final-state messaging to avoid confusion.

## Additional Notes
- Vite dev server auto-switched to port 5174 due to 5173 in use; all tests run against `http://127.0.0.1:5174` with API at `http://127.0.0.1:8000`.
- Tasks were seeded via direct API calls/SQLite updates to cover list states (pending → running → done/failed/aborted) given Submit Task blocking bug.
