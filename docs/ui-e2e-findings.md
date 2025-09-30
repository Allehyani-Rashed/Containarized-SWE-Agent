# UI E2E Findings

## Direct URL navigation returns JSON instead of SPA shell
- **Status**: Resolved
- **Severity**: High (breaks deep links and Playwright E2E coverage)
- **Environment**: Local dev server (`npm --prefix ui run dev` serving on `http://127.0.0.1:5173`), Playwright 1.55.1, Chromium 140.0.7339.186
- **Reproduction**:
  1. Launch the UI dev server (`make ui` or `npm --prefix ui run dev`).
  2. In Playwright (or any browser), navigate directly to `http://127.0.0.1:5173/tasks`.
  3. Observe that the response body is raw JSON (task list payload) and `document.contentType` is `application/json`.
  4. Repeat for `http://127.0.0.1:5173/projects` and `http://127.0.0.1:5173/settings`.
- **Expected**: The SPA router should render the AppShell and corresponding page content regardless of direct navigation, matching the behavior when arriving via in-app links.
- **Actual** *(pre-fix)*: The dev server returned the backend API response for these routes, so the React app never mounted. Headless Playwright runs therefore failed (`page.waitForSelector('text=Task History')` timed out) and operators could not deep-link to `/tasks` without first loading `/`.
- **Evidence**:
  - `document.contentType` logged as `application/json` for `/tasks` before the fix (see the original `node tmp/ui-e2e-tasks.js` run).
  - Headless screenshot `tmp/tasks-headless.png` shows the JSON payload that previously rendered.
- **Resolution**: Added an HTML-accepting bypass to the Vite dev proxy in `ui/vite.config.ts` so requests for SPA routes return `/index.html` instead of proxying to the FastAPI backend. Re-ran `node tmp/ui-e2e-tasks.js` to confirm the Tasks page now renders under direct navigation.
