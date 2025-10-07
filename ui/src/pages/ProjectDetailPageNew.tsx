import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getProject } from '../api/projects';
import { useProjects } from '../hooks/useProjectsData';
import { usePatStatus } from '../hooks/usePatStatus';
import { ProjectAllowlistStatus, ProjectDetail, ProjectTaskSummary } from '../types';
import { formatTimestamp } from '../utils/time';
import { Card, Button, StatusBadge, Icon } from '../components';
import './ProjectDetailPageNew.css';

const allowlistLabels: Record<ProjectAllowlistStatus, string> = {
  custom: 'Custom',
  empty: 'Empty',
  unknown: 'Unknown',
};

function ProjectDetailPageNew() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericId = Number(projectId);

  const { projects, refreshProjects } = useProjects();

  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fallbackProject = useMemo(() => {
    return projects.find((project) => project.id === numericId) ?? null;
  }, [projects, numericId]);

  useEffect(() => {
    let cancelled = false;

    const fetchDetail = async () => {
      if (!Number.isFinite(numericId)) {
        setError('Project id is invalid');
        return;
      }
      setNotice(null);
      setLoading(true);
      setError(null);
      try {
        const payload = await getProject(numericId);
        if (!cancelled) {
          setDetail(payload);
        }
      } catch (fetchError) {
        if (!cancelled) {
          const message = fetchError instanceof Error ? fetchError.message : 'Failed to load project';
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchDetail();
    return () => {
      cancelled = true;
    };
  }, [numericId]);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  const { status: patStatus, error: patStatusError } = usePatStatus();

  const combinedError = error ?? patStatusError;

  const summary = detail ?? fallbackProject;

  const copyRefreshCommand = async (projectId: number, projectName: string) => {
    const command = `python3 scripts/project_cache.py --refresh --project-id ${projectId}`;
    setNotice(null);
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(command);
        setNotice(`Cache refresh command copied for ${projectName}.`);
        return;
      }
    } catch (clipboardError) {
      setError((prev) => prev ?? 'Unable to copy refresh command automatically.');
    }
    window.prompt('Copy the cache refresh command and run it from the repository root:', command);
  };

  const taskSuccessRate = useMemo(() => {
    if (!detail || detail.recent_tasks.length === 0) return 0;
    const successful = detail.recent_tasks.filter(t => t.status === 'done').length;
    return Math.round((successful / detail.recent_tasks.length) * 100);
  }, [detail]);

  return (
    <div className="layout-page project-detail-page-new">
      <div className="project-detail-hero">
        <button type="button" className="back-button" onClick={() => navigate('/projects')}>
          <Icon type="chevron-left" />
          <span>Back to Projects</span>
        </button>

        {summary && (
          <>
            <div className="hero-content">
              <h1>{summary.name}</h1>
              <p className="hero-description">
                {summary.repository_url ? (
                  <a href={summary.repository_url} target="_blank" rel="noreferrer" className="repo-link">
                    <Icon type="git" />
                    <span>{summary.repository_url.replace(/^https?:\/\//, '')}</span>
                    <Icon type="external-link" />
                  </a>
                ) : (
                  'Configure your project settings and manage tasks'
                )}
              </p>
            </div>

            <div className="hero-actions">
              <Button
                variant="primary"
                onClick={() => navigate('/', { state: { projectId: summary.id } })}
              >
                Submit Task
              </Button>
              <Button
                variant="secondary"
                onClick={() => navigate('/projects', { state: { editProjectId: summary.id } })}
              >
                Edit Project
              </Button>
              <Button
                variant="ghost"
                onClick={() => navigate('/tasks', { state: { projectId: summary.id } })}
              >
                View All Tasks
              </Button>
            </div>
          </>
        )}
      </div>

      {combinedError && <div className="error-banner">{combinedError}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      {loading && <div className="alert alert-info">Loading project information…</div>}

      {summary && detail ? (
        <div className="grid">
          {/* Quick Stats Row */}
          <div className="stats-row">
            <Card className="stat-card">
              <div className="stat-icon-wrapper stat-icon-primary">
                <Icon type="clipboard" />
              </div>
              <div className="stat-content">
                <div className="stat-value">{summary.total_task_count}</div>
                <div className="stat-label">Total Tasks</div>
              </div>
            </Card>

            <Card className="stat-card">
              <div className="stat-icon-wrapper stat-icon-success">
                <Icon type="clock" />
              </div>
              <div className="stat-content">
                <div className="stat-value">{summary.active_task_count}</div>
                <div className="stat-label">Active Tasks</div>
              </div>
            </Card>

            <Card className="stat-card">
              <div className="stat-icon-wrapper stat-icon-info">
                <Icon type="check" />
              </div>
              <div className="stat-content">
                <div className="stat-value">{taskSuccessRate}%</div>
                <div className="stat-label">Success Rate</div>
              </div>
            </Card>

            <Card className="stat-card">
              <div className="stat-icon-wrapper stat-icon-warning">
                <Icon type="git" />
              </div>
              <div className="stat-content">
                <div className="stat-value">{summary.default_branch}</div>
                <div className="stat-label">Default Branch</div>
              </div>
            </Card>
          </div>

          {/* Main Content Grid */}
          <div className="content-grid">
            {/* Configuration Card */}
            <Card className="config-card">
              <h2 className="card-title">
                <Icon type="settings" />
                Configuration
              </h2>
              <div className="config-grid">
                <div className="config-item">
                  <span className="config-label">GitLab Host</span>
                  <span className="config-value">{summary.gitlab_host.replace(/^https?:\/\//, '')}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Project Path</span>
                  <span className="config-value">{summary.gitlab_project_path}</span>
                </div>
                <div className="config-item">
                  <span className="config-label">Cache Status</span>
                  <StatusBadge
                    status={summary.cache_status === 'ready' ? 'configured' : 'pending'}
                    label={summary.cache_status || 'unknown'}
                  />
                </div>
                <div className="config-item">
                  <span className="config-label">Cache Quota</span>
                  <span className="config-value">
                    {summary.cache_quota_mb !== null ? `${summary.cache_quota_mb} MB` : 'Unlimited'}
                  </span>
                </div>
                <div className="config-item">
                  <span className="config-label">Allowlist Status</span>
                  <StatusBadge
                    status={summary.allowlist_status === 'custom' ? 'configured' : 'idle'}
                    label={`${allowlistLabels[summary.allowlist_status]}${summary.allowlist.length > 0 ? ` (${summary.allowlist.length})` : ''}`}
                  />
                </div>
                {summary.allowlist.length > 0 && (
                  <div className="config-item config-item-full">
                    <span className="config-label">Allowlist Domains</span>
                    <div className="domain-tags">
                      {summary.allowlist.map((domain, idx) => (
                        <span key={idx} className="domain-tag">{domain}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="card-actions">
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => copyRefreshCommand(summary.id, summary.name)}
                >
                  <Icon type="copy" />
                  Copy Cache Refresh CLI
                </Button>
              </div>
            </Card>

            {/* Credentials Card */}
            <Card className="credentials-card">
              <h2 className="card-title">
                <Icon type="key" />
                Credentials
              </h2>

              <div className="credential-status-grid">
                <div className="credential-item">
                  <div className="credential-header">
                    <span className="credential-name">GitLab PAT</span>
                    <StatusBadge
                      status={patStatus.configured ? 'configured' : 'missing'}
                      label={patStatus.configured ? 'Configured' : 'Missing'}
                    />
                  </div>
                  {patStatus.configured && (
                    <div className="credential-meta">
                      <span className="meta-item">
                        <Icon type="clock" />
                        {formatTimestamp(patStatus.updated_at)}
                      </span>
                      {patStatus.verification_status === 'verified' && (
                        <span className="meta-item verified">
                          <Icon type="check" />
                          Verified
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <div className="credential-item">
                  <div className="credential-header">
                    <span className="credential-name">ChatGPT Session</span>
                    <StatusBadge
                      status={patStatus.session_configured ? 'active' : 'idle'}
                      label={patStatus.session_configured ? 'Active' : 'Not configured'}
                    />
                  </div>
                  {patStatus.session_configured && patStatus.session_updated_at && (
                    <div className="credential-meta">
                      <span className="meta-item">
                        <Icon type="clock" />
                        {formatTimestamp(patStatus.session_updated_at)}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {patStatus.configured && patStatus.session_configured && (
                <div className="success-indicator">
                  <Icon type="check-circle" />
                  <div>
                    <strong>All Systems Ready</strong>
                    <p>Project is ready for task submission</p>
                  </div>
                </div>
              )}

              {(!patStatus.configured || !patStatus.session_configured) && (
                <div className="card-actions">
                  <Button
                    variant="secondary"
                    size="small"
                    onClick={() => navigate('/settings')}
                  >
                    <Icon type="settings" />
                    Configure Credentials
                  </Button>
                </div>
              )}
            </Card>
          </div>

          {/* Recent Tasks Card */}
          <Card className="tasks-card">
            <div className="card-header-with-action">
              <h2 className="card-title">
                <Icon type="clipboard" />
                Recent Tasks
              </h2>
              {detail.recent_tasks.length > 0 && (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => navigate('/tasks', { state: { projectId: summary.id } })}
                >
                  View All
                </Button>
              )}
            </div>

            {detail.recent_tasks.length === 0 ? (
              <div className="empty-tasks">
                <Icon type="inbox" />
                <p>No tasks yet for this project</p>
                <Button
                  variant="primary"
                  size="small"
                  onClick={() => navigate('/', { state: { projectId: summary.id } })}
                >
                  Create First Task
                </Button>
              </div>
            ) : (
              <div className="tasks-timeline">
                {detail.recent_tasks.map((task: ProjectTaskSummary) => (
                  <div key={task.id} className="timeline-item">
                    <div className="timeline-marker">
                      <StatusBadge status={task.status} />
                    </div>
                    <div className="timeline-content">
                      <div className="timeline-header">
                        <span className="task-id">Task #{task.id}</span>
                        <span className="task-time">{formatTimestamp(task.created_at)}</span>
                      </div>
                      <p className="task-prompt">{task.prompt.substring(0, 100)}{task.prompt.length > 100 ? '...' : ''}</p>
                      <div className="task-meta">
                        {task.branch && (
                          <span className="meta-badge">
                            <Icon type="git" />
                            {task.branch}
                          </span>
                        )}
                        {task.codex_model && (
                          <span className="meta-badge">
                            <Icon type="cpu" />
                            {task.codex_model}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : null}
    </div>
  );
}

export default ProjectDetailPageNew;
