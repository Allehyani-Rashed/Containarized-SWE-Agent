import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { createTask, listTasks } from '../api/tasks';
import { listCodexModels } from '../api/models';
import { listProjectBranches } from '../api/projects';
import { CodexModel, TaskCreatePayload, ProjectBranch, Task, TaskChangeMode } from '../types';
import { formatTimestamp } from '../utils/time';
import { useProjects } from '../hooks/useProjectsData';
import { usePatStatus } from '../hooks/usePatStatus';
import { ErrorBoundary } from '../components/ErrorBoundary';
import {
  Card,
  Button,
  TextInput,
  TextArea,
  Select,
  StatusBadge,
  InfoPanel,
  Icon,
} from '../components';
import './TaskSubmitPage.css';

type TaskSubmissionFormState = {
  projectId: string;
  prompt: string;
  targetBranch: string;
  branchName: string;
  changeMode: TaskChangeMode;
  codexModel: string;
  codexReasoningEffort: 'low' | 'medium' | 'high';
  mrTitle: string;
};

type FieldValidation = {
  [K in keyof TaskSubmissionFormState]?: string | null;
};

const initialFormState: TaskSubmissionFormState = {
  projectId: '',
  prompt: '',
  targetBranch: '',
  branchName: '',
  changeMode: 'merge_request',
  codexModel: '',
  codexReasoningEffort: 'medium',
  mrTitle: '',
};

function TaskSubmitPage() {
  const [models, setModels] = useState<CodexModel[]>([]);
  const [form, setForm] = useState(initialFormState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [createdTaskId, setCreatedTaskId] = useState<number | null>(null);
  const [branchOptions, setBranchOptions] = useState<ProjectBranch[]>([]);
  const [fieldErrors, setFieldErrors] = useState<FieldValidation>({});
  const [touchedFields, setTouchedFields] = useState<Set<keyof TaskSubmissionFormState>>(new Set());
  const [recentTasks, setRecentTasks] = useState<Task[]>([]);
  const [recentTasksLoading, setRecentTasksLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const { projects, error: projectsError, clearError: clearProjectsError, isLoading: projectsLoading } = useProjects();

  const {
    status: patStatus,
    error: patStatusError,
  } = usePatStatus();

  const selectedProject = useMemo(() => {
    return projects.find((project) => String(project.id) === form.projectId) ?? null;
  }, [form.projectId, projects]);

  const isBranchCommit = form.changeMode === 'branch_commit';

  // Validation logic
  const validateField = (field: keyof TaskSubmissionFormState, value: string): string | null => {
    switch (field) {
      case 'projectId':
        return !value ? 'Project is required' : null;
      case 'prompt':
        if (!value.trim()) return 'Task instructions are required';
        if (value.trim().length < 10) return 'Please provide more detailed instructions (at least 10 characters)';
        return null;
      case 'mrTitle': {
        const normalizedTitle = value.replace(/\s+/g, ' ').trim();
        if (!normalizedTitle) {
          return form.changeMode === 'branch_commit'
            ? 'Commit message is required'
            : 'Merge request title is required';
        }
        if (normalizedTitle.length > 240) {
          return form.changeMode === 'branch_commit'
            ? 'Commit message cannot exceed 240 characters'
            : 'Title cannot exceed 240 characters';
        }
        return null;
      }
      case 'targetBranch':
        // Optional but should be valid if provided
        return null;
      case 'branchName':
        // Branch name is optional for merge requests (auto-generated if empty)
        // Not used at all for branch commits (field is hidden)
        return null;
      case 'changeMode':
        return null;
      default:
        return null;
    }
  };

  const validateForm = (): boolean => {
    const errors: FieldValidation = {};
    let isValid = true;

    (Object.keys(form) as Array<keyof TaskSubmissionFormState>).forEach((field) => {
      const error = validateField(field, form[field] as string);
      if (error) {
        errors[field] = error;
        isValid = false;
      }
    });

    setFieldErrors(errors);
    return isValid;
  };

  const handleFieldChange = (field: keyof TaskSubmissionFormState, value: string) => {
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      // Clear branchName when switching to branch_commit mode (not used)
      if (field === 'changeMode' && value === 'branch_commit') {
        next.branchName = '';
      }
      return next;
    });

    if (field === 'changeMode') {
      setTouchedFields((prev) => {
        const next = new Set(prev);
        // Remove branchName from touched fields when not in merge_request mode
        next.delete('branchName');
        return next;
      });
    }

    // Real-time validation for touched fields
    if (touchedFields.has(field)) {
      const error = validateField(field, value);
      setFieldErrors((prev) => ({ ...prev, [field]: error }));
    }
  };

  const handleFieldBlur = (field: keyof TaskSubmissionFormState) => {
    setTouchedFields((prev) => new Set(prev).add(field));
    const error = validateField(field, form[field] as string);
    setFieldErrors((prev) => ({ ...prev, [field]: error }));
  };

  // Calculate form completion progress
  const requiredFields = useMemo<Array<keyof TaskSubmissionFormState>>(() => {
    const fields: Array<keyof TaskSubmissionFormState> = ['projectId', 'prompt', 'mrTitle'];
    // branchName is optional for merge requests and not used for branch commits
    return fields;
  }, [form.changeMode]);

  // Auto-select first project on load
  useEffect(() => {
    if (!form.projectId && projects.length) {
      setForm((prev) => ({
        ...prev,
        projectId: String(projects[0].id),
        targetBranch: projects[0].default_branch,
      }));
    }
  }, [projects, form.projectId]);

  // Handle project selection and task clone/retry from navigation state
  useEffect(() => {
    const state = location.state as {
      projectId?: number;
      prompt?: string;
      targetBranch?: string;
      branchName?: string;
      changeMode?: TaskChangeMode;
      codexModel?: string;
      codexReasoningEffort?: 'low' | 'medium' | 'high';
      mrTitle?: string;
    } | null;

    if (!state || !projects.length) {
      return;
    }

    // If we have a projectId in state
    if (state.projectId) {
      const exists = projects.some((project) => project.id === state.projectId);
      if (exists) {
        const target = projects.find((project) => project.id === state.projectId);
        setForm((prev) => ({
          ...prev,
          projectId: String(state.projectId),
          prompt: state.prompt || prev.prompt,
          targetBranch: state.targetBranch || target?.default_branch || prev.targetBranch,
          branchName: state.branchName ?? prev.branchName,
          changeMode:
            state.changeMode && ['merge_request', 'branch_commit'].includes(state.changeMode)
              ? state.changeMode
              : prev.changeMode,
          codexModel: state.codexModel || prev.codexModel,
          codexReasoningEffort: state.codexReasoningEffort || prev.codexReasoningEffort,
          mrTitle: state.mrTitle || prev.mrTitle,
        }));
        navigate('.', { replace: true, state: {} });
      }
    }
  }, [location.state, navigate, projects]);

  // Update target branch when project changes
  useEffect(() => {
    if (!selectedProject) {
      return;
    }
    setForm((prev) => {
      if (!prev.targetBranch.trim()) {
        return { ...prev, targetBranch: selectedProject.default_branch };
      }
      return prev;
    });
  }, [selectedProject]);

  // Fetch available models
  useEffect(() => {
    let cancelled = false;

    const fetchModels = async () => {
      try {
        const available = await listCodexModels();
        if (!cancelled) {
          setModels(available);
          setModelsError(null);
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
          setModelsError(apiError instanceof Error ? apiError.message : 'Failed to load models');
        }
      }
    };

    void fetchModels();

    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch branches when project changes
  useEffect(() => {
    if (!form.projectId) {
      setBranchOptions([]);
      return;
    }

    listProjectBranches(Number(form.projectId), { perPage: 20 })
      .then((response) => {
        setBranchOptions(response.items);
      })
      .catch(() => {
        setBranchOptions([]);
      });
  }, [form.projectId]);

  // Fetch recent tasks when project changes
  useEffect(() => {
    if (!form.projectId) {
      setRecentTasks([]);
      return;
    }

    setRecentTasksLoading(true);
    listTasks({ projectId: Number(form.projectId), limit: 5 })
      .then((response) => {
        setRecentTasks(response.items);
      })
      .catch(() => {
        setRecentTasks([]);
      })
      .finally(() => {
        setRecentTasksLoading(false);
      });
  }, [form.projectId]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // Mark all required fields as touched
    setTouchedFields(new Set(requiredFields));

    // Validate form
    if (!validateForm()) {
      setError('Please fix the errors in the form before submitting');
      return;
    }

    if (!patStatus.configured) {
      setError('Configure a GitLab PAT before submitting tasks');
      return;
    }

    const normalizedMrTitle = form.mrTitle.replace(/\s+/g, ' ').trim();

    const payload: TaskCreatePayload = {
      project_id: Number(form.projectId),
      prompt: form.prompt,
      mr_title: normalizedMrTitle,
      change_mode: form.changeMode,
    };

    if (form.targetBranch.trim()) {
      payload.target_branch = form.targetBranch.trim();
    }
    if (form.branchName.trim()) {
      payload.branch_name = form.branchName.trim();
    }
    if (form.codexModel) {
      payload.codex_model = form.codexModel;
    }
    if (form.codexReasoningEffort) {
      payload.codex_reasoning_effort = form.codexReasoningEffort;
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
      setSuccessMessage(`Task #${task.id} created and queued for processing`);
      setForm((prev) => ({ ...prev, prompt: '', mrTitle: '' }));
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : 'Failed to submit task');
    } finally {
      setSubmitting(false);
    }
  };

  const projectOptions = projects.map((project) => ({
    value: String(project.id),
    label: project.name,
  }));

  const modelOptions = models.map((model) => ({
    value: model.id,
    label: model.label,
  }));

  const reasoningOptions = [
    { value: 'low', label: 'Low (Fastest)' },
    { value: 'medium', label: 'Medium (Balanced)' },
    { value: 'high', label: 'High (Deepest)' },
  ];

  const bannerMessage = error ?? projectsError ?? patStatusError ?? modelsError;

  return (
    <ErrorBoundary>
      <div className="task-submit-page">
        {bannerMessage && (
          <InfoPanel variant="error" title="Error" className="page-banner">
            {bannerMessage}
          </InfoPanel>
        )}

        <div className="task-submit-grid">
        {/* Left Column: Task Submission Form */}
        <div className="task-submit-main">
          <Card className="task-submit-card">
            <div className="task-submit-card-header">
              <h3 className="task-submit-card-title">Task Submission</h3>
            </div>

            <form onSubmit={handleSubmit} className="task-form">
              <Select
                label="Project"
                required
                tooltip="Select the GitLab project where the task will be executed"
                value={form.projectId}
                onChange={(e) => {
                  const nextProjectId = e.target.value;
                  const selected = projects.find((project) => String(project.id) === nextProjectId);
                  handleFieldChange('projectId', nextProjectId);
                  setForm((prev) => ({
                    ...prev,
                    projectId: nextProjectId,
                    targetBranch: selected?.default_branch ?? prev.targetBranch,
                  }));
                }}
                onBlur={() => handleFieldBlur('projectId')}
                options={projectOptions}
                placeholder={projects.length === 0 ? "No projects available - add one in Projects page" : "Select a project..."}
                disabled={projectsLoading || !projects.length}
                error={touchedFields.has('projectId') ? fieldErrors.projectId || undefined : undefined}
                success={touchedFields.has('projectId') && !fieldErrors.projectId && !!form.projectId}
                hint={projects.length === 0 ? "You need to add at least one project before submitting tasks" : undefined}
              />

              <div className="change-mode-field">
                <label className="change-mode-label">
                  Change Destination
                </label>
                <div className="change-mode-segmented">
                  <button
                    type="button"
                    className={`change-mode-button ${form.changeMode === 'merge_request' ? 'active' : ''}`}
                    onClick={() => handleFieldChange('changeMode', 'merge_request')}
                    title="Create a new branch and open a merge request for review"
                  >
                    <Icon type="git-merge" size={18} />
                    Create Merge Request
                  </button>
                  <button
                    type="button"
                    className={`change-mode-button ${isBranchCommit ? 'active' : ''}`}
                    onClick={() => handleFieldChange('changeMode', 'branch_commit')}
                    title="Commit changes directly to an existing branch"
                  >
                    <Icon type="git-branch" size={18} />
                    Update Existing Branch
                  </button>
                </div>
                <p className="change-mode-hint">
                  {form.changeMode === 'merge_request'
                    ? 'Creates a new task branch from the base branch and opens a merge request'
                    : 'Commits changes directly to the target branch without creating a merge request'}
                </p>
              </div>

              <div className="field-grid field-grid-two">
                <TextInput
                  label={isBranchCommit ? 'Target Branch' : 'Base Branch'}
                  tooltip={
                    isBranchCommit
                      ? 'The existing branch where commits will be pushed directly'
                      : 'The branch to use as the base for creating the new task branch'
                  }
                  value={form.targetBranch}
                  onChange={(e) => handleFieldChange('targetBranch', e.target.value)}
                  onBlur={() => handleFieldBlur('targetBranch')}
                  placeholder={selectedProject?.default_branch || 'main'}
                  hint="Start typing to see suggestions from your repository"
                  list="branch-suggestions"
                />

                {!isBranchCommit && (
                  <TextInput
                    label="Branch Name (Optional)"
                    tooltip="Custom branch name for the new task branch (leave empty to auto-generate based on task and date)"
                    value={form.branchName}
                    onChange={(e) => handleFieldChange('branchName', e.target.value)}
                    onBlur={() => handleFieldBlur('branchName')}
                    placeholder="feature/new-functionality"
                    hint="Leave empty to auto-generate (e.g., codex/task-2025-01-15-42)"
                    className="field-with-transition"
                  />
                )}
              </div>

              {branchOptions.length > 0 && (
                <datalist id="branch-suggestions">
                  {branchOptions.map((branch) => (
                    <option key={branch.name} value={branch.name} />
                  ))}
                </datalist>
              )}

              <TextInput
                label={isBranchCommit ? 'Commit Message' : 'Merge Request Title'}
                required
                tooltip={
                  isBranchCommit
                    ? 'A concise summary for the commit that will be pushed to the selected branch'
                    : 'A clear, descriptive title for the merge request that will be created'
                }
                value={form.mrTitle}
                onChange={(e) => handleFieldChange('mrTitle', e.target.value)}
                onBlur={() => handleFieldBlur('mrTitle')}
                placeholder={
                  isBranchCommit ? 'Describe the commit (e.g., Update navigation links)' : 'Implement new feature or fix'
                }
                maxLength={240}
                hint={
                  isBranchCommit
                    ? 'This becomes the commit summary on the existing branch'
                    : 'Clear, descriptive title for your merge request'
                }
                showCharCount
                error={touchedFields.has('mrTitle') ? fieldErrors.mrTitle || undefined : undefined}
                success={touchedFields.has('mrTitle') && !fieldErrors.mrTitle && !!form.mrTitle.trim()}
              />

              <TextArea
                label="Task Instructions"
                required
                tooltip="Detailed description of what you want the AI agent to accomplish"
                value={form.prompt}
                onChange={(e) => handleFieldChange('prompt', e.target.value)}
                onBlur={() => handleFieldBlur('prompt')}
                placeholder={`Describe what you want the AI agent to accomplish...

Example:
- Add user authentication to the login page
- Fix the memory leak in the data processing module
- Implement responsive design for mobile devices
- Add unit tests for the payment service`}
                rows={9}
                hint="Be specific about requirements, constraints, and expected outcomes"
                error={touchedFields.has('prompt') ? fieldErrors.prompt || undefined : undefined}
                success={touchedFields.has('prompt') && !fieldErrors.prompt && !!form.prompt.trim()}
                aria-label="Prompt"
              />
              <div className="field-grid field-grid-two">
                <Select
                  label="AI Model"
                  tooltip="The AI model to use for processing this task"
                  value={form.codexModel}
                  onChange={(e) => setForm((prev) => ({ ...prev, codexModel: e.target.value }))}
                  options={modelOptions}
                  placeholder="Select a model"
                  disabled={!models.length}
                />

                <Select
                  label="Reasoning Effort"
                  tooltip="How much computational effort the AI should use (higher = more thorough but slower)"
                  value={form.codexReasoningEffort}
                  onChange={(e) => setForm((prev) => ({ ...prev, codexReasoningEffort: e.target.value as 'low' | 'medium' | 'high' }))}
                  options={reasoningOptions}
                  hint="Higher effort = more thorough analysis, longer processing time"
                />
              </div>

              {!patStatus.configured && (
                <InfoPanel
                  variant="warning"
                  title="GitLab PAT Required"
                  icon={<Icon type="alert" size={20} />}
                  className="task-submit-callout"
                >
                  <p>A GitLab Personal Access Token is required to push changes. Configure it in Settings before submitting tasks.</p>
                  <Button
                    variant="primary"
                    size="small"
                    onClick={() => navigate('/settings')}
                    style={{ marginTop: '0.75rem' }}
                    type="button"
                  >
                    Go to Settings →
                  </Button>
                </InfoPanel>
              )}

              <div className="task-submit-actions">
                <Button
                  type="submit"
                  variant="primary"
                  size="medium"
                  className="task-submit-primary"
                  disabled={submitting || projectsLoading || !projects.length || !patStatus.configured}
                >
                  {submitting ? 'Submitting Task...' : 'Submit Task'}
                </Button>
              </div>
            </form>
          </Card>
        </div>

        {/* Right Column: Status and Recent Tasks */}
        <div className="task-submit-sidebar">
          {/* Compact Credential Status */}
          <Card>
            <h3 className="card-section-title">
              {patStatus.configured ? 'Credentials Ready' : 'Setup Required'}
            </h3>

            {/* GitLab PAT Status Row */}
            <div className="status-row">
              <div className="status-label">GitLab PAT</div>
              <div className="status-actions">
                <div className="status-actions-group">
                  <StatusBadge status={patStatus.configured ? 'configured' : 'missing'} />
                  {patStatus.configured ? (
                    <Button
                      variant="secondary"
                      size="small"
                      onClick={() => navigate('/settings')}
                    >
                      Verify
                    </Button>
                  ) : (
                    <Button
                      variant="primary"
                      size="small"
                      onClick={() => navigate('/settings')}
                    >
                      Configure →
                    </Button>
                  )}
                </div>
              </div>
            </div>

            {/* Verification Detail (Progressive Disclosure) */}
            {patStatus.configured && patStatus.verification_checked_at && (
              <div className="status-detail">
                <Icon type="info" size={14} />
                <span>
                  {patStatus.verification_host && `${patStatus.verification_host} • `}
                  Verified {formatTimestamp(patStatus.verification_checked_at)}
                </span>
              </div>
            )}

            {/* Active Project Row */}
            <div className="status-row">
              <div className="status-label">Project</div>
              <div className="status-actions">
                {selectedProject ? (
                  <>
                    <span className="status-value">{selectedProject.name}</span>
                    <Button
                      variant="secondary"
                      size="small"
                      onClick={() => navigate('/projects')}
                    >
                      Change
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="primary"
                    size="small"
                    onClick={() => navigate('/projects')}
                  >
                    Select →
                  </Button>
                )}
              </div>
            </div>

            {/* Compact Quick Links Row */}
            <div className="quick-actions-compact">
              <Button
                variant="secondary"
                size="small"
                onClick={() => navigate('/tasks')}
              >
                Tasks
              </Button>
              <Button
                variant="secondary"
                size="small"
                onClick={() => navigate('/help')}
              >
                Help
              </Button>
            </div>
          </Card>

          {/* Recent Tasks Section */}
          {selectedProject && (
            <Card>
              <div className="recent-tasks-header">
                <h3 className="card-section-title">
                  Recent Tasks
                  {!recentTasksLoading && recentTasks.length > 0 && (
                    <span className="task-count"> ({recentTasks.length})</span>
                  )}
                </h3>
              </div>

              {recentTasksLoading ? (
                <div className="recent-tasks-loading">
                  <Icon type="info" size={16} />
                  <span>Loading tasks...</span>
                </div>
              ) : recentTasks.length === 0 ? (
                <div className="recent-tasks-empty">
                  <Icon type="info" size={16} />
                  <span>No tasks yet for this project</span>
                </div>
              ) : (
                <>
                  <div className="recent-tasks-list">
                    {recentTasks.map((task) => (
                      <div
                        key={task.id}
                        className="recent-task-item"
                        onClick={() => navigate('/tasks', { state: { focusTaskId: task.id } })}
                      >
                        <div className="recent-task-header">
                          <span className="recent-task-id">#{task.id}</span>
                          <StatusBadge status={task.status} size="small" />
                        </div>
                        <div className="recent-task-meta">
                          <span className="recent-task-time">
                            {formatTimestamp(task.created_at)}
                          </span>
                          <span className={`recent-task-mode recent-task-mode-${task.change_mode}`}>
                            {task.change_mode === 'branch_commit' ? 'Branch commit' : 'Merge request'}
                          </span>
                          <span className="recent-task-branch">
                            {task.branch ?? 'Auto branch'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="recent-tasks-footer">
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => navigate('/tasks', { state: { projectFilter: selectedProject.id } })}
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      View all tasks →
                    </Button>
                  </div>
                </>
              )}
            </Card>
          )}

          {successMessage && createdTaskId && (
            <Card className="task-success-card alert alert-success">
              <div className="success-message">
                <div className="success-icon"><Icon type="check" size={24} /></div>
                <div className="success-content">
                  <h4>Task Created Successfully</h4>
                  <p>
                    <span className="sr-only">Task {createdTaskId} created.</span>
                    {successMessage}
                  </p>
                  <Button
                    variant="primary"
                    size="small"
                    onClick={() => navigate('/tasks', { state: { focusTaskId: createdTaskId } })}
                    style={{ marginTop: '0.75rem' }}
                    aria-label={`View Task ${createdTaskId}`}
                  >
                    View Task Details →
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
      </div>
    </ErrorBoundary>
  );
}

export default TaskSubmitPage;
