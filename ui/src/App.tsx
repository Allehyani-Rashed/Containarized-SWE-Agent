import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import { ProjectsProvider } from './hooks/useProjectsData';
import { PatStatusProvider } from './hooks/usePatStatus';
import PageLoadingSkeleton from './components/PageLoadingSkeleton';
import { useToastAnnouncer } from './components/Toast';
import './App.css';

// Lazy load all page components
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const ProjectDetailPageNew = lazy(() => import('./pages/ProjectDetailPageNew'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const TaskListPage = lazy(() => import('./pages/TaskListPage'));
const TaskSubmitPage = lazy(() => import('./pages/TaskSubmitPage'));
const HelpPage = lazy(() => import('./pages/HelpPage'));

function App() {
  // Connect toast announcements to ARIA live region
  useToastAnnouncer();

  return (
    <Routes>
      <Route
        path="/"
        element={(
          <PatStatusProvider>
            <ProjectsProvider>
              <AppShell />
            </ProjectsProvider>
          </PatStatusProvider>
        )}
      >
        <Route index element={<Suspense fallback={<PageLoadingSkeleton />}><TaskSubmitPage /></Suspense>} />
        <Route path="tasks" element={<Suspense fallback={<PageLoadingSkeleton />}><TaskListPage /></Suspense>} />
        <Route path="projects" element={<Suspense fallback={<PageLoadingSkeleton />}><ProjectsPage /></Suspense>} />
        <Route path="projects/:projectId" element={<Suspense fallback={<PageLoadingSkeleton />}><ProjectDetailPageNew /></Suspense>} />
        <Route path="settings" element={<Suspense fallback={<PageLoadingSkeleton />}><SettingsPage /></Suspense>} />
        <Route path="help" element={<Suspense fallback={<PageLoadingSkeleton />}><HelpPage /></Suspense>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
