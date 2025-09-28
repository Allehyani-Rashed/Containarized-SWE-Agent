import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getPatStatus, initialPatStatus } from '../api/integrations';
import { getProject } from '../api/projects';
import { useProjects } from '../hooks/useProjectsData';
import { ProjectAllowlistStatus, ProjectDetail, ProjectTaskSummary } from '../types';
import { formatTimestamp } from '../utils/time';

const allowlistLabels: Record<ProjectAllowlistStatus, string> = {
  custom: 'Custom entries',
  empty: 'Empty allowlist',
  unknown: 'No runs yet',
};

function ProjectDetailPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericId = Number(projectId);

  const { projects, refreshProjects } = useProjects();

  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [patStatus, setPatStatus] = useState(initialPatStatus);

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

  useEffect(() => {
    let cancelled = false;

    const fetchPatStatus = async () => {
      try {
        const status = await getPatStatus();
        if (!cancelled) {
          setPatStatus(status);
        }
      } catch (statusError) {
        if (!cancelled) {
          setError((prev) => prev ?? 'Failed to load credential status');
        }
      }
    };

    void fetchPatStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  const summary = detail ?? fallbackProject;

  return (
    <div className="page">
      <header className="page-header">
        <h2>Project Detail</h2>
        <p>Review configuration, credential status, and recent Codex activity.</p>
      </header>

      <button type="button" className="ghost-button" onClick={() => navigate('/projects')}>
        ← Back to Projects
      </button>

      {error && <div className="error-banner">{error}</div>}

      {loading && <div className="notice">Loading project information…</div>}

      {summary ? (
        <section className="panel">
          <h3>{summary.name}</h3>
          <dl className="summary-list">
            <div>
              <dt>Repository</dt>
              <dd>
                {summary.repository_url ? (
                  <a href={summary.repository_url} target="_blank" rel="noreferrer">
                    {summary.repository_url}
                  </a>
                ) : (
                  'Not provided'
                )}
              </dd>
            </div>
            <div>
              <dt>Local Path</dt>
              <dd>{summary.local_path}</dd>
            </div>
            <div>
              <dt>GitLab Host</dt>
              <dd>{summary.gitlab_host || '—'}</dd>
            </div>
            <div>
              <dt>Default Branch</dt>
              <dd>{summary.default_branch}</dd>
            </div>
            <div>
              <dt>Allowlist</dt>
              <dd>{allowlistLabels[summary.allowlist_status]}</dd>
            </div>
            <div>
              <dt>Total Tasks</dt>
              <dd>{summary.total_task_count}</dd>
            </div>
            <div>
              <dt>Active Tasks</dt>
              <dd>{summary.active_task_count}</dd>
            </div>
            <div>
              <dt>Last Activity</dt>
              <dd>{formatTimestamp(summary.last_task_at)}</dd>
            </div>
          </dl>
          <div className="button-row">
            <button type="button" onClick={() => navigate('/projects', { state: { editProjectId: summary.id } })}>
              Edit Project
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => navigate('/tasks/submit', { state: { projectId: summary.id } })}
            >
              Submit Task
            </button>
          </div>
        </section>
      ) : null}

      {detail ? (
        <section className="panel">
          <h3>Credential Status</h3>
          <div className="summary-list">
            <div>
              <dt>Project Codex Token</dt>
              <dd>
                {detail.codex_token_configured ? (
                  <span className="status status-done">Configured</span>
                ) : (
                  <span className="status status-failed">Missing</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Token Updated At</dt>
              <dd>{formatTimestamp(detail.codex_token_updated_at)}</dd>
            </div>
            <div>
              <dt>Session Bundle</dt>
              <dd>
                {patStatus.session_configured ? (
                  <span className="status status-running">Available</span>
                ) : (
                  <span className="status status-failed">Not configured</span>
                )}
              </dd>
            </div>
            <div>
              <dt>GitLab PAT</dt>
              <dd>
                {patStatus.configured ? (
                  <span className="status status-done">Stored</span>
                ) : (
                  <span className="status status-failed">Missing</span>
                )}
              </dd>
            </div>
            <div>
              <dt>PAT Last Verified</dt>
              <dd>{formatTimestamp(patStatus.verification_checked_at)}</dd>
            </div>
          </div>
        </section>
      ) : null}

      {detail ? (
        <section className="panel">
          <h3>Recent Tasks</h3>
          {detail.recent_tasks.length === 0 ? (
            <p className="empty">No tasks recorded for this project yet.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>Branch</th>
                    <th>Model</th>
                    <th>Allowlist Entries</th>
                    <th>Created</th>
                    <th>Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.recent_tasks.map((task: ProjectTaskSummary) => (
                    <tr key={task.id}>
                      <td>{task.id}</td>
                      <td>
                        <span className={`status status-${task.status}`}>{task.status}</span>
                      </td>
                      <td>{task.branch ?? 'Auto-generated'}</td>
                      <td>{task.codex_model ?? 'Default'}</td>
                      <td>{task.allowlist_size}</td>
                      <td>{formatTimestamp(task.created_at)}</td>
                      <td>{formatTimestamp(task.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}

export default ProjectDetailPage;
