import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import { ProjectsProvider } from './hooks/useProjectsData';
import ProjectsPage from './pages/ProjectsPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import SettingsPage from './pages/SettingsPage';
import TaskListPage from './pages/TaskListPage';
import TaskSubmitPage from './pages/TaskSubmitPage';
import './App.css';

function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={(
          <ProjectsProvider>
            <AppShell />
          </ProjectsProvider>
        )}
      >
        <Route index element={<Navigate to="/tasks/submit" replace />} />
        <Route path="tasks/submit" element={<TaskSubmitPage />} />
        <Route path="tasks" element={<TaskListPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/tasks/submit" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
