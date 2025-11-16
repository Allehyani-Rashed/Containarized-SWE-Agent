import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './App.css';

type Project = {
  id: number;
  name: string;
  local_path: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  created_at: string;
  codex_token_configured: boolean;
  codex_token_updated_at: string | null;
};

type PatStatus = {
  configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
  session_configured: boolean;
  session_updated_at: string | null;
  session_updated_by: string | null;
  active_credential: 'api_token' | 'session' | 'none';
  verification_status: 'verified' | 'error' | null;
  verification_checked_at: string | null;
  verification_error: string | null;
  verification_host: string | null;
};

type Task = {
  id: number;
  project_id: number;
  prompt: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  agent_type: 'codex' | 'claude-code';
  model: string | null;
  allowlist: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  branch: string | null;
  mr_url: string | null;
  workspace_path: string | null;
  codex_agent_version: string | null;
  codex_invocation: string | null;
};

type CopyState = 'idle' | 'success' | 'error';

const initialProjectForm = {
  name: '',
  local_path: '',
  default_branch: 'main',
  gitlab_host: 'https://gitlab.com',
  gitlab_project_path: '',
  codex_token: '',
};

const initialTaskForm = {
  projectId: '',
  prompt: '',
  agent_type: 'codex',
  model: '',
  allowlist: '',
};

const initialPatStatus: PatStatus = {
  configured: false,
  updated_at: null,
  updated_by: null,
  session_configured: false,
  session_updated_at: null,
  session_updated_by: null,
  active_credential: 'none',
  verification_status: null,
  verification_checked_at: null,
  verification_error: null,
  verification_host: null,
};

const initialPatForm = {
  token: '',
  actor: '',
};

const initialSessionForm = {
  bundle: '',
  actor: '',
};

const formatTimestamp = (value: string | null) => {
  if (!value) {
    return '--';
  }
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
};

const mapPatStatus = (data: PatStatus): PatStatus => ({
  configured: data.configured,
  updated_at: data.updated_at ?? null,
  updated_by: data.updated_by ?? null,
  session_configured: data.session_configured ?? false,
  session_updated_at: data.session_updated_at ?? null,
  session_updated_by: data.session_updated_by ?? null,
  active_credential: data.active_credential ?? 'none',
  verification_status: data.verification_status ?? null,
  verification_checked_at: data.verification_checked_at ?? null,
  verification_error: data.verification_error ?? null,
  verification_host: data.verification_host ?? null,
});

const orderTasks = (items: Task[]) => {
  return [...items].sort((a, b) => {
    const aTime = Date.parse(a.created_at) || 0;
    const bTime = Date.parse(b.created_at) || 0;
    return bTime - aTime;
  });
};

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projectForm, setProjectForm] = useState(initialProjectForm);
  const [projectSubmitting, setProjectSubmitting] = useState(false);

  const [taskForm, setTaskForm] = useState(initialTaskForm);
  const [taskSubmitting, setTaskSubmitting] = useState(false);

  const [patStatus, setPatStatus] = useState<PatStatus>(initialPatStatus);
  const [patForm, setPatForm] = useState(initialPatForm);
  const [patMessage, setPatMessage] = useState<string | null>(null);
  const [patSubmitting, setPatSubmitting] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<'success' | 'error' | null>(null);
  const [verifySubmitting, setVerifySubmitting] = useState(false);
  const [clearModalOpen, setClearModalOpen] = useState(false);
  const [clearSubmitting, setClearSubmitting] = useState(false);
  const [clearActor, setClearActor] = useState('');
  const [sessionForm, setSessionForm] = useState(initialSessionForm);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [sessionSubmitting, setSessionSubmitting] = useState(false);
  const [sessionFileName, setSessionFileName] = useState<string | null>(null);
  const [sessionClearSubmitting, setSessionClearSubmitting] = useState(false);
  const [sessionClearActor, setSessionClearActor] = useState('');
  const [sessionClearModalOpen, setSessionClearModalOpen] = useState(false);

  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [taskLookupId, setTaskLookupId] = useState('');
  const [taskDetail, setTaskDetail] = useState<Task | null>(null);
  const [taskLogs, setTaskLogs] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<CopyState>('idle');

  const logContainerRef = useRef<HTMLPreElement | null>(null);
  const copyResetRef = useRef<number | null>(null);

  const projectMap = useMemo(() => {
    const map = new Map<number, Project>();
    projects.forEach((project) => {
      map.set(project.id, project);
    });
    return map;
  }, [projects]);

  const activeCredentialLabel = useMemo(() => {
    switch (patStatus.active_credential) {
      case 'api_token':
        return 'Codex API token';
      case 'session':
        return 'ChatGPT session bundle';
      default:
        return 'None';
    }
  }, [patStatus.active_credential]);

  const renderCodexCredential = (project: Project) => {
    if (project.codex_token_configured) {
      return (
        <>
          <span className="status status-done">Configured</span>
          {project.codex_token_updated_at ? (
            <div className="meta">Updated {formatTimestamp(project.codex_token_updated_at)}</div>
          ) : null}
        </>
      );
    }

    if (patStatus.session_configured) {
      return (
        <>
          <span className="status status-done">Session bundle</span>
          {patStatus.session_updated_at ? (
            <div className="meta">Imported {formatTimestamp(patStatus.session_updated_at)}</div>
          ) : (
            <div className="meta">Using ChatGPT session bundle</div>
          )}
        </>
      );
    }

    return <span className="status status-failed">Missing</span>;
  };

  const fetchPatStatus = useCallback(async () => {
    try {
      const res = await fetch('/integrations/pat');
      if (!res.ok) {
        throw new Error('Failed to load PAT status');
      }
      const data = (await res.json()) as PatStatus;
      setPatStatus(mapPatStatus(data));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch('/projects');
      if (!res.ok) {
        throw new Error('Failed to load projects');
      }
      const data = (await res.json()) as Project[];
      setProjects(data);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const handlePatStore = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!patForm.token.trim()) {
      setError('Token is required to store the PAT');
      return;
    }
    setPatSubmitting(true);
    setPatMessage(null);
    setSessionMessage(null);
    setError(null);
    setVerifyMessage(null);
    setVerifyResult(null);
    try {
      const payload = {
        token: patForm.token.trim(),
        updated_by: patForm.actor.trim() ? patForm.actor.trim() : null,
      };
      const res = await fetch('/integrations/pat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error('Failed to store the PAT');
      }
      const data = (await res.json()) as PatStatus;
      setPatStatus(mapPatStatus(data));
      setPatForm(initialPatForm);
      setPatMessage('Personal access token stored successfully.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPatSubmitting(false);
    }
  };

  const handlePatClear = async () => {
    setClearSubmitting(true);
    setPatMessage(null);
    setSessionMessage(null);
    setError(null);
    setVerifyMessage(null);
    setVerifyResult(null);
    try {
      const payload = clearActor.trim() ? { updated_by: clearActor.trim() } : {};
      const res = await fetch('/integrations/pat', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error('Failed to clear the PAT');
      }
      const data = (await res.json()) as PatStatus;
      setPatStatus(mapPatStatus(data));
      setPatMessage('Personal access token cleared. Tasks will fail until a new token is configured.');
      setClearActor('');
      setClearModalOpen(false);
      setPatForm(initialPatForm);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setClearSubmitting(false);
    }
  };

  const handlePatVerify = async () => {
    setVerifySubmitting(true);
    setVerifyMessage(null);
    setVerifyResult(null);
    setPatMessage(null);
    setSessionMessage(null);
    setError(null);
    try {
      const payload: Record<string, string> = {};
      if (patStatus.verification_host) {
        payload.gitlab_host = patStatus.verification_host;
      } else if (projects.length && projects[0]?.gitlab_host) {
        payload.gitlab_host = projects[0].gitlab_host;
      }

      const res = await fetch('/integrations/pat/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorPayload = (await res.json().catch(() => null)) as { detail?: string } | null;
        const message = errorPayload?.detail ?? 'Failed to verify the GitLab PAT';
        setVerifyResult('error');
        setVerifyMessage(message);
        setError(message);
        return;
      }

      const data = (await res.json()) as PatStatus;
      const mapped = mapPatStatus(data);
      setPatStatus(mapped);

      if (mapped.verification_status === 'verified') {
        const hostLabel = mapped.verification_host ?? 'GitLab';
        setVerifyResult('success');
        setVerifyMessage(`PAT verified against ${hostLabel}.`);
      } else {
        const fallbackMessage =
          mapped.verification_error ?? 'Verification completed but the result was inconclusive.';
        setVerifyResult('error');
        setVerifyMessage(fallbackMessage);
      }
    } catch (err) {
      const message = (err as Error).message || 'Unable to verify GitLab PAT';
      setVerifyResult('error');
      setVerifyMessage(message);
      setError(message);
    } finally {
      setVerifySubmitting(false);
    }
  };

  const handleSessionImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sessionForm.bundle.trim()) {
      setError('Session bundle content is required');
      return;
    }
    setSessionSubmitting(true);
    setSessionMessage(null);
    setPatMessage(null);
    setError(null);
    try {
      const payload = {
        bundle: sessionForm.bundle,
        updated_by: sessionForm.actor.trim() ? sessionForm.actor.trim() : null,
      };
      const res = await fetch('/integrations/pat/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error('Failed to import ChatGPT session bundle');
      }
      const data = (await res.json()) as PatStatus;
      setPatStatus(mapPatStatus(data));
      setSessionForm(initialSessionForm);
      setSessionFileName(null);
      setSessionMessage('ChatGPT session bundle imported successfully.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSessionSubmitting(false);
    }
  };

  const handleSessionFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files && event.target.files[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      setSessionForm((prev) => ({ ...prev, bundle: result }));
      setSessionFileName(file.name);
    };
    reader.onerror = () => {
      setError(`Failed to read ${file.name}`);
    };
    reader.readAsText(file);
  };

  const handleSessionClear = async () => {
    setSessionClearSubmitting(true);
    setSessionMessage(null);
    setPatMessage(null);
    setError(null);
    try {
      const payload = sessionClearActor.trim() ? { updated_by: sessionClearActor.trim() } : {};
      const res = await fetch('/integrations/pat/session', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error('Failed to clear the ChatGPT session bundle');
      }
      const data = (await res.json()) as PatStatus;
      setPatStatus(mapPatStatus(data));
      setSessionMessage('ChatGPT session bundle cleared. Import a fresh bundle to continue.');
      setSessionForm(initialSessionForm);
      setSessionFileName(null);
      setSessionClearActor('');
      setSessionClearModalOpen(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSessionClearSubmitting(false);
    }
  };

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch('/tasks');
      if (!res.ok) {
        throw new Error('Failed to load tasks');
      }
      const data = (await res.json()) as Task[];
      setTasks(orderTasks(data));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const refreshTaskDetail = useCallback(
    async (taskId: number, force?: boolean) => {
      if (
        !force &&
        taskDetail &&
        taskDetail.id === taskId &&
        (taskDetail.status === 'done' || taskDetail.status === 'failed')
      ) {
        return taskDetail;
      }
      try {
        const res = await fetch(`/tasks/${taskId}`);
        if (!res.ok) {
          throw new Error('Task not found');
        }
        const data = (await res.json()) as Task;
        setTaskDetail(data);
        setTasks((prev) => {
          const exists = prev.some((item) => item.id === data.id);
          if (exists) {
            return orderTasks(prev.map((item) => (item.id === data.id ? data : item)));
          }
          return orderTasks([...prev, data]);
        });
        return data;
      } catch (err) {
        setError((err as Error).message);
        return null;
      }
    },
    [taskDetail],
  );

  useEffect(() => {
    void fetchProjects();
    void fetchTasks();
  }, [fetchProjects, fetchTasks]);

  useEffect(() => {
    void fetchPatStatus();
  }, [fetchPatStatus]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void fetchPatStatus();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [fetchPatStatus]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void fetchTasks();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [fetchTasks]);

  useEffect(() => {
    if (!projects.length) {
      return;
    }
    setTaskForm((prev) => ({ ...prev, projectId: prev.projectId || String(projects[0].id) }));
  }, [projects]);

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }
    let cancelled = false;
    let eventSource: EventSource | null = null;

    const openStream = async () => {
      try {
        const snapshot = await fetch(`/tasks/${selectedTaskId}/logs?follow=0`);
        if (!snapshot.ok) {
          throw new Error('Failed to load log snapshot');
        }
        const data = (await snapshot.json()) as { entries?: string[] };
        if (!cancelled) {
          setCopyState('idle');
          setTaskLogs(data.entries ?? []);
        }
      } catch (err) {
        if (!cancelled) {
          setTaskLogs([]);
        }
      }

      eventSource = new EventSource(`/tasks/${selectedTaskId}/logs`);
      setIsStreaming(true);
      eventSource.onmessage = (event) => {
        if (cancelled) {
          return;
        }
        const message = event.data as string;
        if (message) {
          setTaskLogs((prev) => [...prev, message]);
        }
      };
      eventSource.addEventListener('done', async () => {
        if (!cancelled) {
          setIsStreaming(false);
          await refreshTaskDetail(selectedTaskId, true);
        }
        eventSource?.close();
      });
      eventSource.onerror = () => {
        if (!cancelled) {
          setIsStreaming(false);
        }
        eventSource?.close();
      };
    };

    void openStream();

    return () => {
      cancelled = true;
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [selectedTaskId, refreshTaskDetail]);

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }

    let interval: number | undefined;

    const poll = async () => {
      const detail = await refreshTaskDetail(selectedTaskId);
      if (detail && (detail.status === 'done' || detail.status === 'failed')) {
        if (interval !== undefined) {
          window.clearInterval(interval);
          interval = undefined;
        }
      }
    };

    interval = window.setInterval(() => {
      void poll();
    }, 1000);

    void poll();

    return () => {
      if (interval !== undefined) {
        window.clearInterval(interval);
      }
    };
  }, [selectedTaskId, refreshTaskDetail]);

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [taskLogs]);

  useEffect(() => {
    return () => {
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
    };
  }, []);

  const handleProjectSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setProjectSubmitting(true);
    setError(null);
    try {
      const trimmedCodex = projectForm.codex_token.trim();
      const payload = {
        ...projectForm,
        codex_token: trimmedCodex.length ? trimmedCodex : null,
      };

      const res = await fetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error('Failed to register project');
      }
      await fetchProjects();
      setProjectForm(initialProjectForm);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setProjectSubmitting(false);
    }
  };

  const handleTaskSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!taskForm.projectId || !taskForm.prompt.trim()) {
      setError('Project and prompt are required');
      return;
    }
    if (!patStatus.configured) {
      setError('Configure a GitLab PAT before submitting tasks');
      return;
    }
    setTaskSubmitting(true);
    setError(null);
    try {
      const allowlist = taskForm.allowlist
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      const res = await fetch('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: Number(taskForm.projectId),
          prompt: taskForm.prompt,
          agent_type: taskForm.agent_type,
          model: taskForm.model || null,
          allowlist,
        }),
      });
      if (!res.ok) {
        throw new Error('Failed to submit task');
      }
      const data = (await res.json()) as Task;
      setSelectedTaskId(data.id);
      setTaskLookupId(String(data.id));
      setTaskDetail(data);
      setTaskLogs([]);
      setCopyState('idle');
      setTaskForm((prev) => ({ ...prev, prompt: '' }));
      await fetchTasks();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTaskSubmitting(false);
    }
  };

  const handleTaskLookup = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!taskLookupId.trim()) {
      return;
    }
    const id = Number(taskLookupId);
    if (Number.isNaN(id)) {
      setError('Task ID must be a number');
      return;
    }
    setSelectedTaskId(id);
    setTaskLogs([]);
    setCopyState('idle');
    void refreshTaskDetail(id, true);
  };

  const handleTaskSelect = (task: Task) => {
    setSelectedTaskId(task.id);
    setTaskLookupId(String(task.id));
    setTaskDetail(task);
    setTaskLogs([]);
    setCopyState('idle');
    setError(null);
    void refreshTaskDetail(task.id, true);
  };

  const handleCopyLogs = async () => {
    if (!taskLogs.length) {
      return;
    }
    if (copyResetRef.current !== null) {
      window.clearTimeout(copyResetRef.current);
    }
    try {
      if (!navigator.clipboard) {
        throw new Error('Clipboard API unavailable');
      }
      await navigator.clipboard.writeText(taskLogs.join('\n'));
      setCopyState('success');
    } catch (err) {
      setCopyState('error');
    }
    copyResetRef.current = window.setTimeout(() => {
      setCopyState('idle');
    }, 2000);
  };

  const selectedProject = taskDetail ? projectMap.get(taskDetail.project_id) ?? null : null;

  return (
    <div className="app">
      <header className="hero">
        <h1>Containerized Codex Agent</h1>
        <p>Register projects, submit codex tasks, and monitor results locally.</p>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="panel">
        <h2>Settings</h2>
        <div className="settings-grid">
          <div className="integrations-card">
            <h3>Credentials</h3>
            <div className="credential-summary">
              <div className="summary-row">
                <span>GitLab PAT</span>
                <span
                  className={patStatus.configured ? 'status status-done' : 'status status-failed'}
                  title="GitLab PATs are write-only; we only track whether a token is stored for this environment"
                >
                  {patStatus.configured ? 'Configured' : 'Missing'}
                </span>
              </div>
              <div className="summary-meta">
                <span>Last update: {formatTimestamp(patStatus.updated_at)}</span>
                <span>Updated by: {patStatus.updated_by ? patStatus.updated_by : '--'}</span>
              </div>
              {!patStatus.configured && (
                <p className="pat-hint">
                  Seeing “Missing” after storing a token elsewhere? Configure the PAT on this machine so the
                  runner can reuse it.
                </p>
              )}
              <div className="summary-row">
                <span>PAT Verification</span>
                <span
                  className={
                    patStatus.verification_status === 'verified'
                      ? 'status status-done'
                      : patStatus.verification_status === 'error'
                      ? 'status status-failed'
                      : 'status status-pending'
                  }
                  title="Use Verify PAT access to confirm connectivity without exposing the token"
                >
                  {patStatus.verification_status === 'verified'
                    ? 'Verified'
                    : patStatus.verification_status === 'error'
                    ? 'Check failed'
                    : 'Not run'}
                </span>
              </div>
              <div className="summary-meta">
                <span>Last check: {formatTimestamp(patStatus.verification_checked_at)}</span>
                <span>Target host: {patStatus.verification_host ? patStatus.verification_host : '--'}</span>
              </div>
              {patStatus.verification_status === 'error' && patStatus.verification_error ? (
                <p className="pat-hint pat-hint-error">
                  Last verification failed: {patStatus.verification_error}
                </p>
              ) : null}
              <div className="summary-row">
                <span>ChatGPT Session</span>
                <span className={patStatus.session_configured ? 'status status-done' : 'status status-failed'}>
                  {patStatus.session_configured ? 'Configured' : 'Missing'}
                </span>
              </div>
              <div className="summary-meta">
                <span>Last import: {formatTimestamp(patStatus.session_updated_at)}</span>
                <span>Updated by: {patStatus.session_updated_by ? patStatus.session_updated_by : '--'}</span>
              </div>
              <div className="summary-meta">
                <span>Active credential: {activeCredentialLabel}</span>
              </div>
            </div>
            <p className="pat-hint">
              GitLab PATs are write-only; we encrypt the token and never render the secret after storage.
            </p>
            <p className="pat-hint">
              Status labels reflect this environment. Clearing secrets or switching machines will show “Missing”
              until a new token is stored.
            </p>
            {!patStatus.configured && (
              <div className="notice notice-warning">
                <strong>GitLab PAT required.</strong>{' '}
                Provide a project-scoped personal access token with API access.{' '}
                <a
                  href="https://github.com/openai/codex/tree/main/docs/authentication.md#gitlab-personal-access-tokens"
                  target="_blank"
                  rel="noreferrer"
                >
                  Review the PAT troubleshooting guide
                </a>
                .
              </div>
            )}
            {patMessage && <div className="notice notice-success">{patMessage}</div>}
            {sessionMessage && <div className="notice notice-success">{sessionMessage}</div>}
            {verifyMessage && (
              <div
                className={`notice ${
                  verifyResult === 'success' ? 'notice-success' : 'notice-warning'
                }`}
              >
                {verifyMessage}
              </div>
            )}
            <div className="credential-forms">
              <div className="credential-block">
                <h4>Store GitLab PAT</h4>
                <form className="form pat-form" onSubmit={handlePatStore}>
                  <label>
                    New Token
                    <input
                      type="password"
                      value={patForm.token}
                      onChange={(event) => setPatForm({ ...patForm, token: event.target.value })}
                      placeholder="glpat-..."
                      required
                    />
                  </label>
                  <label>
                    Stored By (optional)
                    <input
                      type="text"
                      value={patForm.actor}
                      onChange={(event) => setPatForm({ ...patForm, actor: event.target.value })}
                      placeholder="operator name"
                    />
                  </label>
                  <button type="submit" disabled={patSubmitting}>
                    {patSubmitting ? 'Storing...' : 'Store Token'}
                  </button>
                </form>
                <button
                  type="button"
                  onClick={handlePatVerify}
                  disabled={verifySubmitting || !patStatus.configured}
                >
                  {verifySubmitting ? 'Verifying...' : 'Verify PAT access'}
                </button>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => {
                    setPatMessage(null);
                    setSessionMessage(null);
                    setError(null);
                    setClearModalOpen(true);
                  }}
                  disabled={clearSubmitting || !patStatus.configured}
                >
                  Clear PAT
                </button>
                <p className="pat-hint">
                  Clearing the token will abort pending tasks and block new submissions until a replacement is provided.
                </p>
              </div>

              <div className="credential-block">
                <h4>Import ChatGPT Session Bundle</h4>
                <p className="pat-hint">
                  Make sure Codex is installed locally and that you are logged in before copying the session bundle.
                </p>
                <p className="pat-hint">
                  macOS copy helper:<br/>
                  <code>cat ~/.codex/auth.json | pbcopy</code>
                </p>
                <p className="pat-hint">
                  linux copy helper:<br/>
                  <code>cat ~/.codex/auth.json | xclip -selection clipboard</code>
                </p>
                <p className="pat-hint">
                  windows copy helper:<br/>
                  <code>Get-Content $env:USERPROFILE\.codex\auth.json | Set-Clipboard</code>
                </p>
                <form className="form session-form" onSubmit={handleSessionImport}>
                  <label>
                    Session JSON
                    <textarea
                      value={sessionForm.bundle}
                      onChange={(event) => setSessionForm({ ...sessionForm, bundle: event.target.value })}
                      placeholder="Paste the contents of auth.json"

                      rows={6}
                      required
                    />
                  </label>
                  <label className="session-file-label">
                    Load from file
                    <input type="file" accept=".json,application/json" onChange={handleSessionFile} />
                  </label>
                  {sessionFileName && <p className="file-hint">Loaded from {sessionFileName}</p>}
                  <label>
                    Imported By (optional)
                    <input
                      type="text"
                      value={sessionForm.actor}
                      onChange={(event) => setSessionForm({ ...sessionForm, actor: event.target.value })}
                      placeholder="operator name"
                    />
                  </label>
                  <button type="submit" disabled={sessionSubmitting}>
                    {sessionSubmitting ? 'Importing...' : 'Import Session'}
                  </button>
                </form>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => {
                    setSessionMessage(null);
                    setError(null);
                    setSessionClearModalOpen(true);
                  }}
                  disabled={sessionClearSubmitting || !patStatus.session_configured}
                >
                  Clear Session Bundle
                </button>
                <p className="pat-hint">
                  Session bundles let Docker runs authenticate without a Codex API key. Import fresh bundles after updating
                  your credentials and clear them if they expire or are revoked.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>Projects</h2>
        <div className="panel-grid">
          <form className="form" onSubmit={handleProjectSubmit}>
            <h3>Register Project</h3>
            <label>
              Name
              <input
                type="text"
                value={projectForm.name}
                onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })}
                required
              />
            </label>
            <label>
              Local Path
              <input
                type="text"
                value={projectForm.local_path}
                onChange={(event) => setProjectForm({ ...projectForm, local_path: event.target.value })}
                required
              />
            </label>
            <label>
              Default Branch
              <input
                type="text"
                value={projectForm.default_branch}
                onChange={(event) => setProjectForm({ ...projectForm, default_branch: event.target.value })}
                required
              />
            </label>
            <label>
              GitLab Host
              <input
                type="text"
                value={projectForm.gitlab_host}
                onChange={(event) => setProjectForm({ ...projectForm, gitlab_host: event.target.value })}
                required
              />
            </label>
            <label>
              GitLab Project Path
              <input
                type="text"
                value={projectForm.gitlab_project_path}
                onChange={(event) => setProjectForm({ ...projectForm, gitlab_project_path: event.target.value })}
                required
              />
            </label>
            <label>
              Codex API Token (optional when a session bundle is configured)
              <input
                type="password"
                value={projectForm.codex_token}
                onChange={(event) => setProjectForm({ ...projectForm, codex_token: event.target.value })}
                placeholder="Codex access token"
              />
            </label>
            <button type="submit" disabled={projectSubmitting}>
              {projectSubmitting ? 'Registering...' : 'Register Project'}
            </button>
          </form>

          <div className="table-wrapper">
            <h3>Registered Projects</h3>
            {projects.length === 0 ? (
              <p className="empty">No projects registered yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Default Branch</th>
                    <th>GitLab</th>
                    <th>Codex Credential</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project) => (
                    <tr key={project.id}>
                      <td>{project.id}</td>
                      <td>{project.name}</td>
                      <td>{project.default_branch}</td>
                      <td>{project.gitlab_project_path}</td>
                      <td>{renderCodexCredential(project)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>Submit Task</h2>
        <form className="form" onSubmit={handleTaskSubmit}>
          <label>
            Project
            <select
              value={taskForm.projectId}
              onChange={(event) => setTaskForm({ ...taskForm, projectId: event.target.value })}
              required
            >
              <option value="" disabled>
                Select project
              </option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Agent Type
            <select
              value={taskForm.agent_type}
              onChange={(event) => {
                const newAgentType = event.target.value;
                setTaskForm({
                  ...taskForm,
                  agent_type: newAgentType,
                  model: newAgentType === 'claude-code' ? 'sonnet' : '',
                });
              }}
              required
            >
              <option value="codex">Codex CLI</option>
              <option value="claude-code">Claude Code</option>
            </select>
          </label>
          {taskForm.agent_type === 'claude-code' && (
            <label>
              Model
              <select
                value={taskForm.model}
                onChange={(event) => setTaskForm({ ...taskForm, model: event.target.value })}
                required
              >
                <option value="sonnet">Claude Sonnet 4.5</option>
                <option value="haiku">Claude Haiku 4.5</option>
              </select>
            </label>
          )}
          <label>
            Prompt
            <textarea
              value={taskForm.prompt}
              onChange={(event) => setTaskForm({ ...taskForm, prompt: event.target.value })}
              placeholder="Explain what the agent should do..."
              rows={4}
              required
            />
          </label>
          <label>
            Allowlist Domains (optional)
            <input
              type="text"
              value={taskForm.allowlist}
              onChange={(event) => setTaskForm({ ...taskForm, allowlist: event.target.value })}
              placeholder="domain1.com, domain2.com"
            />
          </label>
          {!patStatus.configured && (
            <p className="notice notice-warning">
              Personal access token missing. Store a token in Settings before submitting a task.
            </p>
          )}
          <button type="submit" disabled={taskSubmitting || !projects.length || !patStatus.configured}>
            {taskSubmitting ? 'Submitting...' : 'Create Task'}
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>Tasks</h2>
        <div className="table-wrapper">
          {tasks.length === 0 ? (
            <p className="empty">No tasks submitted yet.</p>
          ) : (
            <table className="task-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Project</th>
                  <th>Agent</th>
                  <th>Model</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Finished</th>
                  <th>Branch</th>
                  <th>Merge Request</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => {
                  const projectName = projectMap.get(task.project_id)?.name ?? String(task.project_id);
                  return (
                    <tr
                      key={task.id}
                      className={selectedTaskId === task.id ? 'active' : ''}
                      onClick={() => handleTaskSelect(task)}
                    >
                      <td>{task.id}</td>
                      <td>{projectName}</td>
                      <td>{task.agent_type === 'claude-code' ? 'Claude Code' : 'Codex CLI'}</td>
                      <td>{task.model ?? '--'}</td>
                      <td>
                        <span className={`status status-${task.status}`}>{task.status}</span>
                      </td>
                      <td>{formatTimestamp(task.created_at)}</td>
                      <td>{formatTimestamp(task.finished_at)}</td>
                      <td>{task.branch ?? '--'}</td>
                      <td>
                        {task.mr_url ? (
                          <a href={task.mr_url} target="_blank" rel="noreferrer">
                            {task.mr_url}
                          </a>
                        ) : (
                          '--'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {clearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear GitLab PAT?</h3>
            <p>
              Clearing the personal access token immediately fails any pending tasks and prevents new runs
              until a replacement token is configured. Running tasks continue with the credentials they
              already captured.
            </p>
            <label>
              Cleared By (optional)
              <input
                type="text"
                value={clearActor}
                onChange={(event) => setClearActor(event.target.value)}
                placeholder="operator name"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setClearModalOpen(false);
                  setClearActor('');
                }}
                disabled={clearSubmitting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={() => {
                  void handlePatClear();
                }}
                disabled={clearSubmitting}
              >
                {clearSubmitting ? 'Clearing...' : 'Clear Token'}
              </button>
            </div>
          </div>
        </div>
      )}

      {sessionClearModalOpen && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal">
            <h3>Clear ChatGPT Session Bundle?</h3>
            <p>
              Clearing the session bundle forces Docker tasks to rely on a Codex API token. Import a fresh
              bundle after clearing to continue using session-based authentication.
            </p>
            <label>
              Cleared By (optional)
              <input
                type="text"
                value={sessionClearActor}
                onChange={(event) => setSessionClearActor(event.target.value)}
                placeholder="operator name"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setSessionClearModalOpen(false);
                  setSessionClearActor('');
                }}
                disabled={sessionClearSubmitting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={() => {
                  void handleSessionClear();
                }}
                disabled={sessionClearSubmitting}
              >
                {sessionClearSubmitting ? 'Clearing...' : 'Clear Session'}
              </button>
            </div>
          </div>
        </div>
      )}

      <section className="panel">
        <h2>Task Detail</h2>
        <form className="lookup" onSubmit={handleTaskLookup}>
          <label htmlFor="task-id">Inspect Task ID</label>
          <div className="lookup-controls">
            <input
              id="task-id"
              type="number"
              value={taskLookupId}
              onChange={(event) => setTaskLookupId(event.target.value)}
              min={1}
            />
            <button type="submit">Load</button>
          </div>
        </form>

        {taskDetail ? (
          <div className="task-metadata">
            <dl>
              <div>
                <dt>Task ID</dt>
                <dd>{taskDetail.id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd className={`status status-${taskDetail.status}`}>{taskDetail.status}</dd>
              </div>
              <div>
                <dt>Project</dt>
                <dd>{selectedProject ? selectedProject.name : taskDetail.project_id}</dd>
              </div>
              <div>
                <dt>Prompt</dt>
                <dd>{taskDetail.prompt}</dd>
              </div>
              <div>
                <dt>Allowlist</dt>
                <dd>{taskDetail.allowlist.length ? taskDetail.allowlist.join(', ') : '--'}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{formatTimestamp(taskDetail.started_at)}</dd>
              </div>
              <div>
                <dt>Finished</dt>
                <dd>{formatTimestamp(taskDetail.finished_at)}</dd>
              </div>
              <div>
                <dt>Workspace Path</dt>
                <dd>{taskDetail.workspace_path ?? '--'}</dd>
              </div>
              <div>
                <dt>Branch</dt>
                <dd>{taskDetail.branch ?? '--'}</dd>
              </div>
              <div>
                <dt>Merge Request</dt>
                <dd>
                  {taskDetail.mr_url ? (
                    <a href={taskDetail.mr_url} target="_blank" rel="noreferrer">
                      {taskDetail.mr_url}
                    </a>
                  ) : (
                    '--'
                  )}
                </dd>
              </div>
              <div>
                <dt>Codex Agent</dt>
                <dd>{taskDetail.codex_agent_version ?? '--'}</dd>
              </div>
              <div>
                <dt>Codex Invocation</dt>
                <dd>{taskDetail.codex_invocation ?? '--'}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <p className="empty">Select or submit a task to see its details.</p>
        )}

        <div className="logs">
          <div className="logs-header">
            <h3>Logs</h3>
            <div className="logs-actions">
              {isStreaming && <span className="live-indicator">Live</span>}
              <button
                type="button"
                className="ghost-button"
                onClick={handleCopyLogs}
                disabled={!taskLogs.length}
              >
                {copyState === 'success' ? 'Copied!' : copyState === 'error' ? 'Copy failed' : 'Copy logs'}
              </button>
            </div>
          </div>
          {taskLogs.length ? (
            <pre className="log-output" ref={logContainerRef}>
              {taskLogs.map((line, index) => (
                <span key={`${line}-${index}`}>{line}\n</span>
              ))}
            </pre>
          ) : (
            <p className="empty">No logs yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

export default App;
