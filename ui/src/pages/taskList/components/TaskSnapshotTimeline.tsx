import { Task } from '../../../types';
import { formatTimestamp } from '../../../utils/time';
import { formatReasoningEffort } from '../taskSelectors';
import { TaskLogMetadata } from '../types';

type TaskSnapshotTimelineProps = {
  metadata: TaskLogMetadata | null;
  taskDetail: Task | null;
};

function renderChangeLink(metadata: TaskLogMetadata, taskDetail: Task | null) {
  if (metadata.change_mode === 'merge_request') {
    if (taskDetail?.mr_url) {
      return (
        <a href={taskDetail.mr_url} target="_blank" rel="noreferrer">
          {taskDetail.mr_url}
        </a>
      );
    }
    return taskDetail?.mr_url ?? '--';
  }

  if (metadata.commit_sha) {
    if (metadata.commit_url) {
      return (
        <a href={metadata.commit_url} target="_blank" rel="noreferrer">
          Commit {metadata.commit_sha.slice(0, 7)}
        </a>
      );
    }
    return `Commit ${metadata.commit_sha.slice(0, 7)}`;
  }

  return 'Branch update';
}

function TaskSnapshotTimeline({ metadata, taskDetail }: TaskSnapshotTimelineProps) {
  if (!metadata) {
    return null;
  }

  return (
    <dl className="logs-metadata">
      <div>
        <dt>Status at capture</dt>
        <dd>{metadata.status}</dd>
      </div>
      <div>
        <dt>Branch at capture</dt>
        <dd>{metadata.branch ?? '--'}</dd>
      </div>
      <div>
        <dt>{metadata.change_mode === 'branch_commit' ? 'Commit at capture' : 'Merge request at capture'}</dt>
        <dd>{renderChangeLink(metadata, taskDetail)}</dd>
      </div>
      <div>
        <dt>Model at capture</dt>
        <dd>{metadata.codex_model ?? 'Default'}</dd>
      </div>
      <div>
        <dt>Reasoning effort</dt>
        <dd>{formatReasoningEffort(metadata.codex_reasoning_effort)}</dd>
      </div>
      <div>
        <dt>Abort requested</dt>
        <dd>{metadata.abort_requested ? 'Yes' : 'No'}</dd>
      </div>
      <div>
        <dt>GitLab PAT available</dt>
        <dd>{metadata.credentials.gitlab_pat_available ? 'Yes' : 'No'}</dd>
      </div>
      <div>
        <dt>GitLab PAT updated</dt>
        <dd>{formatTimestamp(metadata.credentials.gitlab_pat_last_updated)}</dd>
      </div>
      <div>
        <dt>ChatGPT session available</dt>
        <dd>{metadata.credentials.chatgpt_session_available ? 'Yes' : 'No'}</dd>
      </div>
      <div>
        <dt>ChatGPT session updated</dt>
        <dd>{formatTimestamp(metadata.credentials.chatgpt_session_last_updated)}</dd>
      </div>
    </dl>
  );
}

export default TaskSnapshotTimeline;
