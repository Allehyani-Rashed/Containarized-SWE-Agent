import { Task, CodexModel } from '../../../types';
import EmptyState from '../../../components/EmptyState';
import Icon from '../../../components/Icon';
import Skeleton from '../../../components/Skeleton';
import { formatTimestamp } from '../../../utils/time';
import {
  formatReasoningEffort,
  getCodexModelLabel,
  getProjectDisplayName,
  ProjectLookup,
} from '../taskSelectors';
import { TASK_LIST_PAGE_SIZE } from '../constants';
import { TaskListMeta } from '../types';

export type TaskTableProps = {
  tasks: Task[];
  models: CodexModel[];
  projectLookup: ProjectLookup;
  isLoading: boolean;
  isLoadingMore: boolean;
  listMeta: TaskListMeta;
  filtersApplied: boolean;
  canLoadMore: boolean;
  reachedPageLimit: boolean;
  selectedTaskId: number | null;
  quickActionLoading: number | null;
  onSelectTask: (task: Task) => void;
  onLoadMore: () => void;
  onResetFilters: () => void;
  onSubmitTask: () => void;
  onQuickAbortRequest: (taskId: number) => void;
  onQuickRetry: (task: Task) => void;
  onQuickClone: (task: Task) => void;
};

const skeletonRowCount = Math.min(5, TASK_LIST_PAGE_SIZE);

function TaskTable({
  tasks,
  models,
  projectLookup,
  isLoading,
  isLoadingMore,
  listMeta,
  filtersApplied,
  canLoadMore,
  reachedPageLimit,
  selectedTaskId,
  quickActionLoading,
  onSelectTask,
  onLoadMore,
  onResetFilters,
  onSubmitTask,
  onQuickAbortRequest,
  onQuickRetry,
  onQuickClone,
}: TaskTableProps) {
  const renderSkeleton = () => (
    <div className="table-responsive">
      <table className="task-table task-table-skeleton" aria-hidden="true">
        <caption className="sr-only">Loading task list</caption>
        <thead>
          <tr>
            <th>ID</th>
            <th>Project</th>
            <th>Status</th>
            <th>Created</th>
            <th>Finished</th>
            <th>Agent Invocation</th>
            <th>Model</th>
            <th>Reasoning</th>
            <th>Branch</th>
            <th>Base Branch</th>
            <th>Merge Request</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: skeletonRowCount }).map((_, rowIndex) => (
            <tr key={`skeleton-${rowIndex}`}>
              {Array.from({ length: 12 }).map((__, cellIndex) => (
                <td key={cellIndex}>
                  <Skeleton variant="text" width={`${Math.max(32, 85 - cellIndex * 6)}%`} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderEmptyState = () =>
    filtersApplied ? (
      <EmptyState
        icon="alert"
        title="No matching tasks"
        description="No tasks match your current filters. Try adjusting your filter criteria or clearing filters to see all tasks."
        actionLabel="Clear Filters"
        onAction={onResetFilters}
      />
    ) : (
      <EmptyState
        title="No tasks yet"
        description="Submit your first task to get started with AI-powered development"
        actionLabel="Submit Task"
        onAction={onSubmitTask}
      />
    );

  const getCaptionText = () => {
    if (filtersApplied) {
      return `Task list (filtered, showing ${tasks.length} of ${listMeta.total} tasks)`;
    }
    return `Task list (showing ${listMeta.total} tasks)`;
  };

  const renderTableBody = () => (
    <>
      <div className="table-responsive">
        <table className="task-table">
          <caption className="sr-only">{getCaptionText()}</caption>
          <thead>
            <tr>
              <th className="sticky-column">ID</th>
              <th>Project</th>
              <th>Status</th>
              <th>Created</th>
              <th className="hide-mobile">Finished</th>
              <th className="hide-tablet">Agent Invocation</th>
              <th className="hide-mobile">Model</th>
              <th className="hide-tablet">Reasoning</th>
              <th className="hide-tablet">Mode</th>
              <th className="hide-tablet">Branch</th>
              <th className="hide-tablet">Base Branch</th>
              <th className="hide-mobile">Change Link</th>
              <th className="task-actions-header">Actions</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const projectName = getProjectDisplayName(projectLookup, task.project_id);
              const canAbort = task.status === 'pending' || task.status === 'running';
              const canRetry = task.status === 'failed';
              const isWorking = quickActionLoading === task.id;
              const changeLink = task.change_mode === 'merge_request'
                ? task.mr_url
                  ? (
                      <a
                        href={task.mr_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                      >
                        {task.mr_url}
                      </a>
                    )
                  : '--'
                : task.commit_sha
                ? task.commit_url
                  ? (
                      <a
                        href={task.commit_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                      >
                        Commit {task.commit_sha.slice(0, 7)}
                      </a>
                    )
                  : `Commit ${task.commit_sha.slice(0, 7)}`
                : 'Branch update';

              return (
                <tr key={task.id} className={selectedTaskId === task.id ? 'active' : ''}>
                  <td className="sticky-column" onClick={() => onSelectTask(task)}>
                    {task.id}
                  </td>
                  <td onClick={() => onSelectTask(task)}>{projectName}</td>
                  <td onClick={() => onSelectTask(task)}>
                    <span className={`status status-${task.status}`}>{task.status}</span>
                  </td>
                  <td onClick={() => onSelectTask(task)}>{formatTimestamp(task.created_at)}</td>
                  <td className="hide-mobile" onClick={() => onSelectTask(task)}>
                    {formatTimestamp(task.finished_at)}
                  </td>
                  <td className="hide-tablet" onClick={() => onSelectTask(task)}>{task.codex_invocation ?? '--'}</td>
                  <td className="hide-mobile" onClick={() => onSelectTask(task)}>
                    {getCodexModelLabel(models, task.codex_model)}
                  </td>
                  <td className="hide-tablet" onClick={() => onSelectTask(task)}>
                    {formatReasoningEffort(task.codex_reasoning_effort)}
                  </td>
                  <td className="hide-tablet" onClick={() => onSelectTask(task)}>
                    <span className={`change-mode-chip change-mode-${task.change_mode}`}>
                      {task.change_mode === 'branch_commit' ? 'Branch commit' : 'Merge request'}
                    </span>
                  </td>
                  <td className="hide-tablet" onClick={() => onSelectTask(task)}>{task.branch ?? '--'}</td>
                  <td className="hide-tablet" onClick={() => onSelectTask(task)}>{task.target_branch ?? '--'}</td>
                  <td className="hide-mobile" onClick={() => onSelectTask(task)}>{changeLink}</td>
                  <td className="task-actions-cell" onClick={(event) => event.stopPropagation()}>
                    <div className="task-actions">
                      {canAbort && (
                        <button
                          type="button"
                          className="action-btn action-btn-abort"
                          onClick={() => onQuickAbortRequest(task.id)}
                          disabled={isWorking || task.abort_requested}
                          title="Abort task"
                          aria-label="Abort task"
                        >
                          <Icon type="alert" size={16} />
                          <span className="action-text">Abort</span>
                        </button>
                      )}
                      {canRetry && (
                        <button
                          type="button"
                          className="action-btn action-btn-retry"
                          onClick={() => onQuickRetry(task)}
                          disabled={isWorking}
                          title="Retry with same parameters"
                          aria-label="Retry task"
                        >
                          <Icon type="rotate-cw" size={16} />
                          <span className="action-text">Retry</span>
                        </button>
                      )}
                      <button
                        type="button"
                        className="action-btn action-btn-clone"
                        onClick={() => onQuickClone(task)}
                        disabled={isWorking}
                        title="Clone task with same parameters"
                        aria-label="Clone task"
                      >
                        <Icon type="copy" size={16} />
                        <span className="action-text">Clone</span>
                      </button>
                      <button
                        type="button"
                        className="action-btn action-btn-view"
                        onClick={() => onSelectTask(task)}
                        disabled={isWorking}
                        title="View task details and logs"
                        aria-label="View task logs"
                      >
                        <Icon type="eye" size={16} />
                        <span className="action-text">View</span>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="table-footer">
        {canLoadMore && (
          <button type="button" className="secondary-button" onClick={onLoadMore} disabled={isLoadingMore}>
            {isLoadingMore ? 'Loading…' : 'Load more'}
          </button>
        )}
        {reachedPageLimit && (
          <p className="table-hint">Showing the latest {tasks.length} tasks (API window limit reached).</p>
        )}
        {!canLoadMore && !reachedPageLimit && tasks.length < listMeta.total && (
          <p className="table-hint">Showing {tasks.length} of {listMeta.total} tasks.</p>
        )}
      </div>
    </>
  );

  return (
    <section className="panel" aria-busy={isLoading ? 'true' : 'false'}>
      <div className="panel-header">
        <h3>Task History</h3>
        <div className="panel-meta">
          <span>{`Showing ${tasks.length} of ${listMeta.total} tasks`}</span>
          {filtersApplied && <span className="filter-indicator">Filters active</span>}
        </div>
      </div>
      <div className="table-wrapper">
        {isLoading ? renderSkeleton() : tasks.length === 0 ? renderEmptyState() : renderTableBody()}
      </div>
    </section>
  );
}

export default TaskTable;
