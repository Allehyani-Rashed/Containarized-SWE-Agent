import { Outlet, useLocation } from 'react-router-dom';
import { useMemo } from 'react';
import { useProjects } from '../hooks/useProjectsData';
import Sidebar from './Sidebar';
import Breadcrumb, { BreadcrumbItem } from './Breadcrumb';
import './AppShell.css';

const pageNames: Record<string, string> = {
  '/': 'Task Submission',
  '/tasks': 'Task Management',
  '/projects': 'Projects',
  '/analytics': 'Analytics & Insights',
  '/settings': 'Settings',
  '/help': 'Help & Documentation',
};

function AppShell() {
  const location = useLocation();
  const { projects } = useProjects();

  // Get page title from pathname, handling project detail pages
  const getPageTitle = () => {
    if (location.pathname.startsWith('/projects/')) {
      return 'Project Details';
    }
    return pageNames[location.pathname] || 'Containerized Agent Runner';
  };

  const pageTitle = getPageTitle();

  // Generate breadcrumbs based on current pathname
  const breadcrumbs = useMemo<BreadcrumbItem[]>(() => {
    const path = location.pathname;

    // Home page - no breadcrumbs
    if (path === '/') {
      return [{ label: 'Home', path: '/' }];
    }

    // Tasks page
    if (path === '/tasks') {
      return [
        { label: 'Home', path: '/' },
        { label: 'Tasks' },
      ];
    }

    // Projects list page
    if (path === '/projects') {
      return [
        { label: 'Home', path: '/' },
        { label: 'Projects' },
      ];
    }

    // Project detail page
    if (path.startsWith('/projects/')) {
      const projectId = path.split('/')[2];
      const project = projects.find(p => p.id === Number(projectId));
      const projectName = project?.name || `Project #${projectId}`;

      return [
        { label: 'Home', path: '/' },
        { label: 'Projects', path: '/projects' },
        { label: projectName },
      ];
    }

    // Settings page
    if (path === '/settings') {
      return [
        { label: 'Home', path: '/' },
        { label: 'Settings' },
      ];
    }

    // Analytics page
    if (path === '/analytics') {
      return [
        { label: 'Home', path: '/' },
        { label: 'Analytics' },
      ];
    }

    // Help page
    if (path === '/help') {
      return [
        { label: 'Home', path: '/' },
        { label: 'Help' },
      ];
    }

    // Default fallback
    return [{ label: 'Home', path: '/' }];
  }, [location.pathname, projects]);

  const getPageSubtitle = () => {
    if (location.pathname === '/') {
      return 'Submit tasks, monitor execution, and manage your AI-powered development workflow';
    }
    if (location.pathname === '/tasks') {
      return 'View task history, monitor execution logs, and manage your agent workflow runs';
    }
    if (location.pathname === '/projects') {
      return 'Register repositories, manage credentials, and configure project-specific settings';
    }
    if (location.pathname === '/analytics') {
      return 'View task metrics, success rates, and performance insights across projects';
    }
    if (location.pathname === '/settings') {
      return 'Configure GitLab PAT, ChatGPT session credentials, and integration settings';
    }
    if (location.pathname === '/help') {
      return 'Get started, find answers to common questions, and troubleshoot issues';
    }
    if (location.pathname.startsWith('/projects/')) {
      return 'View project details, recent tasks, and manage cache and credentials';
    }
    return 'Monitor task execution, view logs, and manage your AI agent workflows';
  };

  const pageSubtitle = getPageSubtitle();

  return (
    <div className="app-shell-new">
      <Sidebar />

      <div className="app-content">
        <header className="app-header">
          <div className="app-header-main">
            <Breadcrumb items={breadcrumbs} />
            <h1 className="app-header-title">{pageTitle}</h1>
            <p className="app-header-subtitle">{pageSubtitle}</p>
          </div>
          <div className="app-header-actions">
            <div className="system-status">
              <span className="status-indicator status-online"></span>
              <span className="status-text">System Online</span>
            </div>
            <button className="icon-button" aria-label="Notifications" title="Notifications">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/>
              </svg>
            </button>
            <button className="icon-button" aria-label="Help" title="Help">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd"/>
              </svg>
            </button>
          </div>
        </header>

        <main className="app-main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppShell;
