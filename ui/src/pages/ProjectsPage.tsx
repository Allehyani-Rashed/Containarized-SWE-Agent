import {
  useCallback,
  useMemo,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjects } from '../hooks/useProjectsData';
import {
  Project,
  ProjectAllowlistStatus,
} from '../types';
import { usePatStatus } from '../hooks/usePatStatus';
import { ProjectCard, EmptyState, Skeleton } from '../components';
import './ProjectsPage-cards.css';

type SortKey =
  | 'name'
  | 'gitlab_host'
  | 'default_branch'
  | 'allowlist_status'
  | 'active_task_count'
  | 'last_task_at';

const allowlistOrder: Record<ProjectAllowlistStatus, number> = {
  custom: 0,
  empty: 1,
  unknown: 2,
};

function ProjectsPage() {
  const navigate = useNavigate();
  const {
    projects,
    isLoading,
    error: projectsError,
    refreshProjects,
    deleteProject,
    clearError,
  } = useProjects();

  const [pageError, setPageError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [sortKey] = useState<SortKey>('name');
  const [sortDirection] = useState<'asc' | 'desc'>('asc');
  const [retrying, setRetrying] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [hostFilter, setHostFilter] = useState('');
  const [cacheStatusFilter, setCacheStatusFilter] = useState('');

  const { status: patStatus, error: patStatusError, refresh: refreshPatStatus, clearError: clearPatStatusError } =
    usePatStatus();

  const uniqueHosts = useMemo(() => {
    const hosts = new Set(projects.map((p) => p.gitlab_host).filter(Boolean));
    return Array.from(hosts).sort();
  }, [projects]);

  const uniqueCacheStatuses = useMemo(() => {
    const statuses = new Set(projects.map((p) => p.cache_status).filter(Boolean));
    return Array.from(statuses).sort();
  }, [projects]);

  const filteredProjects = useMemo(() => {
    let result = [...projects];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (project) =>
          project.name.toLowerCase().includes(query) ||
          (project.repository_url && project.repository_url.toLowerCase().includes(query)) ||
          (project.gitlab_project_path && project.gitlab_project_path.toLowerCase().includes(query)) ||
          (project.gitlab_host && project.gitlab_host.toLowerCase().includes(query))
      );
    }

    if (hostFilter) {
      result = result.filter((project) => project.gitlab_host === hostFilter);
    }

    if (cacheStatusFilter) {
      result = result.filter((project) => project.cache_status === cacheStatusFilter);
    }

    return result;
  }, [projects, searchQuery, hostFilter, cacheStatusFilter]);

  const sortedProjects = useMemo(() => {
    const items = [...filteredProjects];
    const multiplier = sortDirection === 'asc' ? 1 : -1;

    items.sort((a, b) => {
      const left = a;
      const right = b;
      switch (sortKey) {
        case 'name':
          return left.name.localeCompare(right.name) * multiplier;
        case 'gitlab_host':
          return (left.gitlab_host || '').localeCompare(right.gitlab_host || '') * multiplier;
        case 'default_branch':
          return (left.default_branch || '').localeCompare(right.default_branch || '') * multiplier;
        case 'allowlist_status': {
          const weightLeft = allowlistOrder[left.allowlist_status] ?? 99;
          const weightRight = allowlistOrder[right.allowlist_status] ?? 99;
          if (weightLeft === weightRight) {
            return left.name.localeCompare(right.name) * multiplier;
          }
          return (weightLeft - weightRight) * multiplier;
        }
        case 'active_task_count':
          return (left.active_task_count - right.active_task_count) * multiplier;
        case 'last_task_at': {
          const leftTime = left.last_task_at ? Date.parse(left.last_task_at) : 0;
          const rightTime = right.last_task_at ? Date.parse(right.last_task_at) : 0;
          if (leftTime === rightTime) {
            return left.name.localeCompare(right.name) * multiplier;
          }
          return (leftTime - rightTime) * multiplier;
        }
        default:
          return 0;
      }
    });

    return items;
  }, [filteredProjects, sortDirection, sortKey]);

  const combinedError = pageError || projectsError || patStatusError;

  const handleRetry = useCallback(async () => {
    setRetrying(true);
    setPageError(null);
    setSuccessMessage(null);
    clearError();
    clearPatStatusError();
    try {
      await Promise.all([refreshProjects(), refreshPatStatus()]);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Retry failed';
      setPageError(`Retry failed: ${message}`);
    } finally {
      setRetrying(false);
    }
  }, [clearError, clearPatStatusError, refreshProjects, refreshPatStatus]);

  const handleEditSelect = useCallback((project: Project) => {
    // Navigate to projects page with edit state (will be handled by edit modal in future)
    navigate('/projects', { state: { editProjectId: project.id } });
  }, [navigate]);

  const handleDelete = (project: Project) => {
    setDeleteTarget(project);
    setDeleteError(null);
    setPageError(null);
    setSuccessMessage(null);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteSubmitting(true);
    setDeleteError(null);
    try {
      await deleteProject(deleteTarget.id);
      setSuccessMessage(`Deleted project ${deleteTarget.name}.`);
      setDeleteTarget(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete project';
      setDeleteError(message);
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const copyRefreshCommand = async (project: Project) => {
    const command = `python3 scripts/project_cache.py --refresh --project-id ${project.id}`;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(command);
        setSuccessMessage(`Copied cache refresh command for ${project.name}.`);
        return;
      }
    } catch (copyError) {
      setPageError((prev) => prev ?? 'Unable to copy refresh command; use the prompt instead.');
    }
    window.prompt('Copy the cache refresh command and run it from the repository root:', command);
  };

  const hasActiveFilters = searchQuery || hostFilter || cacheStatusFilter;

  const clearFilters = () => {
    setSearchQuery('');
    setHostFilter('');
    setCacheStatusFilter('');
  };

  return (
    <div className="layout-page projects-page-new">
      {combinedError ? (
        <div className="error-banner">
          <span>{combinedError}</span>
          <button
            type="button"
            className="ghost-button"
            onClick={handleRetry}
            disabled={retrying}
          >
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      ) : null}
      {successMessage && <div className="alert alert-success">{successMessage}</div>}

      {projects.length > 0 && (
        <div className="projects-filters">
          <div className="filter-search-bar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="search-icon">
              <path
                d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM19 19l-4.35-4.35"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <input
              type="text"
              className="filter-search-input"
              placeholder="Search by name, repository, or host..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="search-clear" onClick={() => setSearchQuery('')} aria-label="Clear search">
                ×
              </button>
            )}
          </div>
          <div className="filter-dropdowns">
            <select
              className="filter-select"
              value={hostFilter}
              onChange={(e) => setHostFilter(e.target.value)}
            >
              <option value="">All Hosts</option>
              {uniqueHosts.map((host) => (
                <option key={host} value={host}>
                  {host.replace(/^https?:\/\//, '')}
                </option>
              ))}
            </select>
            <select
              className="filter-select"
              value={cacheStatusFilter}
              onChange={(e) => setCacheStatusFilter(e.target.value)}
            >
              <option value="">All Cache Statuses</option>
              {uniqueCacheStatuses.map((status) => (
                <option key={status} value={status}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
            </select>
            {hasActiveFilters && (
              <button type="button" className="filter-clear-btn" onClick={clearFilters}>
                Clear Filters
              </button>
            )}
          </div>
          <div className="filter-results-info">
            <span>
              Showing {sortedProjects.length} of {projects.length} project{projects.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="projects-grid">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="project-card-skeleton">
              <Skeleton variant="text" width="60%" height="24px" />
              <Skeleton variant="text" width="80%" height="16px" />
              <Skeleton variant="text" width="100%" height="80px" />
              <Skeleton variant="text" width="40%" height="16px" />
            </div>
          ))}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon="folder"
          title="No projects configured"
          description="Add your first project to start running AI agent tasks. Projects connect your GitLab repositories to the Codex runner."
        />
      ) : sortedProjects.length === 0 ? (
        <EmptyState
          icon="alert"
          title="No matching projects"
          description="No projects match your current search and filter criteria. Try adjusting your filters or clearing them to see all projects."
          actionLabel="Clear Filters"
          onAction={clearFilters}
        />
      ) : (
        <div className="projects-grid">
          {sortedProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onView={() => navigate(`/projects/${project.id}`)}
              onEdit={handleEditSelect}
              onDelete={handleDelete}
              onSubmitTask={(proj) => navigate('/', { state: { projectId: proj.id } })}
              onCopyRefreshCLI={copyRefreshCommand}
              patConfigured={patStatus.configured}
              sessionConfigured={patStatus.session_configured}
            />
          ))}
        </div>
      )}

      {deleteTarget ? (
        <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Project</h3>
            <p>
              Remove <strong>{deleteTarget.name}</strong> from the runner? Completed task logs will remain
              available, but future runs will no longer reference this project.
            </p>
            {deleteError && <div className="error-banner">{deleteError}</div>}
            <div className="modal-actions">
              <button type="button" onClick={confirmDelete} disabled={deleteSubmitting} className="btn-danger">
                {deleteSubmitting ? 'Deleting…' : 'Confirm Deletion'}
              </button>
              <button type="button" className="ghost-button" onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ProjectsPage;
