import {
  Dispatch,
  FormEvent,
  KeyboardEvent,
  SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useProjects } from '../hooks/useProjectsData';
import {
  Project,
  ProjectAllowlistStatus,
  ProjectCreatePayload,
  ProjectUpdatePayload,
} from '../types';
import { formatTimestamp } from '../utils/time';
import { usePatStatus } from '../hooks/usePatStatus';

type ProjectFormState = {
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  cache_quota_mb: string;
  cache_prune_after_hours: string;
  allowlist: string;
};

type FormErrors = Partial<Record<keyof ProjectFormState, string>>;

type SortKey =
  | 'name'
  | 'gitlab_host'
  | 'default_branch'
  | 'allowlist_status'
  | 'active_task_count'
  | 'last_task_at';

const initialFormState: ProjectFormState = {
  name: '',
  default_branch: 'main',
  gitlab_host: 'https://gitlab.com',
  gitlab_project_path: '',
  cache_quota_mb: '',
  cache_prune_after_hours: '',
  allowlist: '',
};

const allowlistOrder: Record<ProjectAllowlistStatus, number> = {
  custom: 0,
  empty: 1,
  unknown: 2,
};

function normalizeHost(value: string): string {
  const trimmed = value.trim();
  return trimmed.replace(/\/+$/, '');
}

function normalizeProjectPath(value: string): string {
  const trimmed = value.trim();
  return trimmed.replace(/^\/+/, '');
}

function parseAllowlist(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function validateField(field: keyof ProjectFormState, value: string): string | null {
  const trimmed = value.trim();
  switch (field) {
    case 'name':
      return trimmed ? null : 'Name is required';
    case 'default_branch':
      if (!trimmed) {
        return 'Default branch is required';
      }
      if (/\s/.test(trimmed)) {
        return 'Branch cannot contain spaces';
      }
      if (trimmed.startsWith('-')) {
        return 'Branch cannot start with a dash';
      }
      if (trimmed.endsWith('.') || trimmed.endsWith(' ')) {
        return 'Branch cannot end with a dot or space';
      }
      if (trimmed.endsWith('.lock')) {
        return 'Branch cannot end with .lock';
      }
      return null;
    case 'gitlab_host':
      if (!trimmed) {
        return 'GitLab host is required';
      }
      try {
        const parsed = new URL(trimmed);
        if (!['http:', 'https:'].includes(parsed.protocol)) {
          return 'GitLab host must start with http or https';
        }
      } catch (error) {
        return 'Enter a valid GitLab host URL';
      }
      return null;
    case 'gitlab_project_path':
      if (!trimmed) {
        return 'GitLab project path is required';
      }
      if (/\s/.test(trimmed)) {
        return 'Project path cannot include spaces';
      }
      return null;
    case 'cache_quota_mb':
      if (!trimmed) {
        return null;
      }
      if (!/^\d+$/.test(trimmed)) {
        return 'Cache quota must be a non-negative integer (megabytes)';
      }
      return null;
    case 'cache_prune_after_hours':
      if (!trimmed) {
        return null;
      }
      if (!/^\d+$/.test(trimmed)) {
        return 'Prune interval must be a non-negative integer (hours)';
      }
      return null;
    case 'allowlist':
      return null;
    default:
      return null;
  }
}

function ProjectsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    projects,
    isLoading,
    error: projectsError,
    refreshProjects,
    createProject,
    updateProject,
    deleteProject,
    clearError,
  } = useProjects();

  const [pageError, setPageError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [createForm, setCreateForm] = useState<ProjectFormState>(initialFormState);
  const [createErrors, setCreateErrors] = useState<FormErrors>({});
  const [createSubmitting, setCreateSubmitting] = useState(false);

  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [editForm, setEditForm] = useState<ProjectFormState>(initialFormState);
  const [editErrors, setEditErrors] = useState<FormErrors>({});
  const [editSubmitting, setEditSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (!editingProject) {
      setEditForm(initialFormState);
      setEditErrors({});
    }
  }, [editingProject]);

  const { status: patStatus, error: patStatusError, refresh: refreshPatStatus, clearError: clearPatStatusError } =
    usePatStatus();

  const sortedProjects = useMemo(() => {
    const items = [...projects];
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
  }, [projects, sortDirection, sortKey]);

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

  const updateFieldError = (
    field: keyof ProjectFormState,
    value: string,
    setErrors: Dispatch<SetStateAction<FormErrors>>,
  ) => {
    const validation = validateField(field, value);
    setErrors((prev) => {
      const next = { ...prev };
      if (validation) {
        next[field] = validation;
      } else {
        delete next[field];
      }
      return next;
    });
  };

  const handleCreateChange = (field: keyof ProjectFormState, value: string) => {
    setCreateForm((prev) => ({ ...prev, [field]: value }));
    updateFieldError(field, value, setCreateErrors);
  };

  const handleEditChange = (field: keyof ProjectFormState, value: string) => {
    setEditForm((prev) => ({ ...prev, [field]: value }));
    updateFieldError(field, value, setEditErrors);
  };

  const runValidation = (form: ProjectFormState): FormErrors => {
    const next: FormErrors = {};
    (Object.keys(form) as Array<keyof ProjectFormState>).forEach((field) => {
      const message = validateField(field, form[field]);
      if (message) {
        next[field] = message;
      }
    });
    return next;
  };

  const handleCreateSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPageError(null);
    setSuccessMessage(null);

    const errors = runValidation(createForm);
    if (Object.keys(errors).length > 0) {
      setCreateErrors(errors);
      setPageError('Fix the highlighted fields before continuing');
      return;
    }

    const payload: ProjectCreatePayload = {
      name: createForm.name.trim(),
      default_branch: createForm.default_branch.trim(),
      gitlab_host: normalizeHost(createForm.gitlab_host),
      gitlab_project_path: normalizeProjectPath(createForm.gitlab_project_path),
      allowlist: parseAllowlist(createForm.allowlist),
    };

    const cacheQuota = createForm.cache_quota_mb.trim();
    if (cacheQuota) {
      payload.cache_quota_mb = Number(cacheQuota);
    }

    const pruneInterval = createForm.cache_prune_after_hours.trim();
    if (pruneInterval) {
      payload.cache_prune_after_hours = Number(pruneInterval);
    }

    setCreateSubmitting(true);
    try {
      await createProject(payload);
      setCreateForm(initialFormState);
      setCreateErrors({});
      setSuccessMessage('Project registered successfully.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to register project';
      setPageError(message);
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleEditSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingProject) {
      return;
    }

    setPageError(null);
    setSuccessMessage(null);

    const errors = runValidation(editForm);
    if (Object.keys(errors).length > 0) {
      setEditErrors(errors);
      setPageError('Fix the highlighted fields before continuing');
      return;
    }

    const payload: ProjectUpdatePayload = {
      name: editForm.name.trim(),
      default_branch: editForm.default_branch.trim(),
      gitlab_host: normalizeHost(editForm.gitlab_host),
      gitlab_project_path: normalizeProjectPath(editForm.gitlab_project_path),
      allowlist: parseAllowlist(editForm.allowlist),
    };

    const quotaValue = editForm.cache_quota_mb.trim();
    if (quotaValue) {
      payload.cache_quota_mb = Number(quotaValue);
    } else if (editingProject.cache_quota_mb != null) {
      payload.cache_quota_mb = null;
    }

    const pruneValue = editForm.cache_prune_after_hours.trim();
    if (pruneValue) {
      payload.cache_prune_after_hours = Number(pruneValue);
    } else if (editingProject.cache_prune_after_hours != null) {
      payload.cache_prune_after_hours = null;
    }

    setEditSubmitting(true);
    try {
      await updateProject(editingProject.id, payload);
      setSuccessMessage('Project updated successfully.');
      setEditingProject(null);
      setEditForm(initialFormState);
      setEditErrors({});
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update project';
      setPageError(message);
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleEditSelect = useCallback((project: Project) => {
    setEditingProject(project);
    setEditForm({
      name: project.name,
      default_branch: project.default_branch,
      gitlab_host: project.gitlab_host,
      gitlab_project_path: project.gitlab_project_path,
      cache_quota_mb: project.cache_quota_mb == null ? '' : String(project.cache_quota_mb),
      cache_prune_after_hours:
        project.cache_prune_after_hours == null ? '' : String(project.cache_prune_after_hours),
      allowlist: project.allowlist.length ? project.allowlist.join('\n') : '',
    });
    setEditErrors({});
    setPageError(null);
    setSuccessMessage(null);
  }, []);

  useEffect(() => {
    const state = location.state as { editProjectId?: number } | null;
    const targetId = state?.editProjectId;
    if (!targetId) {
      return;
    }

    if (projects.length === 0 && isLoading) {
      return;
    }

    const match = projects.find((project) => project.id === targetId);
    if (match) {
      handleEditSelect(match);
      navigate('.', { replace: true, state: {} });
      return;
    }

    if (!isLoading) {
      setPageError((prev) => prev ?? 'Project not found. It may have been removed.');
      navigate('.', { replace: true, state: {} });
    }
  }, [handleEditSelect, isLoading, location.state, navigate, projects]);

  const handleEditCancel = () => {
    setEditingProject(null);
    setEditForm(initialFormState);
    setEditErrors({});
  };

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

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDirection('asc');
    }
  };

  const renderCredentialBadge = () => {
    if (patStatus.session_configured) {
      return (
        <div className="table-status">
          <span className="status status-running">Session bundle</span>
          {patStatus.session_updated_at ? (
            <div className="meta">Imported {formatTimestamp(patStatus.session_updated_at)}</div>
          ) : null}
        </div>
      );
    }
    return <span className="status status-failed">Missing</span>;
  };

  const renderAllowlistBadge = (status: ProjectAllowlistStatus) => {
    if (status === 'custom') {
      return <span className="status status-done">Custom entries</span>;
    }
    if (status === 'empty') {
      return <span className="status status-pending">Empty</span>;
    }
    return <span className="status status-running">No runs yet</span>;
  };

  const renderCacheCell = (project: Project) => {
    let badgeClass = 'status-running';
    let badgeLabel = project.cache_status || 'unknown';
    if (project.cache_status === 'ready') {
      badgeClass = 'status-done';
      badgeLabel = 'Ready';
    } else if (project.cache_status === 'present') {
      badgeClass = 'status-running';
      badgeLabel = 'Present';
    } else if (project.cache_status === 'missing') {
      badgeClass = 'status-failed';
      badgeLabel = 'Missing';
    }

    const shortCommit = project.last_cache_commit ? project.last_cache_commit.slice(0, 12) : null;

    return (
      <div className="table-status">
        <span className={`status ${badgeClass}`}>{badgeLabel}</span>
        <div className="meta">{project.cache_path}</div>
        {shortCommit ? <div className="meta">HEAD {shortCommit}</div> : null}
      </div>
    );
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

  const sortIndicator = (key: SortKey) => {
    if (key !== sortKey) {
      return null;
    }
    return sortDirection === 'asc' ? ' ▲' : ' ▼';
  };

  const sortableHeaderProps = (key: SortKey) => ({
    role: 'button' as const,
    tabIndex: 0,
    onClick: () => toggleSort(key),
    onKeyDown: (event: KeyboardEvent<HTMLTableCellElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleSort(key);
      }
    },
  });

  return (
    <div className="page">
      <header className="page-header">
        <h2>Projects</h2>
        <p>Register repositories, inspect recent activity, and manage runner credentials.</p>
      </header>

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
      {successMessage && <div className="notice notice-success">{successMessage}</div>}

      <div className="panel-grid">
        <form className="form" onSubmit={handleCreateSubmit} noValidate>
          <h3>Register Project</h3>
          <label>
            Name
            <input
              type="text"
              value={createForm.name}
              onChange={(event) => handleCreateChange('name', event.target.value)}
              required
            />
            {createErrors.name ? <span className="status status-failed">{createErrors.name}</span> : null}
          </label>
          <label>
            Default Branch
            <input
              type="text"
              value={createForm.default_branch}
              onChange={(event) => handleCreateChange('default_branch', event.target.value)}
              required
            />
            {createErrors.default_branch ? (
              <span className="status status-failed">{createErrors.default_branch}</span>
            ) : null}
          </label>
          <label>
            GitLab Host
            <input
              type="text"
              value={createForm.gitlab_host}
              onChange={(event) => handleCreateChange('gitlab_host', event.target.value)}
              required
            />
            {createErrors.gitlab_host ? <span className="status status-failed">{createErrors.gitlab_host}</span> : null}
          </label>
          <label>
            GitLab Project Path
            <input
              type="text"
              value={createForm.gitlab_project_path}
              onChange={(event) => handleCreateChange('gitlab_project_path', event.target.value)}
              required
            />
            <p className="meta">
              The runner clones into <code>project-cache/&lt;slug&gt;/repo</code>; no local path input is required.
            </p>
            {createErrors.gitlab_project_path ? (
              <span className="status status-failed">{createErrors.gitlab_project_path}</span>
            ) : null}
          </label>
          <label>
            Project Allowlist (optional)
            <textarea
              value={createForm.allowlist}
              onChange={(event) => handleCreateChange('allowlist', event.target.value)}
              placeholder={'.example.com\nregistry.npmjs.org'}
              rows={3}
            />
            <p className="field-hint">Enter one domain per line (commas also supported). Leave blank to use only the default deny list.</p>
          </label>
          <div className="field-grid">
            <label>
              Cache Quota (MB)
              <input
                type="number"
                min={0}
                step={1}
                value={createForm.cache_quota_mb}
                onChange={(event) => handleCreateChange('cache_quota_mb', event.target.value)}
                placeholder="Leave blank for unlimited"
              />
              {createErrors.cache_quota_mb ? (
                <span className="status status-failed">{createErrors.cache_quota_mb}</span>
              ) : null}
            </label>
            <label>
              Prune Interval (hours)
              <input
                type="number"
                min={0}
                step={1}
                value={createForm.cache_prune_after_hours}
                onChange={(event) => handleCreateChange('cache_prune_after_hours', event.target.value)}
                placeholder="Leave blank to disable auto-prune"
              />
              {createErrors.cache_prune_after_hours ? (
                <span className="status status-failed">{createErrors.cache_prune_after_hours}</span>
              ) : null}
            </label>
          </div>
          <button type="submit" disabled={createSubmitting}>
            {createSubmitting ? 'Registering…' : 'Register Project'}
          </button>
        </form>

        <div className="panel">
          <h3>Project Overview</h3>
          <div className="table-wrapper">
            {projects.length === 0 ? (
              <p className="empty">{isLoading ? 'Loading projects…' : 'No projects registered yet.'}</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th {...sortableHeaderProps('name')}>
                      Name{sortIndicator('name')}
                    </th>
                    <th>Repository</th>
                    <th>Cache</th>
                    <th {...sortableHeaderProps('gitlab_host')}>
                      Host{sortIndicator('gitlab_host')}
                    </th>
                    <th {...sortableHeaderProps('default_branch')}>
                      Default Branch{sortIndicator('default_branch')}
                    </th>
                    <th {...sortableHeaderProps('allowlist_status')}>
                      Allowlist{sortIndicator('allowlist_status')}
                    </th>
                    <th>Credentials</th>
                    <th {...sortableHeaderProps('last_task_at')}>
                      Last Activity{sortIndicator('last_task_at')}
                    </th>
                    <th {...sortableHeaderProps('active_task_count')}>
                      Active Tasks{sortIndicator('active_task_count')}
                    </th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedProjects.map((project) => (
                    <tr key={project.id}>
                      <td>{project.name}</td>
                      <td>
                        {project.repository_url ? (
                          <a href={project.repository_url} target="_blank" rel="noreferrer">
                            {project.repository_url}
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>{renderCacheCell(project)}</td>
                      <td>{project.gitlab_host || '—'}</td>
                      <td>{project.default_branch}</td>
                      <td>{renderAllowlistBadge(project.allowlist_status)}</td>
                      <td>{renderCredentialBadge()}</td>
                      <td>
                        {project.last_task_at ? (
                          <div className="table-status">
                            <span className={`status status-${project.last_task_status ?? 'pending'}`}>
                              {project.last_task_status ?? 'unknown'}
                            </span>
                            <div className="meta">{formatTimestamp(project.last_task_at)}</div>
                          </div>
                        ) : (
                          <span className="meta">No tasks yet</span>
                        )}
                      </td>
                      <td>{project.active_task_count}</td>
                      <td>
                        <div className="button-row">
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => navigate(`/projects/${project.id}`)}
                          >
                            View
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => handleEditSelect(project)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => copyRefreshCommand(project)}
                          >
                            Copy Refresh CLI
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => handleDelete(project)}
                            disabled={project.active_task_count > 0}
                            title={
                              project.active_task_count > 0
                                ? 'Abort or complete active tasks before deleting'
                                : undefined
                            }
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {editingProject ? (
      <form className="panel form" onSubmit={handleEditSubmit} noValidate>
        <h3>Edit Project – {editingProject.name}</h3>
        <label>
          Name
          <input
            type="text"
            value={editForm.name}
            onChange={(event) => handleEditChange('name', event.target.value)}
            required
          />
          {editErrors.name ? <span className="status status-failed">{editErrors.name}</span> : null}
        </label>
        <label>
          Default Branch
          <input
            type="text"
            value={editForm.default_branch}
            onChange={(event) => handleEditChange('default_branch', event.target.value)}
            required
          />
          {editErrors.default_branch ? (
            <span className="status status-failed">{editErrors.default_branch}</span>
          ) : null}
        </label>
        <label>
          GitLab Host
          <input
            type="text"
            value={editForm.gitlab_host}
            onChange={(event) => handleEditChange('gitlab_host', event.target.value)}
            required
          />
          {editErrors.gitlab_host ? <span className="status status-failed">{editErrors.gitlab_host}</span> : null}
        </label>
        <label>
          GitLab Project Path
          <input
            type="text"
            value={editForm.gitlab_project_path}
            onChange={(event) => handleEditChange('gitlab_project_path', event.target.value)}
            required
          />
          <p className="meta">
            The deterministic cache lives under <code>project-cache/&lt;slug&gt;/repo</code>; refresh with
            <code> scripts/project_cache.py --refresh</code> if needed.
          </p>
          {editErrors.gitlab_project_path ? (
            <span className="status status-failed">{editErrors.gitlab_project_path}</span>
          ) : null}
        </label>
        <label>
          Project Allowlist (optional)
          <textarea
            value={editForm.allowlist}
            onChange={(event) => handleEditChange('allowlist', event.target.value)}
            placeholder={'.example.com\nregistry.npmjs.org'}
            rows={3}
          />
          <p className="field-hint">One domain per line or separated with commas. Leave blank to rely on defaults.</p>
        </label>
        <div className="field-grid">
          <label>
            Cache Quota (MB)
            <input
              type="number"
              min={0}
              step={1}
              value={editForm.cache_quota_mb}
              onChange={(event) => handleEditChange('cache_quota_mb', event.target.value)}
              placeholder="Leave blank for unlimited"
            />
            {editErrors.cache_quota_mb ? (
              <span className="status status-failed">{editErrors.cache_quota_mb}</span>
            ) : null}
          </label>
          <label>
            Prune Interval (hours)
            <input
              type="number"
              min={0}
              step={1}
              value={editForm.cache_prune_after_hours}
              onChange={(event) => handleEditChange('cache_prune_after_hours', event.target.value)}
              placeholder="Leave blank to disable auto-prune"
            />
            {editErrors.cache_prune_after_hours ? (
              <span className="status status-failed">{editErrors.cache_prune_after_hours}</span>
            ) : null}
          </label>
        </div>
        <div className="button-row">
          <button type="submit" disabled={editSubmitting}>
            {editSubmitting ? 'Saving…' : 'Save Changes'}
          </button>
          <button type="button" className="ghost-button" onClick={handleEditCancel}>
            Cancel
          </button>
        </div>
      </form>
      ) : null}

      {deleteTarget ? (
        <div className="panel">
          <h3>Delete Project</h3>
          <p>
            Remove <strong>{deleteTarget.name}</strong> from the runner? Completed task logs will remain
            available, but future runs will no longer reference this project.
          </p>
          {deleteError && <div className="error-banner">{deleteError}</div>}
          <div className="button-row">
            <button type="button" onClick={confirmDelete} disabled={deleteSubmitting}>
              {deleteSubmitting ? 'Deleting…' : 'Confirm Deletion'}
            </button>
            <button type="button" className="ghost-button" onClick={() => setDeleteTarget(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ProjectsPage;
