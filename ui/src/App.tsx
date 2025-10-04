import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import { ProjectsProvider } from './hooks/useProjectsData';
import { PatStatusProvider } from './hooks/usePatStatus';
import ProjectsPage from './pages/ProjectsPage';
import ProjectDetailPageNew from './pages/ProjectDetailPageNew';
import SettingsPage from './pages/SettingsPage';
import TaskListPage from './pages/TaskListPage';
import TaskSubmitPage from './pages/TaskSubmitPage';
import HelpPage from './pages/HelpPage';
import './App.css';

function App() {
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
        <Route index element={<TaskSubmitPage />} />
        <Route path="tasks" element={<TaskListPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailPageNew />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="help" element={<HelpPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
