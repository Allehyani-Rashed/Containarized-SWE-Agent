import { ChangeEvent, FormEvent } from 'react';
import { CodexModel, TaskStatus } from '../../../types';
import { TASK_STATUS_OPTIONS } from '../constants';
import { TaskFilters } from '../types';

export type TaskFilterToolbarProps = {
  filterDraft: TaskFilters;
  filtersApplied: boolean;
  filterDraftMatchesApplied: boolean;
  models: CodexModel[];
  statusOptions?: TaskStatus[];
  onStatusToggle: (status: TaskStatus) => void;
  onModelChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  onBranchChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
};

function TaskFilterToolbar({
  filterDraft,
  filtersApplied,
  filterDraftMatchesApplied,
  models,
  statusOptions = TASK_STATUS_OPTIONS,
  onStatusToggle,
  onModelChange,
  onBranchChange,
  onSubmit,
  onReset,
}: TaskFilterToolbarProps) {
  return (
    <section className="panel">
      <h3>Filters</h3>
      <form className="task-filters" onSubmit={onSubmit} aria-label="Filter tasks">
        <fieldset className="filter-group">
          <legend>Status</legend>
          <div className="filter-options">
            {statusOptions.map((statusOption) => {
              const checked = filterDraft.statuses.includes(statusOption);
              return (
                <label key={statusOption} className={`filter-chip${checked ? ' active' : ''}`}>
                  <input type="checkbox" checked={checked} onChange={() => onStatusToggle(statusOption)} />
                  <span>{statusOption}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
        <div className="filter-field">
          <label htmlFor="task-filter-model">Model</label>
          <select id="task-filter-model" value={filterDraft.codexModel} onChange={onModelChange}>
            <option value="">All models</option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label || model.id}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-field">
          <label htmlFor="task-filter-branch">Branch contains</label>
          <input
            id="task-filter-branch"
            type="text"
            value={filterDraft.branch}
            onChange={onBranchChange}
            placeholder="feature/"
          />
        </div>
        <div className="filter-actions">
          <button type="submit" className="secondary-button" disabled={filterDraftMatchesApplied}>
            Apply filters
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={onReset}
            disabled={!filtersApplied && filterDraftMatchesApplied}
          >
            Reset
          </button>
        </div>
      </form>
    </section>
  );
}

export default TaskFilterToolbar;
