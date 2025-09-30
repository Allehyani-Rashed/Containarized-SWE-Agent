import { Dispatch, FormEventHandler, SetStateAction, useMemo } from 'react';
import { CodexModel, PatStatus, Project } from '../types';

export type TaskSubmissionFormState = {
  projectId: string;
  prompt: string;
  allowlist: string;
  branchName: string;
  codexModel: string;
  codexReasoningEffort: 'low' | 'medium' | 'high';
};

type SubmitHandler = FormEventHandler<HTMLFormElement>;

type TaskSubmissionCardProps = {
  form: TaskSubmissionFormState;
  setForm: Dispatch<SetStateAction<TaskSubmissionFormState>>;
  onSubmit: SubmitHandler;
  projects: Project[];
  models: CodexModel[];
  patStatus: PatStatus;
  submitting: boolean;
  disabled: boolean;
};

function TaskSubmissionCard({
  form,
  setForm,
  onSubmit,
  projects,
  models,
  patStatus,
  submitting,
  disabled,
}: TaskSubmissionCardProps) {
  const selectedModel = useMemo(() => {
    return models.find((model) => model.id === form.codexModel) ?? null;
  }, [form.codexModel, models]);

  const reasoningOptions: Array<{ value: 'low' | 'medium' | 'high'; label: string }> = [
    { value: 'low', label: 'Low (fastest)' },
    { value: 'medium', label: 'Medium (default)' },
    { value: 'high', label: 'High (deepest)' },
  ];
  const reasoningDescriptions: Record<'low' | 'medium' | 'high', string> = {
    low: 'Favors speed and cost; suited for straightforward edits.',
    medium: 'Balances quality and latency; recommended default.',
    high: 'Allocates more reasoning time for complex tasks.',
  };
  const reasoningHint = reasoningDescriptions[form.codexReasoningEffort];

  const modelsAvailable = models.length > 0;

  return (
    <section className="panel">
      <h3>Task Submission</h3>
      <form className="form" onSubmit={onSubmit}>
        <label>
          Project
          <select
            value={form.projectId}
            onChange={(event) => setForm((prev) => ({ ...prev, projectId: event.target.value }))}
            required
          >
            <option value="" disabled>
              {projects.length ? 'Select project' : 'Create a project first'}
            </option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Prompt
          <textarea
            value={form.prompt}
            onChange={(event) => setForm((prev) => ({ ...prev, prompt: event.target.value }))}
            placeholder="Explain what Codex should do..."
            rows={4}
            required
          />
        </label>

        <label>
          Allowlist Domains (optional)
          <input
            type="text"
            value={form.allowlist}
            onChange={(event) => setForm((prev) => ({ ...prev, allowlist: event.target.value }))}
            placeholder="domain1.com, domain2.com"
          />
        </label>

        <label>
          Branch Name (optional)
          <input
            type="text"
            value={form.branchName}
            onChange={(event) => setForm((prev) => ({ ...prev, branchName: event.target.value }))}
            placeholder="feature/my-custom-branch"
            autoComplete="off"
          />
        </label>

        <label>
          Codex Model
          <select
            value={form.codexModel}
            onChange={(event) => setForm((prev) => ({ ...prev, codexModel: event.target.value }))}
            disabled={!modelsAvailable}
          >
            {modelsAvailable ? null : (
              <option value="">Models unavailable</option>
            )}
            {modelsAvailable && <option value="">Use default</option>}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label}
              </option>
            ))}
          </select>
        </label>
        {selectedModel?.description ? (
          <p className="field-hint">{selectedModel.description}</p>
        ) : null}

        <label>
          Reasoning Effort
          <select
            value={form.codexReasoningEffort}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                codexReasoningEffort: event.target.value as 'low' | 'medium' | 'high',
              }))
            }
          >
            {reasoningOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <p className="field-hint">{reasoningHint}</p>

        {!patStatus.configured && (
          <p className="notice notice-warning">
            Personal access token missing. Store a token in Settings before submitting a task.
          </p>
        )}

        <button type="submit" disabled={disabled}>
          {submitting ? 'Submitting...' : 'Create Task'}
        </button>
      </form>
    </section>
  );
}

export default TaskSubmissionCard;
