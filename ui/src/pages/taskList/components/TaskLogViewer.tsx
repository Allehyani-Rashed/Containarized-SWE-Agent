import { useEffect, useRef } from 'react';
import { Task } from '../../../types';
import TaskSnapshotTimeline from './TaskSnapshotTimeline';
import { CopyState, TaskLogMetadata } from '../types';

type TaskLogViewerProps = {
  logs: string[];
  metadata: TaskLogMetadata | null;
  isStreaming: boolean;
  copyState: CopyState;
  onCopyLogs: () => Promise<void>;
  onResetCopyFeedback: () => void;
  taskDetail: Task | null;
};

function TaskLogViewer({
  logs,
  metadata,
  isStreaming,
  copyState,
  onCopyLogs,
  onResetCopyFeedback,
  taskDetail,
}: TaskLogViewerProps) {
  const containerRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    return onResetCopyFeedback;
  }, [onResetCopyFeedback]);

  return (
    <div className="logs drawer-logs">
      <div className="logs-header">
        <h4>Logs</h4>
        <div className="logs-actions">
          {isStreaming && <span className="live-indicator">Live</span>}
          <button type="button" className="ghost-button" onClick={onCopyLogs} disabled={!logs.length}>
            {copyState === 'success' ? 'Copied!' : copyState === 'error' ? 'Copy failed' : 'Copy logs'}
          </button>
          {copyState !== 'idle' && (
            <span
              className={`copy-feedback ${copyState === 'success' ? 'copy-feedback-success' : 'copy-feedback-error'}`}
              role="status"
              aria-live="polite"
            >
              {copyState === 'success' ? 'Logs copied to clipboard' : 'Failed to copy logs'}
            </span>
          )}
        </div>
      </div>
      <TaskSnapshotTimeline metadata={metadata} taskDetail={taskDetail} />
      {logs.length ? (
        <pre className="log-output" ref={containerRef}>
          {logs.map((line, index) => (
            <span key={`${index}-${line}`}>{line}\n</span>
          ))}
        </pre>
      ) : (
        <p className="empty">No logs yet.</p>
      )}
    </div>
  );
}

export default TaskLogViewer;
