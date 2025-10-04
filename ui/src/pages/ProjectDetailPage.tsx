import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getProject } from '../api/projects';
import { useProjects } from '../hooks/useProjectsData';
import { usePatStatus } from '../hooks/usePatStatus';
import { ProjectAllowlistStatus, ProjectDetail, ProjectTaskSummary } from '../types';
import { formatTimestamp } from '../utils/time';
import { Card, Button, StatusBadge, InfoList, InfoItem, EmptyState } from '../components';
import './ProjectDetailPage.css';

const allowlistLabels: Record<ProjectAllowlistStatus, string> = {
  custom: 'Custom',
  empty: 'Empty',
  unknown: 'Unknown',
};

function ProjectDetailPage() {
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

  return (
    <div className="page project-detail-page">
      <div className="project-detail-header">
        <button type="button" className="back-link" onClick={() => navigate('/projects')}>
          ← Back to Projects
        </button>
        <div className="page-title-section">
          <h1>{summary?.name || 'Project Detail'}</h1>
          <p className="page-subtitle">Detailed view and management for the selected project</p>
        </div>
        {summary && (
          <div className="action-buttons-row">
            <Button
              variant="primary"
              icon={
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M11.333 2L14 4.667M1.333 14.667l2.89-2.89L1.333 14.667zm2.89-2.89L13.334 2.667c.368-.367.552-.551.621-.762a1 1 0 000-.81c-.069-.21-.253-.395-.621-.762l-.667-.666c-.368-.368-.552-.552-.762-.621a1 1 0 00-.81 0c-.21.069-.395.253-.762.621L1.223 9.778l3 3 3-3z"
                    stroke="currentColor"
                    strokeWidth="1.333"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              }
              onClick={() => navigate('/projects', { state: { editProjectId: summary.id } })}
            >
              Edit Project
            </Button>
            <Button
              variant="success"
              icon={
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M8 1v14M1 8h14"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              }
              onClick={() => navigate('/', { state: { projectId: summary.id } })}
            >
              Submit Task
            </Button>
            <Button
              variant="secondary"
              onClick={() => copyRefreshCommand(summary.id, summary.name)}
            >
              Copy Refresh CLI
            </Button>
          </div>
        )}
      </div>

      {combinedError && <div className="error-banner">{combinedError}</div>}
      {notice && <div className="notice notice-success">{notice}</div>}

      {loading && <div className="notice">Loading project information…</div>}

      {summary && detail ? (
        <div className="project-detail-layout">
          <div className="left-column">
            <Card>
              <h2 className="section-title">Project Summary</h2>
              <InfoList columns={2}>
                <InfoItem
                  label="Repository"
                  value={
                    summary.repository_url ? (
                      <a href={summary.repository_url} target="_blank" rel="noreferrer" className="repo-link">
                        {summary.repository_url.replace(/^https?:\/\//, '')}
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ marginLeft: '4px' }}>
                          <path
                            d="M10 6.667V10a.667.667 0 01-.667.667H2A.667.667 0 011.333 10V2.667A.667.667 0 012 2h3.333M7.333 1.333H10.667V4.667M5 7L10.667 1.333"
                            stroke="currentColor"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </a>
                    ) : (
                      'Not provided'
                    )
                  }
                />
                <InfoItem label="GitLab Host" value={summary.gitlab_host || '—'} />
                <InfoItem label="Default Branch" value={summary.default_branch} />
                <InfoItem
                  label="Allowlist Status"
                  value={
                    <StatusBadge
                      status={summary.allowlist_status === 'custom' ? 'configured' : 'idle'}
                      label={`${allowlistLabels[summary.allowlist_status]}${summary.allowlist.length > 0 ? ` ${summary.allowlist.length} domains` : ''}`}
                    />
                  }
                />
                <InfoItem
                  label="Cache Quota"
                  value={summary.cache_quota_mb !== null ? `${summary.cache_quota_mb} MB` : 'Unlimited'}
                />
                <InfoItem
                  label="Prune Interval"
                  value={
                    summary.cache_prune_after_hours !== null
                      ? `${summary.cache_prune_after_hours} hours`
                      : 'Disabled'
                  }
                />
                <InfoItem label="Total Tasks" value={summary.total_task_count} />
                <InfoItem label="Active Tasks" value={summary.active_task_count} />
              </InfoList>

              <div className="allowlist-section">
                <h3 className="subsection-title">Allowlist Domains</h3>
                <p className="allowlist-domains">
                  {summary.allowlist.length ? summary.allowlist.join(', ') : 'None configured'}
                </p>
              </div>
            </Card>

            <Card>
              <h2 className="section-title">Recent Tasks</h2>
              {detail.recent_tasks.length === 0 ? (
                <EmptyState
                  icon="clipboard"
                  title="No tasks yet"
                  description="This project has no recorded tasks. Submit a task to see it appear here."
                  actionLabel="Create Task"
                  onAction={() => navigate('/submit')}
                />
              ) : (
                <div className="table-wrapper">
                  <div className="table-responsive">
                    <table>
                      <thead>
                        <tr>
                          <th className="sticky-column">ID</th>
                          <th>Status</th>
                          <th className="hide-mobile">Branch</th>
                          <th className="hide-tablet">Base</th>
                          <th className="hide-mobile">Model</th>
                          <th className="hide-tablet">Cache</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.recent_tasks.map((task: ProjectTaskSummary) => (
                          <tr key={task.id}>
                            <td className="sticky-column">#{task.id}</td>
                            <td>
                              <StatusBadge status={task.status} />
                            </td>
                            <td className="hide-mobile">{task.branch ?? 'Auto-generated'}</td>
                            <td className="hide-tablet">{task.target_branch ?? 'Default'}</td>
                            <td className="hide-mobile">{task.codex_model ?? 'Default'}</td>
                            <td className="hide-tablet">{task.cache_commit ? task.cache_commit.slice(0, 7) : '—'}</td>
                            <td>{formatTimestamp(task.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Card>
          </div>

          <div className="right-column">
            <Card>
              <h2 className="section-title">Credential Status</h2>

              <div className="credential-section">
                <h3 className="credential-title">GitLab PAT</h3>
                <InfoList columns={1}>
                  <InfoItem
                    label=""
                    value={
                      <StatusBadge
                        status={patStatus.configured ? 'configured' : 'missing'}
                        label={patStatus.configured ? 'Configured' : 'Not configured'}
                      />
                    }
                  />
                  <InfoItem
                    label="Last updated"
                    value={formatTimestamp(patStatus.updated_at) || 'Never'}
                  />
                  <InfoItem label="Updated by" value="operator" />
                  <InfoItem
                    label="PAT Verification"
                    value={
                      <StatusBadge
                        status={patStatus.verification_status === 'verified' ? 'verified' : 'pending'}
                        label={patStatus.verification_status === 'verified' ? 'Verified' : 'Not verified'}
                      />
                    }
                  />
                  <InfoItem
                    label="Host"
                    value={patStatus.verification_host || summary.gitlab_host || 'gitlab.com'}
                  />
                  {patStatus.verification_checked_at && (
                    <InfoItem
                      label="Verified"
                      value={formatTimestamp(patStatus.verification_checked_at)}
                    />
                  )}
                </InfoList>
              </div>

              <div className="credential-section">
                <h3 className="credential-title">ChatGPT Session</h3>
                <InfoList columns={1}>
                  <InfoItem
                    label=""
                    value={
                      <StatusBadge
                        status={patStatus.session_configured ? 'active' : 'idle'}
                        label={patStatus.session_configured ? 'Active' : 'Not configured'}
                      />
                    }
                  />
                  {patStatus.session_configured && (
                    <>
                      <InfoItem label="" value="Session bundle configured" />
                      <InfoItem label="Updated by" value="operator" />
                    </>
                  )}
                </InfoList>
              </div>

              {patStatus.configured && patStatus.session_configured && (
                <div className="success-banner">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M13.333 4L6 11.333 2.667 8"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <div>
                    <strong>All Systems Ready</strong>
                    <p>Project is ready for task submission</p>
                  </div>
                </div>
              )}
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ProjectDetailPage;
