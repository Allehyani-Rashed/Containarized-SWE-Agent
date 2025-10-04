import { Project } from '../types';
import { formatTimestamp } from '../utils/time';
import StatusBadge from './StatusBadge';
import Button from './Button';
import Icon from './Icon';
import './ProjectCard.css';

export interface ProjectCardProps {
  project: Project;
  onView: (project: Project) => void;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  onSubmitTask: (project: Project) => void;
  onCopyRefreshCLI: (project: Project) => void;
  patConfigured: boolean;
  sessionConfigured: boolean;
}

function ProjectCard({
  project,
  onView,
  onEdit,
  _onDelete,
  onSubmitTask,
  _onCopyRefreshCLI,
  patConfigured,
  sessionConfigured,
}: ProjectCardProps) {
  const renderCacheStatus = () => {
    let status: 'configured' | 'pending' | 'missing' = 'pending';
    let label = project.cache_status || 'unknown';

    if (project.cache_status === 'ready') {
      status = 'configured';
      label = 'Ready';
    } else if (project.cache_status === 'present') {
      status = 'pending';
      label = 'Present';
    } else if (project.cache_status === 'missing') {
      status = 'missing';
      label = 'Missing';
    }

    return <StatusBadge status={status} label={label} />;
  };

  const renderAllowlistStatus = () => {
    if (project.allowlist_status === 'custom') {
      return <StatusBadge status="configured" label={`${project.allowlist.length} domains`} />;
    }
    if (project.allowlist_status === 'empty') {
      return <StatusBadge status="idle" label="Default only" />;
    }
    return <StatusBadge status="idle" label="Unknown" />;
  };

  const renderCredentialStatus = () => {
    const bothConfigured = patConfigured && sessionConfigured;
    const oneConfigured = patConfigured || sessionConfigured;

    if (bothConfigured) {
      return <StatusBadge status="verified" label="Ready" />;
    } else if (oneConfigured) {
      return <StatusBadge status="pending" label="Partial" />;
    }
    return <StatusBadge status="missing" label="Missing" />;
  };

  const renderLastActivity = () => {
    if (!project.last_task_at) {
      return (
        <div className="project-card-activity">
          <span className="activity-label">No tasks yet</span>
        </div>
      );
    }

    return (
      <div className="project-card-activity">
        <StatusBadge status={project.last_task_status || 'pending'} />
        <span className="activity-time">{formatTimestamp(project.last_task_at)}</span>
      </div>
    );
  };

  return (
    <div className="project-card">
      <div className="project-card-header">
        <h3 className="project-card-title" onClick={() => onView(project)} role="button" tabIndex={0}>
          {project.name}
        </h3>
        {project.repository_url && (
          <a
            href={project.repository_url}
            target="_blank"
            rel="noreferrer"
            className="project-card-repo"
            onClick={(e) => e.stopPropagation()}
          >
            <Icon type="git" />
            <span>{project.repository_url.replace(/^https?:\/\//, '').substring(0, 40)}...</span>
          </a>
        )}
      </div>

      <div className="project-card-meta">
        <div className="meta-item">
          <Icon type="git" />
          <span className="meta-label">Host:</span>
          <span className="meta-value">{project.gitlab_host.replace(/^https?:\/\//, '')}</span>
        </div>
        <div className="meta-item">
          <Icon type="git" />
          <span className="meta-label">Branch:</span>
          <span className="meta-value">{project.default_branch}</span>
        </div>
      </div>

      <div className="project-card-stats">
        <div className="stat-group">
          <span className="stat-label">Cache</span>
          {renderCacheStatus()}
        </div>
        <div className="stat-group">
          <span className="stat-label">Allowlist</span>
          {renderAllowlistStatus()}
        </div>
        <div className="stat-group">
          <span className="stat-label">Credentials</span>
          {renderCredentialStatus()}
        </div>
      </div>

      <div className="project-card-activity-section">
        <span className="stat-label">Last Activity</span>
        {renderLastActivity()}
      </div>

      <div className="project-card-footer">
        <div className="project-card-task-count">
          <Icon type="clipboard" />
          <span className="task-count-active">{project.active_task_count}</span>
          <span className="task-count-total">/ {project.total_task_count} tasks</span>
        </div>

        <div className="project-card-actions">
          <Button variant="ghost" size="small" onClick={() => onView(project)}>
            View
          </Button>
          <Button variant="ghost" size="small" onClick={() => onEdit(project)}>
            Edit
          </Button>
          <Button
            variant="ghost"
            size="small"
            onClick={() => onSubmitTask(project)}
            disabled={!patConfigured}
          >
            Submit
          </Button>
          <button
            className="action-menu-button"
            onClick={(e) => {
              e.stopPropagation();
              // Toggle dropdown menu
            }}
            aria-label="More actions"
          >
            ⋮
          </button>
        </div>
      </div>
    </div>
  );
}

export default ProjectCard;
