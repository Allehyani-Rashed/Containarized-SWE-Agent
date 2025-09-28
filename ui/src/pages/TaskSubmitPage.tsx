import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import TaskSubmissionCard, { TaskSubmissionFormState } from '../components/TaskSubmissionCard';
import { createTask } from '../api/tasks';
import { getPatStatus, initialPatStatus } from '../api/integrations';
import { listCodexModels } from '../api/models';
import { CodexModel, TaskCreatePayload } from '../types';
import { formatTimestamp } from '../utils/time';
import { useProjects } from '../hooks/useProjectsData';

const initialFormState: TaskSubmissionFormState = {
  projectId: '',
  prompt: '',
  allowlist: '',
  branchName: '',
  codexModel: '',
};

function TaskSubmitPage() {
  const [models, setModels] = useState<CodexModel[]>([]);
  const [form, setForm] = useState(initialFormState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [createdTaskId, setCreatedTaskId] = useState<number | null>(null);
  const [patStatus, setPatStatus] = useState(initialPatStatus);
  const [lastPatRefresh, setLastPatRefresh] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const { projects, error: projectsError, clearError: clearProjectsError, isLoading: projectsLoading } = useProjects();

  const selectedProject = useMemo(() => {
    return projects.find((project) => String(project.id) === form.projectId) ?? null;
  }, [form.projectId, projects]);

  useEffect(() => {
    if (!form.projectId && projects.length) {
      setForm((prev) => ({ ...prev, projectId: String(projects[0].id) }));
    }
  }, [projects, form.projectId]);

  useEffect(() => {
    const state = location.state as { projectId?: number } | null;
    if (!state?.projectId || !projects.length) {
      return;
    }
    const exists = projects.some((project) => project.id === state.projectId);
    if (exists) {
      setForm((prev) => ({ ...prev, projectId: String(state.projectId) }));
      navigate('.', { replace: true, state: {} });
    }
  }, [location.state, navigate, projects]);

  useEffect(() => {
    let cancelled = false;

    const fetchModels = async () => {
      try {
        const available = await listCodexModels();
        if (!cancelled) {
          setModels(available);
          const defaultModel = available.find((item) => item.is_default)?.id ?? '';
          setForm((prev) => {
            if (prev.codexModel && available.some((item) => item.id === prev.codexModel)) {
              return prev;
            }
            return { ...prev, codexModel: defaultModel };
          });
        }
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'Failed to load models');
        }
      }
    };

    void fetchModels();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const fetchPatStatus = async () => {
      try {
        const status = await getPatStatus();
        if (!cancelled) {
          setPatStatus(status);
          setLastPatRefresh(new Date().toISOString());
        }
      } catch (apiError) {
        if (!cancelled) {
          setError(apiError instanceof Error ? apiError.message : 'Failed to load credential status');
        }
      }
    };

    void fetchPatStatus();
    const interval = window.setInterval(() => {
      void fetchPatStatus();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.projectId || !form.prompt.trim()) {
      setError('Project and prompt are required');
      return;
    }
    if (!patStatus.configured) {
      setError('Configure a GitLab PAT before submitting tasks');
      return;
    }

    const payload: TaskCreatePayload = {
      project_id: Number(form.projectId),
      prompt: form.prompt,
      allowlist: form.allowlist
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    };

    if (form.branchName.trim()) {
      payload.branch_name = form.branchName.trim();
    }
    if (form.codexModel) {
      payload.codex_model = form.codexModel;
    }

    setSubmitting(true);
    setSuccessMessage(null);
    setError(null);
    if (projectsError) {
      clearProjectsError();
    }

    try {
      const task = await createTask(payload);
      setCreatedTaskId(task.id);
      setSuccessMessage(`Task ${task.id} created. View progress on the Tasks page.`);
      setForm((prev) => ({ ...prev, prompt: '' }));
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to submit task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h2>Submit Task</h2>
        <p>Pick a project, provide the prompt, and submit a new Codex task.</p>
      </header>

      {(error || projectsError) && <div className="error-banner">{error || projectsError}</div>}
      {successMessage && <div className="notice notice-success">{successMessage}</div>}

      <TaskSubmissionCard
        form={form}
        setForm={setForm}
        onSubmit={handleSubmit}
        projects={projects}
        models={models}
        patStatus={patStatus}
        submitting={submitting}
        disabled={submitting || projectsLoading || !projects.length || !patStatus.configured}
      />

      <section className="panel">
        <h3>Credential Status</h3>
        <dl className="summary-list">
          <div>
            <dt>GitLab PAT</dt>
            <dd className={patStatus.configured ? 'status status-done' : 'status status-failed'}>
              {patStatus.configured ? 'Configured' : 'Missing'}
            </dd>
          </div>
          <div>
            <dt>PAT last update</dt>
            <dd>{formatTimestamp(patStatus.updated_at)}</dd>
          </div>
          <div>
            <dt>Active project</dt>
            <dd>{selectedProject ? selectedProject.name : 'Select a project'}</dd>
          </div>
          <div>
            <dt>Credential check</dt>
            <dd>
              {patStatus.verification_status === 'verified'
                ? 'Verified'
                : patStatus.verification_status === 'error'
                ? 'Check failed'
                : 'Not run'}
            </dd>
          </div>
          <div>
            <dt>Last checked</dt>
            <dd>{formatTimestamp(patStatus.verification_checked_at)}</dd>
          </div>
          <div>
            <dt>Status refreshed</dt>
            <dd>{formatTimestamp(lastPatRefresh)}</dd>
          </div>
        </dl>
        {createdTaskId ? (
          <button
            type="button"
            className="ghost-button"
            onClick={() => navigate('/tasks', { state: { focusTaskId: createdTaskId } })}
          >
            View Task {createdTaskId}
          </button>
        ) : null}
      </section>
    </div>
  );
}

export default TaskSubmitPage;
