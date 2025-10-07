import { ChangeEvent, FormEvent } from 'react';
import { Task } from '../../../types';
import { formatTimestamp } from '../../../utils/time';

type TaskLookupPanelProps = {
  taskLookupId: string;
  onLookupChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onLookupSubmit: (event: FormEvent<HTMLFormElement>) => void;
  taskDetail: Task | null;
  isDrawerOpen: boolean;
  onOpenDrawer: () => void;
};

function TaskLookupPanel({
  taskLookupId,
  onLookupChange,
  onLookupSubmit,
  taskDetail,
  isDrawerOpen,
  onOpenDrawer,
}: TaskLookupPanelProps) {
  return (
    <section className="panel">
      <h3>Task Detail</h3>
      <form className="lookup" onSubmit={onLookupSubmit}>
        <label htmlFor="task-id">Inspect Task ID</label>
        <div className="lookup-controls">
          <input id="task-id" type="number" value={taskLookupId} onChange={onLookupChange} min={1} />
          <button className="secondary-button" type="submit">
            Load
          </button>
        </div>
      </form>

      {taskDetail ? (
        <div className="drawer-reminder">
          <p>
            Task <strong>#{taskDetail.id}</strong> selected. Last update {formatTimestamp(taskDetail.finished_at || taskDetail.started_at)}.
          </p>
          {!isDrawerOpen && (
            <button type="button" className="ghost-button" onClick={onOpenDrawer}>
              Open task drawer
            </button>
          )}
        </div>
      ) : (
        <p className="empty">Select a task from the table above or enter a task ID to inspect it.</p>
      )}
    </section>
  );
}

export default TaskLookupPanel;
