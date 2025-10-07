import { Task } from '../../../types';
import { formatTimestamp } from '../../../utils/time';
import { formatReasoningEffort } from '../taskSelectors';
import TaskLogViewer from './TaskLogViewer';
import ConfirmationModal from './ConfirmationModal';
import { CopyState, TaskLogMetadata } from '../types';

type TaskDetailDrawerProps = {
  isOpen: boolean;
  task: Task | null;
  projectName: string;
  abortPending: boolean;
  canAbort: boolean;
  canDelete: boolean;
  isActionLoading: boolean;
  actionNotice: string | null;
  actionError: string | null;
  confirmAction: 'abort' | 'delete' | null;
  onRequestAbort: () => void;
  onRequestDelete: () => void;
  onCancelAction: () => void;
  onConfirmAction: () => void;
  onClose: () => void;
  logs: string[];
  logMetadata: TaskLogMetadata | null;
  isStreaming: boolean;
  copyState: CopyState;
  onCopyLogs: () => Promise<void>;
  onResetCopyFeedback: () => void;
};

function renderChangeLink(task: Task) {
  if (task.change_mode === 'merge_request') {
    if (task.mr_url) {
      return (
        <a href={task.mr_url} target="_blank" rel="noreferrer">
          {task.mr_url}
        </a>
      );
    }
    return '--';
  }

  if (task.commit_sha) {
    if (task.commit_url) {
      return (
        <a href={task.commit_url} target="_blank" rel="noreferrer">
          Commit {task.commit_sha.slice(0, 7)}
        </a>
      );
    }
    return `Commit ${task.commit_sha.slice(0, 7)}`;
  }

  return 'Branch update';
}

function TaskDetailDrawer({
  isOpen,
  task,
  projectName,
  abortPending,
  canAbort,
  canDelete,
  isActionLoading,
  actionNotice,
  actionError,
  confirmAction,
  onRequestAbort,
  onRequestDelete,
  onCancelAction,
  onConfirmAction,
  onClose,
  logs,
  logMetadata,
  isStreaming,
  copyState,
  onCopyLogs,
  onResetCopyFeedback,
}: TaskDetailDrawerProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="task-drawer">
      <div className="task-drawer-backdrop" aria-hidden="true" />
      <div className="task-drawer-panel">
        <button type="button" className="drawer-close" onClick={onClose} aria-label="Close task drawer">
          ×
        </button>
        {task ? (
          <>
            <header className="drawer-header">
              <div className="drawer-header-main">
                <p className="drawer-eyebrow">Task #{task.id}</p>
                <div className="drawer-status-row">
                  <span className={`status status-${task.status}`}>{task.status}</span>
                  {abortPending && <span className="abort-pill">Abort requested</span>}
                </div>
                <p className="drawer-subtle">
                  Created {formatTimestamp(task.created_at)} • Project {projectName}
                </p>
              </div>
              <div className="drawer-actions">
                {canAbort && (
                  <button
                    type="button"
                    className="danger-button"
                    onClick={onRequestAbort}
                    disabled={isActionLoading || confirmAction !== null || task.abort_requested}
                  >
                    {abortPending ? 'Abort pending…' : 'Abort task'}
                  </button>
                )}
                {canDelete && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={onRequestDelete}
                    disabled={isActionLoading || confirmAction !== null}
                  >
                    Delete task
                  </button>
                )}
              </div>
            </header>

            {actionNotice && <div className="alert alert-success">{actionNotice}</div>}
            {actionError && <div className="alert alert-warning">{actionError}</div>}

            <div className="drawer-meta-grid">
              <dl>
                <div>
                  <dt>Prompt</dt>
                  <dd>{task.prompt}</dd>
                </div>
                <div>
                  <dt>Branch</dt>
                  <dd>{task.branch ?? '--'}</dd>
                </div>
                <div>
                  <dt>Base Branch</dt>
                  <dd>{task.target_branch ?? '--'}</dd>
                </div>
                <div>
                  <dt>Change Mode</dt>
                  <dd>{task.change_mode === 'branch_commit' ? 'Branch commit' : 'Merge request'}</dd>
                </div>
                <div>
                  <dt>Agent Model</dt>
                  <dd>{task.codex_model ?? '--'}</dd>
                </div>
                <div>
                  <dt>Reasoning Effort</dt>
                  <dd>{formatReasoningEffort(task.codex_reasoning_effort)}</dd>
                </div>
                <div>
                  <dt>GitLab PAT</dt>
                  <dd>{task.credentials.gitlab_pat_available ? 'Available' : 'Missing'}</dd>
                </div>
                <div>
                  <dt>ChatGPT Session</dt>
                  <dd>{task.credentials.chatgpt_session_available ? 'Available' : 'Missing'}</dd>
                </div>
              </dl>
              <dl>
                <div>
                  <dt>Started</dt>
                  <dd>{formatTimestamp(task.started_at)}</dd>
                </div>
                <div>
                  <dt>Finished</dt>
                  <dd>{formatTimestamp(task.finished_at)}</dd>
                </div>
                <div>
                  <dt>{task.change_mode === 'branch_commit' ? 'Latest Commit' : 'Merge Request'}</dt>
                  <dd>{renderChangeLink(task)}</dd>
                </div>
                <div>
                  <dt>Agent Runtime</dt>
                  <dd>{task.codex_agent_version ?? '--'}</dd>
                </div>
                <div>
                  <dt>Agent Invocation</dt>
                  <dd>{task.codex_invocation ?? '--'}</dd>
                </div>
                <div>
                  <dt>PAT Updated</dt>
                  <dd>{formatTimestamp(task.credentials.gitlab_pat_last_updated)}</dd>
                </div>
                <div>
                  <dt>Session Updated</dt>
                  <dd>{formatTimestamp(task.credentials.chatgpt_session_last_updated)}</dd>
                </div>
              </dl>
            </div>

            <TaskLogViewer
              logs={logs}
              metadata={logMetadata}
              isStreaming={isStreaming}
              copyState={copyState}
              onCopyLogs={onCopyLogs}
              onResetCopyFeedback={onResetCopyFeedback}
              taskDetail={task}
            />
          </>
        ) : (
          <p className="empty">No task selected.</p>
        )}

        <ConfirmationModal
          open={confirmAction !== null}
          title={confirmAction === 'abort' ? 'Abort task?' : 'Delete task?'}
          description={
            confirmAction === 'abort'
              ? 'The task will be terminated. Currently running operations will complete before stopping. This cannot be undone.'
              : 'This removes the task record, logs, and sanitized workspace. This action cannot be undone.'
          }
          confirmLabel={confirmAction === 'abort' ? 'Confirm abort' : 'Confirm delete'}
          isLoading={isActionLoading}
          onConfirm={onConfirmAction}
          onCancel={onCancelAction}
          idSuffix="task-drawer-confirm"
        />
      </div>
    </div>
  );
}

export default TaskDetailDrawer;
