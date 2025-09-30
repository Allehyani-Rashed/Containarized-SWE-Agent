import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { abortTask, deleteTask, getTask, getTaskLogs, listTasks, TaskListParams } from '../api/tasks';
import { listCodexModels } from '../api/models';
import { Project, Task, CodexModel, TaskStatus } from '../types';
import { formatTimestamp } from '../utils/time';
import { useProjects } from '../hooks/useProjectsData';
import { useFocusTrap } from '../hooks/useFocusTrap';

const orderTasks = (items: Task[]) => {
  return [...items].sort((a, b) => {
    const aTime = Date.parse(a.created_at) || 0;
    const bTime = Date.parse(b.created_at) || 0;
    return bTime - aTime;
  });
};

type CopyState = 'idle' | 'success' | 'error';

type LocationState = {
  focusTaskId?: number;
};

const PAGE_SIZE = 25;
const MAX_PAGES = Math.floor(200 / PAGE_SIZE);
const STATUS_OPTIONS: TaskStatus[] = ['pending', 'running', 'done', 'failed', 'aborted'];

type TaskFilters = {
  statuses: TaskStatus[];
  codexModel: string;
  branch: string;
};

const initialFilters: TaskFilters = { statuses: [], codexModel: '', branch: '' };

const normalizeFilters = (filters: TaskFilters): TaskFilters => ({
  statuses: Array.from(new Set(filters.statuses)),
  codexModel: filters.codexModel,
  branch: filters.branch.trim(),
});

const formatReasoningEffort = (value: string | null | undefined) =>
  value ? value.charAt(0).toUpperCase() + value.slice(1) : 'Medium';

function TaskListPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskDetail, setTaskDetail] = useState<Task | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [taskLookupId, setTaskLookupId] = useState('');
  const [taskLogs, setTaskLogs] = useState<string[]>([]);
  const [logSnapshotMeta, setLogSnapshotMeta] = useState<
    {
      status: TaskStatus;
      branch: string | null;
      codex_model: string | null;
      codex_reasoning_effort: string | null;
      abort_requested: boolean;
    } | null
  >(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [copyState, setCopyState] = useState<CopyState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<'abort' | 'delete' | null>(null);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [filters, setFilters] = useState<TaskFilters>(initialFilters);
  const [filterDraft, setFilterDraft] = useState<TaskFilters>(initialFilters);
  const [pagesLoaded, setPagesLoaded] = useState(1);
  const [listMeta, setListMeta] = useState<{ total: number; nextOffset: number | null; limit: number }>(
    { total: 0, nextOffset: null, limit: PAGE_SIZE },
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [models, setModels] = useState<CodexModel[]>([]);

  const logContainerRef = useRef<HTMLPreElement | null>(null);
  const copyResetRef = useRef<number | null>(null);
  const modalCardRef = useRef<HTMLDivElement | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);
  const selectedTaskIdRef = useRef<number | null>(null);
  const logStreamRequestRef = useRef(0);
  const logSkipRef = useRef(0);
  const taskDetailRef = useRef<Task | null>(null);

  const updateSelectedTaskId = useCallback((nextId: number | null) => {
    selectedTaskIdRef.current = nextId;
    setSelectedTaskId(nextId);
  }, []);

  const applyTaskDetail = useCallback((detail: Task | null) => {
    taskDetailRef.current = detail;
    setTaskDetail(detail);
  }, []);

  const location = useLocation();
  const navigate = useNavigate();

  const { projects, error: projectsError, refreshProjects } = useProjects();

  const projectMap = useMemo(() => {
    const map = new Map<number, Project>();
    projects.forEach((project) => {
      map.set(project.id, project);
    });
    return map;
  }, [projects]);

  const fetchTasks = useCallback(
    async (
      context: 'initial' | 'filters' | 'loadMore' | 'refresh' = 'refresh',
      overridePages?: number,
      overrideFilters?: TaskFilters,
    ) => {
      const activeFilters = overrideFilters ?? filters;
      const effectivePages = overridePages ?? pagesLoaded;
      const limit = Math.min(PAGE_SIZE * effectivePages, 200);
      const params: TaskListParams = { limit, offset: 0 };
      if (activeFilters.statuses.length) {
        params.statuses = activeFilters.statuses;
      }
      if (activeFilters.codexModel) {
        params.codexModel = activeFilters.codexModel;
      }
      if (activeFilters.branch) {
        params.branch = activeFilters.branch;
      }

      const showSpinner = context === 'initial' || context === 'filters' || tasks.length === 0;
      if (showSpinner) {
        setIsLoading(true);
      }
      if (context === 'loadMore') {
        setIsLoadingMore(true);
      }

      try {
        const response = await listTasks(params);
        setTasks(orderTasks(response.items));
        setListMeta({
          total: response.total,
          nextOffset: response.next_offset,
          limit: response.limit,
        });
        setError(null);
      } catch (apiError) {
        setError(apiError instanceof Error ? apiError.message : 'Failed to load tasks');
      } finally {
        if (showSpinner) {
          setIsLoading(false);
        }
        if (context === 'loadMore') {
          setIsLoadingMore(false);
        }
      }
    },
    [filters, pagesLoaded, tasks.length],
  );

  useEffect(() => {
    void fetchTasks('initial');
    void refreshProjects();
  }, [fetchTasks, refreshProjects]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void fetchTasks('refresh');
    }, 5000);
    return () => window.clearInterval(interval);
  }, [fetchTasks]);

  useEffect(() => {
    let cancelled = false;

    const loadModels = async () => {
      try {
        const available = await listCodexModels();
        if (!cancelled) {
          setModels(available);
          setModelsError(null);
        }
      } catch (apiError) {
        if (!cancelled) {
          setModelsError(apiError instanceof Error ? apiError.message : 'Failed to load models');
        }
      }
    };

    void loadModels();

    return () => {
      cancelled = true;
    };
  }, []);

  const refreshTaskDetail = useCallback(
    async (taskId: number, force?: boolean) => {
      const currentDetail = taskDetailRef.current;
      if (
        !force &&
        currentDetail &&
        currentDetail.id === taskId &&
        (currentDetail.status === 'done' || currentDetail.status === 'failed')
      ) {
        return currentDetail;
      }
      try {
        const data = await getTask(taskId);
        if (selectedTaskIdRef.current === taskId) {
          applyTaskDetail(data);
        }
        setTasks((prev) => {
          const exists = prev.some((item) => item.id === data.id);
          if (exists) {
            return orderTasks(prev.map((item) => (item.id === data.id ? data : item)));
          }
          return orderTasks([...prev, data]);
        });
        return data;
      } catch (apiError) {
        setError(apiError instanceof Error ? apiError.message : 'Task not found');
        return null;
      }
    },
    [applyTaskDetail],
  );

  useEffect(() => {
    const state = location.state as LocationState | null;
    if (state?.focusTaskId) {
      const focusId = state.focusTaskId;
      updateSelectedTaskId(focusId);
      setTaskLookupId(String(focusId));
      setTaskLogs([]);
      logSkipRef.current = 0;
      setCopyState('idle');
      void refreshTaskDetail(focusId, true);
      navigate('.', { replace: true, state: {} });
    }
  }, [location.state, navigate, refreshTaskDetail, updateSelectedTaskId]);

  useEffect(() => {
    if (!selectedTaskId || !isDrawerOpen) {
      setIsStreaming(false);
      return;
    }

    let cancelled = false;
    const requestId = logStreamRequestRef.current + 1;
    logStreamRequestRef.current = requestId;
    let eventSource: EventSource | null = null;
    const currentTaskId = selectedTaskId;

    const openStream = async () => {
      try {
        const snapshot = await getTaskLogs(currentTaskId);
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        const snapshotEntries = snapshot.entries ?? [];
        setCopyState('idle');
        setTaskLogs(snapshotEntries);
        setLogSnapshotMeta({
          status: snapshot.status,
          branch: snapshot.branch ?? null,
          codex_model: snapshot.codex_model ?? null,
          codex_reasoning_effort: snapshot.codex_reasoning_effort ?? 'medium',
          abort_requested: snapshot.abort_requested,
        });
        logSkipRef.current = snapshotEntries.length;

        const shouldStream = ['pending', 'running'].includes(snapshot.status);
        if (!shouldStream) {
          setIsStreaming(false);
          return;
        }
      } catch {
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        setTaskLogs([]);
        setLogSnapshotMeta(null);
        logSkipRef.current = 0;
      }

      if (cancelled || logStreamRequestRef.current !== requestId) {
        return;
      }

      eventSource = new EventSource(`/tasks/${currentTaskId}/logs`);
      setIsStreaming(true);

      const closeStream = () => {
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
      };

      eventSource.onmessage = (event) => {
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        if (logSkipRef.current > 0) {
          logSkipRef.current -= 1;
          return;
        }
        const message = event.data as string;
        if (message) {
          setTaskLogs((prev) => [...prev, message]);
        }
      };

      eventSource.addEventListener('done', () => {
        void (async () => {
          if (cancelled || logStreamRequestRef.current !== requestId) {
            return;
          }
          setIsStreaming(false);
          logSkipRef.current = 0;
          await refreshTaskDetail(currentTaskId, true);
          await fetchTasks('refresh');
          closeStream();
        })();
      });

      eventSource.addEventListener('aborted', () => {
        void (async () => {
          if (cancelled || logStreamRequestRef.current !== requestId) {
            return;
          }
          setIsStreaming(false);
          logSkipRef.current = 0;
          setActionNotice('Task aborted');
          await refreshTaskDetail(currentTaskId, true);
          await fetchTasks('refresh');
          closeStream();
        })();
      });

      eventSource.addEventListener('deleted', () => {
        void (async () => {
          if (cancelled || logStreamRequestRef.current !== requestId) {
            return;
          }
          setIsStreaming(false);
          applyTaskDetail(null);
          setTaskLogs([]);
          setLogSnapshotMeta(null);
          setActionNotice(null);
          setIsDrawerOpen(false);
          updateSelectedTaskId(null);
          logSkipRef.current = 0;
          await fetchTasks('refresh');
          closeStream();
        })();
      });

      eventSource.onerror = () => {
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        setIsStreaming(false);
        closeStream();
      };
    };

    void openStream();

    return () => {
      cancelled = true;
      if (eventSource) {
        eventSource.close();
      }
      if (logStreamRequestRef.current === requestId) {
        setIsStreaming(false);
      }
    };
  }, [selectedTaskId, isDrawerOpen, refreshTaskDetail, fetchTasks, updateSelectedTaskId, applyTaskDetail]);

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
    if (!taskDetail) {
      return;
    }
    setLogSnapshotMeta({
      status: taskDetail.status,
      branch: taskDetail.branch ?? null,
      codex_model: taskDetail.codex_model ?? null,
      codex_reasoning_effort: taskDetail.codex_reasoning_effort ?? 'medium',
      abort_requested: taskDetail.abort_requested,
    });
  }, [taskDetail]);

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

  useFocusTrap(modalCardRef, Boolean(confirmAction), confirmButtonRef);

  const handleStatusToggle = (statusValue: TaskStatus) => {
    setFilterDraft((prev) => {
      const exists = prev.statuses.includes(statusValue);
      const nextStatuses = exists ? prev.statuses.filter((item) => item !== statusValue) : [...prev.statuses, statusValue];
      return { ...prev, statuses: nextStatuses };
    });
  };

  const handleModelFilterChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setFilterDraft((prev) => ({ ...prev, codexModel: event.target.value }));
  };

  const handleBranchFilterChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFilterDraft((prev) => ({ ...prev, branch: event.target.value }));
  };

  const handleFilterSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = normalizeFilters(filterDraft);
    setFilterDraft(normalized);
    setFilters(normalized);
    setPagesLoaded(1);
    void fetchTasks('filters', 1, normalized);
  };

  const handleFilterReset = () => {
    if (
      !filters.statuses.length &&
      !filters.codexModel &&
      !filters.branch &&
      !filterDraft.statuses.length &&
      !filterDraft.codexModel &&
      !filterDraft.branch
    ) {
      return;
    }
    const resetFilters: TaskFilters = { statuses: [], codexModel: '', branch: '' };
    setFilterDraft(resetFilters);
    setFilters(resetFilters);
    setPagesLoaded(1);
    void fetchTasks('filters', 1, resetFilters);
  };

  const handleLoadMore = () => {
    if (isLoadingMore || listMeta.nextOffset === null || pagesLoaded >= MAX_PAGES) {
      return;
    }
    const nextPageCount = pagesLoaded + 1;
    setPagesLoaded(nextPageCount);
    void fetchTasks('loadMore', nextPageCount);
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
    updateSelectedTaskId(id);
    setTaskLogs([]);
    logSkipRef.current = 0;
    setCopyState('idle');
    setIsDrawerOpen(true);
    setConfirmAction(null);
    setActionError(null);
    setActionNotice(null);
    void refreshTaskDetail(id, true);
  };

  const handleTaskSelect = (task: Task) => {
    updateSelectedTaskId(task.id);
    setTaskLookupId(String(task.id));
    applyTaskDetail(task);
    setLogSnapshotMeta({
      status: task.status,
      branch: task.branch ?? null,
      codex_model: task.codex_model ?? null,
      codex_reasoning_effort: task.codex_reasoning_effort ?? 'medium',
      abort_requested: task.abort_requested,
    });
    setTaskLogs([]);
    logSkipRef.current = 0;
    setCopyState('idle');
    setError(null);
    setIsDrawerOpen(true);
    setConfirmAction(null);
    setActionError(null);
    setActionNotice(null);
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
    } catch (apiError) {
      setCopyState('error');
      setError(apiError instanceof Error ? apiError.message : 'Failed to copy logs');
    }
    copyResetRef.current = window.setTimeout(() => {
      setCopyState('idle');
    }, 2000);
  };

  const selectedProject = taskDetail ? projectMap.get(taskDetail.project_id) ?? null : null;
  const canAbortTask = taskDetail ? ['pending', 'running'].includes(taskDetail.status) : false;
  const canDeleteTask = taskDetail ? ['done', 'failed', 'aborted'].includes(taskDetail.status) : false;
  const abortPending = taskDetail ? taskDetail.abort_requested && ['pending', 'running'].includes(taskDetail.status) : false;

  const handleDrawerClose = useCallback(() => {
    setIsDrawerOpen(false);
    setConfirmAction(null);
    setActionError(null);
    setActionNotice(null);
    setLogSnapshotMeta(null);
    logSkipRef.current = 0;
  }, []);

  useEffect(() => {
    if (!isDrawerOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handleDrawerClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isDrawerOpen, handleDrawerClose]);

  const handleAbortClick = () => {
    setConfirmAction('abort');
    setActionError(null);
  };

  const handleDeleteClick = () => {
    setConfirmAction('delete');
    setActionError(null);
  };

  const handleActionCancel = () => {
    setConfirmAction(null);
  };

  const handleActionConfirm = async () => {
    if (!taskDetail || !confirmAction) {
      return;
    }
    setIsActionLoading(true);
    setActionError(null);
    try {
      if (confirmAction === 'abort') {
        const updated = await abortTask(taskDetail.id);
        applyTaskDetail(updated);
        setActionNotice('Abort requested; waiting for runner to stop');
        await refreshTaskDetail(updated.id, true);
        await fetchTasks('refresh');
      } else {
        await deleteTask(taskDetail.id);
        setActionNotice('Task deleted');
        applyTaskDetail(null);
        setTaskLogs([]);
        setCopyState('idle');
        updateSelectedTaskId(null);
        setIsDrawerOpen(false);
        setLogSnapshotMeta(null);
        await fetchTasks('refresh');
      }
    } catch (apiError) {
      setActionError(apiError instanceof Error ? apiError.message : 'Action failed');
    } finally {
      setIsActionLoading(false);
      setConfirmAction(null);
    }
  };

  const filtersApplied = Boolean(filters.branch) || Boolean(filters.codexModel) || filters.statuses.length > 0;
  const filterDraftMatchesApplied =
    filterDraft.codexModel === filters.codexModel &&
    filterDraft.branch === filters.branch &&
    filterDraft.statuses.length === filters.statuses.length &&
    filters.statuses.every((value) => filterDraft.statuses.includes(value));

  const canLoadMore =
    listMeta.nextOffset !== null &&
    !isLoading &&
    !isLoadingMore &&
    pagesLoaded < MAX_PAGES &&
    tasks.length < listMeta.total;

  const reachedPageLimit = pagesLoaded >= MAX_PAGES && listMeta.nextOffset !== null;

  const combinedError = error || modelsError || projectsError;
  const skeletonRowCount = Math.min(5, PAGE_SIZE);
  const modalTitleId = confirmAction ? `task-confirm-${confirmAction}` : undefined;
  const modalDescriptionId = modalTitleId ? `${modalTitleId}-desc` : undefined;

  return (
    <div className="page">
      <header className="page-header">
        <h2>Tasks</h2>
        <p>Inspect task history, monitor logs, and launch quick follow-up jobs.</p>
      </header>

      {combinedError && <div className="error-banner" role="alert">{combinedError}</div>}

      <section className="panel">
        <h3>Filters</h3>
        <form className="task-filters" onSubmit={handleFilterSubmit} aria-label="Filter tasks">
          <fieldset className="filter-group">
            <legend>Status</legend>
            <div className="filter-options">
              {STATUS_OPTIONS.map((statusOption) => {
                const checked = filterDraft.statuses.includes(statusOption);
                return (
                  <label key={statusOption} className={`filter-chip${checked ? ' active' : ''}`}>
                    <input type="checkbox" checked={checked} onChange={() => handleStatusToggle(statusOption)} />
                    <span>{statusOption}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
          <div className="filter-field">
            <label htmlFor="task-filter-model">Model</label>
            <select
              id="task-filter-model"
              value={filterDraft.codexModel}
              onChange={handleModelFilterChange}
            >
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
              onChange={handleBranchFilterChange}
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
              onClick={handleFilterReset}
              disabled={!filtersApplied && filterDraftMatchesApplied}
            >
              Reset
            </button>
          </div>
        </form>
      </section>

      <section className="panel" aria-busy={isLoading ? 'true' : 'false'}>
        <div className="panel-header">
          <h3>Task History</h3>
          <div className="panel-meta">
            <span>{`Showing ${tasks.length} of ${listMeta.total} tasks`}</span>
            {filtersApplied && <span className="filter-indicator">Filters active</span>}
          </div>
        </div>
        <div className="table-wrapper">
          {isLoading ? (
            <table className="task-table task-table-skeleton" aria-hidden="true">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Project</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Finished</th>
                  <th>Codex</th>
                  <th>Model</th>
                  <th>Reasoning</th>
                  <th>Branch</th>
                  <th>Merge Request</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: skeletonRowCount }).map((_, rowIndex) => (
                  <tr key={`skeleton-${rowIndex}`}>
                    {Array.from({ length: 10 }).map((__, cellIndex) => (
                      <td key={cellIndex}>
                        <span
                          className="skeleton skeleton-text"
                          style={{ width: `${Math.max(32, 85 - cellIndex * 6)}%` }}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : tasks.length === 0 ? (
            <p className="empty">
              {filtersApplied ? 'No tasks match your filters.' : 'No tasks submitted yet.'}
            </p>
          ) : (
            <>
              <table className="task-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Project</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Finished</th>
                    <th>Codex</th>
                    <th>Model</th>
                    <th>Reasoning</th>
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
                        <td>
                          <span className={`status status-${task.status}`}>{task.status}</span>
                        </td>
                        <td>{formatTimestamp(task.created_at)}</td>
                        <td>{formatTimestamp(task.finished_at)}</td>
                        <td>{task.codex_invocation ?? '--'}</td>
                        <td>{task.codex_model ?? '--'}</td>
                        <td>{formatReasoningEffort(task.codex_reasoning_effort)}</td>
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
              <div className="table-footer">
                {canLoadMore && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleLoadMore}
                    disabled={isLoadingMore}
                  >
                    {isLoadingMore ? 'Loading…' : 'Load more'}
                  </button>
                )}
                {reachedPageLimit && (
                  <p className="table-hint">
                    Showing the latest {tasks.length} tasks (API window limit reached).
                  </p>
                )}
                {!canLoadMore && !reachedPageLimit && tasks.length < listMeta.total && (
                  <p className="table-hint">
                    Showing {tasks.length} of {listMeta.total} tasks.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </section>

      <section className="panel">
        <h3>Task Detail</h3>
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
          <div className="drawer-reminder">
            <p>
              Task <strong>#{taskDetail.id}</strong> is selected. Use the drawer to review details and logs.
            </p>
            {!isDrawerOpen && (
              <button type="button" className="ghost-button" onClick={() => setIsDrawerOpen(true)}>
                Open task drawer
              </button>
            )}
          </div>
        ) : (
          <p className="empty">Select or submit a task to inspect it in the detail drawer.</p>
        )}
      </section>

      {isDrawerOpen && (
        <div className="task-drawer">
          <div className="task-drawer-backdrop" aria-hidden="true" />
          <div className="task-drawer-panel">
            <button
              type="button"
              className="drawer-close"
              onClick={handleDrawerClose}
              aria-label="Close task drawer"
            >
              ×
            </button>
            {taskDetail ? (
              <>
                <header className="drawer-header">
                  <div className="drawer-header-main">
                    <p className="drawer-eyebrow">Task #{taskDetail.id}</p>
                    <div className="drawer-status-row">
                      <span className={`status status-${taskDetail.status}`}>{taskDetail.status}</span>
                      {abortPending && <span className="abort-pill">Abort requested</span>}
                    </div>
                    <p className="drawer-subtle">
                      Created {formatTimestamp(taskDetail.created_at)} • Project{' '}
                      {selectedProject ? selectedProject.name : taskDetail.project_id}
                    </p>
                  </div>
                  <div className="drawer-actions">
                    {canAbortTask && (
                      <button
                        type="button"
                        className="danger-button"
                        onClick={handleAbortClick}
                        disabled={isActionLoading || confirmAction !== null || taskDetail.abort_requested}
                      >
                        {abortPending ? 'Abort pending…' : 'Abort task'}
                      </button>
                    )}
                    {canDeleteTask && (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={handleDeleteClick}
                        disabled={isActionLoading || confirmAction !== null}
                      >
                        Delete task
                      </button>
                    )}
                  </div>
                </header>

                {actionNotice && <div className="notice notice-success">{actionNotice}</div>}
                {actionError && <div className="notice notice-warning">{actionError}</div>}

                <div className="drawer-meta-grid">
                  <dl>
                    <div>
                      <dt>Prompt</dt>
                      <dd>{taskDetail.prompt}</dd>
                    </div>
                    <div>
                      <dt>Allowlist</dt>
                      <dd>{taskDetail.allowlist.length ? taskDetail.allowlist.join(', ') : '--'}</dd>
                    </div>
                    <div>
                      <dt>Branch</dt>
                      <dd>{taskDetail.branch ?? '--'}</dd>
                    </div>
                    <div>
                      <dt>Codex Model</dt>
                      <dd>{taskDetail.codex_model ?? '--'}</dd>
                    </div>
                    <div>
                      <dt>Reasoning Effort</dt>
                      <dd>{formatReasoningEffort(taskDetail.codex_reasoning_effort)}</dd>
                    </div>
                  </dl>
                  <dl>
                    <div>
                      <dt>Started</dt>
                      <dd>{formatTimestamp(taskDetail.started_at)}</dd>
                    </div>
                    <div>
                      <dt>Finished</dt>
                      <dd>{formatTimestamp(taskDetail.finished_at)}</dd>
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
                      <dt>Invocation</dt>
                      <dd>{taskDetail.codex_invocation ?? '--'}</dd>
                    </div>
                  </dl>
                </div>

                <div className="logs drawer-logs">
                  <div className="logs-header">
                    <h4>Logs</h4>
                    <div className="logs-actions">
                      {isStreaming && <span className="live-indicator">Live</span>}
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={handleCopyLogs}
                        disabled={!taskLogs.length}
                      >
                        {copyState === 'success'
                          ? 'Copied!'
                          : copyState === 'error'
                            ? 'Copy failed'
                            : 'Copy logs'}
                      </button>
                      {copyState !== 'idle' && (
                        <span
                          className={`copy-feedback ${copyState === 'success' ? 'copy-feedback-success' : 'copy-feedback-error'}`}
                          role="status"
                          aria-live="polite"
                        >
                          {copyState === 'success'
                            ? 'Logs copied to clipboard'
                            : 'Failed to copy logs'}
                        </span>
                      )}
                    </div>
                  </div>
                  {logSnapshotMeta && (
                    <dl className="logs-metadata">
                      <div>
                        <dt>Status at capture</dt>
                        <dd>
                          <span className={`status status-${logSnapshotMeta.status}`}>
                            {logSnapshotMeta.status}
                          </span>
                        </dd>
                      </div>
                      <div>
                        <dt>Branch at capture</dt>
                        <dd>{logSnapshotMeta.branch ?? '--'}</dd>
                      </div>
                      <div>
                        <dt>Model at capture</dt>
                        <dd>{logSnapshotMeta.codex_model ?? 'Default'}</dd>
                      </div>
                      <div>
                        <dt>Reasoning effort</dt>
                        <dd>{formatReasoningEffort(logSnapshotMeta.codex_reasoning_effort)}</dd>
                      </div>
                      <div>
                        <dt>Abort requested</dt>
                        <dd>{logSnapshotMeta.abort_requested ? 'Yes' : 'No'}</dd>
                      </div>
                    </dl>
                  )}
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
              </>
            ) : (
              <p className="empty">No task selected.</p>
            )}

            {confirmAction && (
              <div className="drawer-modal" role="presentation">
                <div
                  className="drawer-modal-card"
                  role="alertdialog"
                  aria-modal="true"
                  aria-labelledby={modalTitleId}
                  aria-describedby={modalDescriptionId}
                  ref={modalCardRef}
                >
                  <h4 id={modalTitleId}>{confirmAction === 'abort' ? 'Abort task?' : 'Delete task?'}</h4>
                  <p id={modalDescriptionId}>
                    {confirmAction === 'abort'
                      ? 'The runner will stop before launching or finish its current step. This cannot be undone.'
                      : 'This removes the task record, logs, and sanitized workspace. This action cannot be undone.'}
                  </p>
                  <div className="drawer-modal-actions">
                    <button
                      type="button"
                      className="danger-button"
                      onClick={handleActionConfirm}
                      disabled={isActionLoading}
                      ref={confirmButtonRef}
                    >
                      {isActionLoading
                        ? 'Working…'
                        : confirmAction === 'abort'
                          ? 'Confirm abort'
                          : 'Confirm delete'}
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={handleActionCancel}
                      disabled={isActionLoading}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default TaskListPage;
