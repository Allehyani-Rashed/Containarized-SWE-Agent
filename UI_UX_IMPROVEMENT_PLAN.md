# UI/UX Improvement Plan - Containerized SWE Agent

**Goal:** Improve UI/UX score from **8.1/10 → 9.5/10**
**Duration:** 6 weeks
**Last Updated:** 2025-01-08

---

## 📊 Current State Assessment

### Overall Scores by Category
- **Design System**: 9/10 ⭐ Excellent
- **Component Architecture**: 8/10 ⭐ Very Good
- **Navigation & User Flows**: 8.5/10 ⭐ Excellent
- **Accessibility**: 8/10 ⭐ Very Good
- **Performance**: 4/10 ⚠️ Needs Improvement
- **Error Handling**: 7/10 ✅ Good
- **Forms & Validation**: 9/10 ⭐ Exemplary
- **Layout & Information Architecture**: 7.2/10 ✅ Good

### Critical Issues Identified
1. No code splitting or lazy loading (288KB monolithic bundle)
2. No error boundaries (uncaught errors crash entire app)
3. Missing WCAG Level A compliance (skip links, modal semantics)
4. No toast notification system for transient feedback
5. Generic error messages with no recovery guidance

---

## Phase 1: Critical Fixes (Week 1-2) 🚨

### Setup Tasks

- [ ] Install dependencies
  ```bash
  npm install --save-dev bundlesize rollup-plugin-visualizer
  npm install web-vitals
  ```

- [ ] Create/verify environment files
  ```bash
  # .env.development
  VITE_API_BASE_URL=http://127.0.0.1:8000

  # .env.test
  VITE_API_BASE_URL=http://localhost:8000
  ```

- [ ] Configure bundlesize in package.json
  ```json
  {
    "bundlesize": [
      {
        "path": "dist/assets/index-*.js",
        "maxSize": "60 KB",
        "compression": "gzip"
      },
      {
        "path": "dist/assets/TaskListPage-*.js",
        "maxSize": "30 KB",
        "compression": "gzip"
      },
      {
        "path": "dist/assets/ProjectsPage-*.js",
        "maxSize": "30 KB",
        "compression": "gzip"
      },
      {
        "path": "dist/assets/react-vendor-*.js",
        "maxSize": "40 KB",
        "compression": "gzip"
      }
    ]
  }
  ```

### Performance Optimization

- [ ] **1.1: Implement route-based code splitting**
  - File: `ui/src/App.tsx`
  - Convert all page imports to `lazy(() => import(...))`
  - Add Suspense boundary with PageLoadingSkeleton fallback
  - Expected: 30-40% reduction in initial bundle size

- [ ] **1.2: Configure Vite manual vendor chunking**
  - File: `ui/vite.config.ts`
  - Add rollupOptions with manualChunks for react/react-dom/react-router-dom
  - Set chunkSizeWarningLimit to 500
  - Add rollup-plugin-visualizer for bundle analysis
  - Coexistence: Vendor chunks only, pages handled by lazy()

- [ ] **1.3: Create bundle analysis scripts**
  - Add `npm run analyze` script
  - Add `npm run bundle-check` script
  - Configure CI to fail if chunks exceed limits

- [ ] **1.4: Measure baseline metrics**
  - Run `npm run build` and record current gzipped sizes
  - Document: Total bundle, per-route sizes, vendor size
  - Create spreadsheet to track before/after

### Error Boundaries

- [ ] **2.1: Create ErrorBoundary component**
  - File: `ui/src/components/ErrorBoundary.tsx`
  - Implement class component with componentDidCatch
  - Create PageErrorFallback with "Go Home" and "Retry" buttons
  - Export both ErrorBoundary and fallback component

- [ ] **2.2: Integrate ErrorBoundary into pages**
  - Wrap inside each page component (NOT around Routes)
  - Files: TaskListPage.tsx, ProjectsPage.tsx, SettingsPage.tsx, TaskSubmitPage.tsx, ProjectDetailPageNew.tsx, HelpPage.tsx
  - Preserves global providers (PatStatus, Projects, AppShell)
  - Users can navigate away without page reload

### Accessibility Fixes (WCAG Level A/AA)

- [ ] **3.1: Add skip link**
  - File: `ui/src/components/AppShell.tsx`
  - Add `<a href="#main-content" className="skip-link">Skip to main content</a>`
  - Add `id="main-content"` to main element
  - Style: Position absolute, hidden until focused

- [ ] **3.2: Fix modal ARIA attributes**
  - File: `ui/src/pages/ProjectsPage.tsx` (delete modal)
  - Add `role="dialog"`, `aria-modal="true"`
  - Add `aria-labelledby` and `aria-describedby`
  - Apply to ConfirmationModal.tsx as template

- [ ] **3.3: Add table captions**
  - File: `ui/src/pages/taskList/components/TaskTable.tsx`
  - Add `<caption className="sr-only">` with descriptive text
  - Include filter state in caption when applicable

- [ ] **3.4: Update API client with retry logic**
  - File: `ui/src/api/client.ts`
  - Add API_BASE constant from `import.meta.env.VITE_API_BASE_URL`
  - Add ERROR_MESSAGES mapping for user-friendly text
  - Implement retry logic in request() wrapper
  - Retry only 5xx/network errors, fail fast on 4xx
  - Exponential backoff: 1s, 2s, 4s

### Acceptance Criteria

- [ ] Initial entry chunk < 60KB gzipped (currently ~85KB)
- [ ] Per-route chunks < 30KB gzipped
- [ ] Bundle analyzer shows vendor chunk properly separated
- [ ] Error boundary catches and displays errors without crashing app
- [ ] Skip link appears on Tab and jumps to main content
- [ ] All modals have proper ARIA attributes (axe-core passes)
- [ ] API errors show user-friendly messages
- [ ] 5xx errors retry automatically (verify in network tab)

---

## Phase 2: User Feedback System (Week 3) ✨

### Toast System with Accessibility

- [ ] **4.1: Create ToastProvider component**
  - File: `ui/src/components/Toast.tsx`
  - Integrate react-hot-toast
  - Create AriaLiveAnnouncer component with queue-based state
  - Implement SSR/test guards (typeof window !== 'undefined')
  - Export accessibleToast() function

- [ ] **4.2: Integrate ToastProvider into App**
  - File: `ui/src/main.tsx` or `ui/src/App.tsx`
  - Wrap application in <ToastProvider>
  - Ensure single aria-live region for all announcements

- [ ] **4.3: Replace success alerts with toasts**
  - Quick actions: Abort, Clone, Retry tasks
  - Copy operations: Logs, CLI commands
  - Secondary successes: Verify PAT, update concurrency
  - Keep persistent banners for credential errors

### Persistent Banner Classification

- [ ] **4.4: Document feedback strategy**
  - Create FEEDBACK_PATTERNS.md
  - List what stays as persistent banner (credential errors, page-level errors)
  - List what becomes toast (quick actions, copy feedback, transient errors)
  - Rule: Action required = persistent; acknowledgment = toast

- [ ] **4.5: Update TaskSubmitPage**
  - Replace success card with toast after task creation
  - Keep PAT warning banner (persistent)
  - Add toast for branch fetch failures (transient)

- [ ] **4.6: Update SettingsPage**
  - Replace success alerts with toasts
  - Keep error banners for critical failures
  - Add toast for copy CLI command

- [ ] **4.7: Update TaskListPage**
  - Add toasts for abort/retry/clone actions
  - Keep credential banner (persistent)
  - Add toast for log copy operation

### Navigation Improvements

- [ ] **5.1: Create dedicated task detail page**
  - File: `ui/src/pages/TaskDetailPage.tsx`
  - Route: `/tasks/:taskId`
  - Full-page version of drawer content
  - Add breadcrumb: Home → Tasks → Task #42
  - Keep drawer for quick access from table

- [ ] **5.2: Add project switcher**
  - Component: `ui/src/components/ProjectSwitcher.tsx`
  - Location: AppShell header or Sidebar
  - Dropdown with recent projects
  - Persist last-used project in localStorage

- [ ] **5.3: Add task count badges to sidebar**
  - Show pending/running task count
  - Polling or WebSocket for real-time updates
  - Visual indicator: badge on "Tasks" nav link

### Acceptance Criteria

- [ ] Toast system shows success/error with auto-dismiss (3-5s)
- [ ] Screen reader announces all toasts via aria-live
- [ ] Rapid toasts queue properly (no race conditions)
- [ ] Persistent banners remain for credential errors
- [ ] Task detail page accessible via /tasks/:id URL
- [ ] All user actions have visual feedback

---

## Phase 3: Component Refinement (Week 4-5) 🔧

### Refactor Large Components

- [ ] **6.1: Extract custom hooks**
  - File: `ui/src/hooks/useDebouncedValue.ts`
  - File: `ui/src/hooks/useBranchSearch.ts`
  - File: `ui/src/hooks/useFormValidation.ts`
  - Move logic from TaskSubmissionCard and other components

- [ ] **6.2: Refactor TaskSubmissionCard**
  - Current: 290 lines
  - Target: ~150 lines
  - Extract BranchSelector component (50 lines)
  - Extract validation to taskFormValidation.ts (30 lines)
  - Use extracted hooks

- [ ] **6.3: Refactor TaskTable**
  - Current: 284 lines
  - Target: ~180 lines
  - Extract TaskTableRow component (60 lines)
  - Extract TaskActions component (40 lines)
  - Keep pagination logic in main table

- [ ] **6.4: Extract reusable components**
  - ConfirmationModal → move to ui/src/components/
  - CredentialBanner → generalize to Banner component
  - TaskLookupPanel → SearchPanel component

### Eliminate Hardcoded Values

- [ ] **7.1: Audit hardcoded colors**
  - Run: `rg "#[0-9a-fA-F]{3,6}" ui/src --type css | grep -v "var(--"`
  - Fix 8 instances in Card.css, InfoPanel.css
  - Map to design tokens: #fb923c → var(--orange-400)

- [ ] **7.2: Audit hardcoded spacing**
  - Run: `rg ":\s*\d+px" ui/src --type css | grep -v "var(--"`
  - Fix high-priority: inputs/buttons (25 instances)
  - Document exceptions for component-specific spacing

- [ ] **7.3: Add missing design tokens**
  - Add --shadow-focus-success if needed
  - Add intermediate spacing tokens (--space-7, --space-14) if patterns emerge
  - Document new tokens in design-system.css

### Acceptance Criteria

- [ ] No components > 200 lines (except Icon.tsx)
- [ ] All custom hooks in dedicated files
- [ ] < 20 hardcoded colors (currently 8)
- [ ] < 30 hardcoded spacing values in high-visibility components
- [ ] Reusable components properly extracted to ui/src/components/

---

## Phase 4: Design System Enhancement (Week 6) 🎨

### Visual Consistency

- [ ] **8.1: Standardize card density**
  - All cards: padding: var(--space-8) on desktop
  - Responsive: --space-6 at 1280px, --space-4 at 768px
  - Create .card-comfortable and .card-compact variants
  - Update: ProjectCard, InfoPanel, TaskSubmissionCard

- [ ] **8.2: Reduce label emphasis**
  - Change stat labels: semibold → medium (500)
  - Remove text-transform: uppercase
  - Remove excessive letter-spacing
  - Apply to: ProjectCard stats, TaskTable headers, meta labels

- [ ] **8.3: Consolidate credential status**
  - Remove: Task Submit sidebar credential panel
  - Add: AppShell header persistent banner (if critical creds missing)
  - Keep: Settings page full detail
  - Result: Single source of truth visible globally

- [ ] **8.4: Improve ProjectCard stats layout**
  - Change from 2-column to 3-column grid (or horizontal flex)
  - Merge "Last Activity" into stats section
  - Reduce footer action buttons (combine into dropdown menu)

### Font Optimization

- [ ] **9.1: Reduce font weights**
  - Current: Inter (300,400,500,600,700) + JetBrains (400,500,600)
  - Target: Inter (400,500,600) + JetBrains (400,500)
  - Update: ui/index.html font link
  - Add display=swap to prevent FOIT

- [ ] **9.2: Audit font weight usage**
  - Replace font-weight: 700 with 600 (if used)
  - Replace font-weight: 300 with 400
  - Document weight usage: 400=body, 500=labels, 600=headings

### Fluid Typography (Optional Enhancement)

- [ ] **9.3: Add clamp() for responsive scaling**
  - Example: `font-size: clamp(1.5rem, 4vw, 3rem);`
  - Apply to page titles, section headings
  - Test at 320px and 2560px viewports

### Acceptance Criteria

- [ ] All cards have consistent padding across pages
- [ ] Label weights reduced (max semibold for page titles only)
- [ ] Credential status shown in one persistent location
- [ ] Font file size reduced by ~20KB
- [ ] FCP improves by 100-200ms (measure with Lighthouse)

---

## Phase 5: Monitoring & Optimization (Week 6) 📊

### Page Visibility API Integration

- [ ] **10.1: Update usePatStatus hook**
  - File: `ui/src/hooks/usePatStatus.tsx`
  - Add visibilitychange event listener
  - Stop polling when document.hidden
  - Resume with immediate refresh when visible

- [ ] **10.2: Update useTaskList hook**
  - File: `ui/src/pages/taskList/useTaskList.ts`
  - Apply same pattern as usePatStatus
  - Reduce server load from background tabs

- [ ] **10.3: Update log polling**
  - File: `ui/src/pages/taskList/useTaskLogs.ts`
  - Pause EventSource when tab hidden
  - Resume when tab becomes visible

### Web Vitals Tracking

- [ ] **11.1: Add Web Vitals measurement**
  - File: `ui/src/utils/webVitals.ts`
  - Import onCLS, onFCP, onFID, onLCP, onTTFB
  - Log to console in development only
  - Optionally: POST to backend analytics endpoint

- [ ] **11.2: Integrate into application**
  - File: `ui/src/main.tsx`
  - Call measureWebVitals() on mount
  - Track baseline before Phase 1 optimizations
  - Measure improvement after all phases

### Search Input Debouncing

- [ ] **12.1: Add debouncing to ProjectsPage search**
  - Use extracted useDebouncedValue hook
  - Delay: 300ms
  - Apply to search input onChange

- [ ] **12.2: Add debouncing to TaskListPage filters**
  - Apply to branch name filter (if text input)
  - Reduce filter submissions on rapid typing

### Acceptance Criteria

- [ ] Polling stops when tab hidden (verify in network tab)
- [ ] Polling resumes when tab visible
- [ ] Web Vitals logged in console (dev mode only)
- [ ] Search inputs debounce (verify no API call on each keystroke)
- [ ] LCP < 2.5s, FID < 100ms (Lighthouse audit)

---

## Phase 6: Testing & Verification 🧪

### Bundle Size Verification

- [ ] **13.1: Run production build**
  ```bash
  npm run build
  ls -lh dist/assets/*.js
  ```

- [ ] **13.2: Verify chunk sizes**
  - Index chunk < 60KB gzipped
  - Per-route chunks < 30KB gzipped
  - Vendor chunk < 40KB gzipped

- [ ] **13.3: Run bundle analyzer**
  ```bash
  npm run analyze
  ```
  - Verify vendor chunk properly separated
  - Check for duplicate dependencies
  - Identify largest modules

- [ ] **13.4: Run bundlesize check**
  ```bash
  npm run bundle-check
  ```
  - All checks should pass
  - CI integration working

### Accessibility Audit

- [ ] **14.1: Automated axe-core scan**
  ```bash
  npx axe http://localhost:5173 --dir ./axe-results
  ```
  - Zero violations (or document exceptions)
  - Run on all major pages: /, /tasks, /projects, /settings

- [ ] **14.2: Lighthouse accessibility audit**
  ```bash
  lighthouse http://localhost:5173 --view
  ```
  - Accessibility score > 95
  - All WCAG AA criteria met

- [ ] **14.3: Keyboard navigation test**
  - Tab through entire application
  - All interactive elements reachable
  - Visible focus indicators
  - Skip link works (Tab on page load)
  - Modal focus trap works
  - Drawer Escape key closes

- [ ] **14.4: Screen reader testing**
  - Test with VoiceOver (macOS) or NVDA (Windows)
  - Task submission flow: form labels, errors, success toast
  - Task list: table navigation, row selection
  - Modal dialogs: title announced, focus trapped
  - Toast announcements: all messages heard, no race conditions

- [ ] **14.5: High contrast mode**
  - Enable system high contrast
  - All text readable
  - Focus indicators visible
  - Status badges distinguishable

### Performance Testing

- [ ] **15.1: Lighthouse performance audit**
  - LCP < 2.5s (target: < 2.0s)
  - FID < 100ms (target: < 50ms)
  - CLS < 0.1 (target: < 0.05)
  - TTFB < 800ms

- [ ] **15.2: Network throttling test**
  - Chrome DevTools → Network → Slow 4G
  - Initial load time acceptable
  - Task list loads progressively
  - Images/fonts don't block rendering

- [ ] **15.3: Verify retry logic**
  - Kill API server → trigger 500 error
  - Verify 3 retry attempts with exponential backoff
  - Check console for retry messages
  - Verify user-friendly error message shown

### Responsive Design Testing

- [ ] **16.1: Breakpoint verification**
  - Test at 320px, 480px, 640px, 768px, 1024px, 1280px, 1920px
  - Sidebar transforms to horizontal nav at 1024px
  - Cards collapse appropriately
  - No horizontal scroll (except tables)

- [ ] **16.2: Real device testing**
  - iOS Safari (iPhone)
  - Android Chrome
  - iPad/tablet
  - Test portrait and landscape orientations

- [ ] **16.3: Touch target verification**
  - All buttons > 44×44px on mobile
  - Adequate spacing between interactive elements
  - No accidental taps

### Error Handling Verification

- [ ] **17.1: Test error boundary**
  - Inject error in component (throw new Error('test'))
  - Verify fallback UI shows
  - Verify "Go Home" and "Retry" buttons work
  - Verify global providers not torn down

- [ ] **17.2: Test toast vs banner classification**
  - Quick action (abort task) → toast ✓
  - Copy operation → toast ✓
  - Credential missing → persistent banner ✓
  - API failure → persistent banner ✓
  - Verify no overlap/duplication

- [ ] **17.3: Test user-friendly error messages**
  - 401 error → "Session expired" message
  - 403 error → PAT scope guidance
  - 500 error → "Server error" with retry suggestion
  - Network error → "Check connection" message

### Documentation

- [ ] **18.1: Update README with new scripts**
  - Document `npm run analyze`
  - Document `npm run bundle-check`
  - Document environment variables (VITE_API_BASE_URL)

- [ ] **18.2: Create FEEDBACK_PATTERNS.md**
  - Document persistent banner use cases
  - Document toast use cases
  - Provide examples for future features

- [ ] **18.3: Update ACCESSIBILITY.md** (create if missing)
  - Document skip link implementation
  - Document screen reader testing checklist
  - Document keyboard shortcuts

### Final Acceptance

- [ ] All Phase 1-5 tasks completed
- [ ] Bundle size targets met (60KB entry, 30KB routes)
- [ ] WCAG 2.1 Level AA compliance (axe-core 0 violations)
- [ ] Lighthouse scores: Performance > 90, Accessibility > 95
- [ ] Screen reader testing passed
- [ ] All error scenarios have proper feedback
- [ ] No regressions in existing functionality

---

## Success Metrics

### Performance (Before → After)
- Initial bundle: 85KB gzipped → **< 60KB gzipped** ✅
- Route chunks: N/A (monolithic) → **< 30KB each** ✅
- LCP: ~3.5s → **< 2.5s** ✅
- FCP: ~2.0s → **< 1.5s** ✅

### Accessibility (Before → After)
- Lighthouse score: ~85 → **> 95** ✅
- axe-core violations: 5-8 → **0** ✅
- WCAG Level: Partial AA → **Full AA** ✅

### User Experience (Before → After)
- Error recovery: Generic messages → **User-friendly + guidance** ✅
- Feedback: Inconsistent → **Toast + persistent banner system** ✅
- Navigation: Drawer-only → **Shareable URLs (/tasks/:id)** ✅

### Code Quality (Before → After)
- Large components: 3 components > 200 lines → **0** ✅
- Hardcoded values: 93 spacing + 8 colors → **< 50 total** ✅
- Error handling: No boundaries → **Page-level boundaries** ✅

---

## Risk Mitigation

### Potential Issues

1. **Bundle size target unattainable**
   - Mitigation: Profile first, adjust target if needed based on actual vendor size
   - Fallback: Accept 70KB entry if vendor chunk is 45KB

2. **Breaking changes to existing features**
   - Mitigation: Comprehensive testing after each phase
   - Rollback: Keep feature flags for major changes

3. **Accessibility regressions**
   - Mitigation: Run axe-core after each component change
   - CI: Add automated accessibility checks

4. **Performance degradation from new features**
   - Mitigation: Measure Web Vitals before and after each phase
   - Revert: If LCP increases > 10%, investigate before proceeding

---
