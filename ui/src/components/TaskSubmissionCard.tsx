import { Dispatch, FormEventHandler, SetStateAction, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { listProjectBranches } from '../api/projects';
import { CodexModel, PatStatus, Project, ProjectBranch } from '../types';

export type TaskSubmissionFormState = {
  projectId: string;
  prompt: string;
  targetBranch: string;
  branchName: string;
  codexModel: string;
  codexReasoningEffort: 'low' | 'medium' | 'high';
  mrTitle: string;
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
  const branchListId = useMemo(() => `base-branch-options-${form.projectId || 'unassigned'}`, [form.projectId]);
  const [branchQuery, setBranchQuery] = useState(form.targetBranch);
  const [branchOptions, setBranchOptions] = useState<ProjectBranch[]>([]);
  const [branchLoading, setBranchLoading] = useState(false);
  const [branchError, setBranchError] = useState<string | null>(null);
  const branchAbortRef = useRef<AbortController | null>(null);
  const debouncedBranchQuery = useDebouncedValue(branchQuery, 300);

  useEffect(() => {
    setBranchQuery(form.targetBranch);
  }, [form.targetBranch]);

  useEffect(() => {
    if (!form.projectId) {
      setBranchOptions([]);
      setBranchError(null);
      setBranchLoading(false);
      if (branchAbortRef.current) {
        branchAbortRef.current.abort();
        branchAbortRef.current = null;
      }
      return;
    }

    const controller = new AbortController();
    branchAbortRef.current?.abort();
    branchAbortRef.current = controller;
    setBranchLoading(true);

    listProjectBranches(Number(form.projectId), {
      search: debouncedBranchQuery.trim() ? debouncedBranchQuery.trim() : undefined,
      perPage: 20,
      signal: controller.signal,
    })
      .then((response) => {
        if (controller.signal.aborted) {
          return;
        }
        setBranchOptions(response.items);
        setBranchError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        if (error instanceof ApiError) {
          setBranchError(error.message);
        } else {
          setBranchError('Failed to load branches');
        }
        setBranchOptions([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setBranchLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [form.projectId, debouncedBranchQuery]);

  return (
    <section className="panel">
      <h3>Task Submission</h3>
      <form className="form" onSubmit={onSubmit}>
        <label>
          Project
          <select
            value={form.projectId}
            onChange={(event) => {
              const nextProjectId = event.target.value;
              let resolvedBranch = '';
              setForm((prev) => {
                const selected = projects.find((project) => String(project.id) === nextProjectId);
                resolvedBranch = selected?.default_branch ?? prev.targetBranch;
                return {
                  ...prev,
                  projectId: nextProjectId,
                  targetBranch: resolvedBranch,
                };
              });
              setBranchQuery(resolvedBranch);
            }}
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
          Base Branch
          <input
            type="text"
            list={branchListId}
            value={form.targetBranch}
            onChange={(event) => {
              const nextValue = event.target.value;
              setForm((prev) => ({ ...prev, targetBranch: nextValue }));
              setBranchQuery(nextValue);
            }}
            placeholder="main"
            autoComplete="off"
            required
          />
          <datalist id={branchListId}>
            {branchOptions.map((branch) => (
              <option
                key={branch.name}
                value={branch.name}
                label={branch.default ? `${branch.name} (default)` : branch.name}
              />
            ))}
          </datalist>
          {branchLoading ? <p className="field-hint">Loading branches…</p> : null}
          {!branchLoading && branchError ? (
            <p className="field-hint">Branches unavailable: {branchError}</p>
          ) : null}
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
          Merge Request Title
          <input
            type="text"
            value={form.mrTitle}
            onChange={(event) => setForm((prev) => ({ ...prev, mrTitle: event.target.value }))}
            placeholder="Agent Task: Short summary"
            maxLength={240}
            required
          />
          <p className="field-hint">Used as the GitLab merge request title (max 240 characters).</p>
        </label>

        <label>
          Prompt
          <textarea
            value={form.prompt}
            onChange={(event) => setForm((prev) => ({ ...prev, prompt: event.target.value }))}
            placeholder="Explain what the agent should do..."
            rows={4}
            required
          />
        </label>

        <label>
          Agent Model
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

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);

  return debounced;
}

export default TaskSubmissionCard;
