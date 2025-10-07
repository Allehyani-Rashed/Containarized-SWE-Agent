import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { NavigateFunction } from 'react-router-dom';
import { abortTask, deleteTask, getTask, listTasks, TaskListParams } from '../../api/tasks';
import { listCodexModels } from '../../api/models';
import { CodexModel, Task, TaskCredentialStatus, TaskStatus } from '../../types';
import { TASK_LIST_MAX_PAGES, TASK_LIST_PAGE_SIZE, TASKS_POLL_INTERVAL_MS } from './constants';
import { TaskFilters, TaskListMeta, initialTaskFilters } from './types';
import {
  areFiltersEqual,
  hasActiveFilters,
  normalizeTaskFilters,
} from './taskSelectors';

const sortTasksDesc = (items: Task[]) =>
  [...items].sort((a, b) => {
    const aTime = Date.parse(a.created_at) || 0;
    const bTime = Date.parse(b.created_at) || 0;
    return bTime - aTime;
  });

export type FetchContext = 'initial' | 'filters' | 'loadMore' | 'refresh';

export type UseTaskListResult = {
  tasks: Task[];
  listMeta: TaskListMeta;
  isLoading: boolean;
  isLoadingMore: boolean;
  filters: TaskFilters;
  filterDraft: TaskFilters;
  filtersApplied: boolean;
  filterDraftMatchesApplied: boolean;
  models: CodexModel[];
  modelsError: string | null;
  error: string | null;
  selectedTaskId: number | null;
  taskDetail: Task | null;
  taskLookupId: string;
  isDrawerOpen: boolean;
  confirmAction: 'abort' | 'delete' | null;
  confirmQuickAbort: number | null;
  quickActionLoading: number | null;
  isActionLoading: boolean;
  actionError: string | null;
  actionNotice: string | null;
  canLoadMore: boolean;
  reachedPageLimit: boolean;
  toggleStatusFilter: (status: TaskStatus) => void;
  updateModelDraft: (event: ChangeEvent<HTMLSelectElement>) => void;
  updateBranchDraft: (event: ChangeEvent<HTMLInputElement>) => void;
  submitFilters: (event?: FormEvent<HTMLFormElement>) => void;
  resetFilters: () => void;
  loadMore: () => void;
  setTaskLookupId: (value: string) => void;
  lookupTask: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  openDrawer: () => void;
  closeDrawer: () => void;
  selectTask: (task: Task) => void;
  requestAbortTask: () => void;
  requestDeleteTask: () => void;
  cancelConfirmation: () => void;
  executeConfirmation: () => Promise<void>;
  requestQuickAbort: (taskId: number) => void;
  clearQuickAbort: () => void;
  performQuickAbort: (taskId: number) => Promise<void>;
  refreshTaskDetail: (taskId: number, force?: boolean) => Promise<Task | null>;
  fetchTasks: (context?: FetchContext, overridePages?: number, overrideFilters?: TaskFilters) => Promise<void>;
  updateSelectedTaskId: (taskId: number | null) => void;
  applyTaskDetail: (detail: Task | null) => void;
  updateTaskCredentials: (taskId: number, credentials: TaskCredentialStatus) => void;
  clearTaskDetail: () => void;
  navigateToSubmit: (task: Task, mode: 'retry' | 'clone') => void;
  setActionNoticeMessage: (message: string | null) => void;
  setErrorMessage: (message: string | null) => void;
};

export type UseTaskListOptions = {
  navigate?: NavigateFunction;
};

export function useTaskList({ navigate }: UseTaskListOptions = {}): UseTaskListResult {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskDetail, setTaskDetail] = useState<Task | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [taskLookupId, setTaskLookupId] = useState('');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [filters, setFilters] = useState<TaskFilters>(initialTaskFilters);
  const [filterDraft, setFilterDraft] = useState<TaskFilters>(initialTaskFilters);
  const [pagesLoaded, setPagesLoaded] = useState(1);
  const [listMeta, setListMeta] = useState<TaskListMeta>({ total: 0, nextOffset: null, limit: TASK_LIST_PAGE_SIZE });
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [models, setModels] = useState<CodexModel[]>([]);
  const [confirmAction, setConfirmAction] = useState<'abort' | 'delete' | null>(null);
  const [confirmQuickAbort, setConfirmQuickAbort] = useState<number | null>(null);
  const [quickActionLoading, setQuickActionLoading] = useState<number | null>(null);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const selectedTaskIdRef = useRef<number | null>(null);
  const taskDetailRef = useRef<Task | null>(null);

  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const updateSelectedTaskId = useCallback((nextId: number | null) => {
    selectedTaskIdRef.current = nextId;
    setSelectedTaskId(nextId);
  }, []);

  const applyTaskDetail = useCallback((detail: Task | null) => {
    taskDetailRef.current = detail;
    setTaskDetail(detail);
  }, []);

  const fetchTasks = useCallback(
    async (
      context: FetchContext = 'refresh',
      overridePages?: number,
      overrideFilters?: TaskFilters,
    ) => {
      const activeFilters = overrideFilters ?? filters;
      const effectivePages = overridePages ?? pagesLoaded;
      const limit = Math.min(TASK_LIST_PAGE_SIZE * effectivePages, TASK_LIST_MAX_PAGES * TASK_LIST_PAGE_SIZE);
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

      const showSpinner = context === 'initial' || context === 'filters';
      if (showSpinner) {
        setIsLoading(true);
      }
      if (context === 'loadMore') {
        setIsLoadingMore(true);
      }

      try {
        const response = await listTasks(params);
        setTasks(sortTasksDesc(response.items));
        setListMeta({ total: response.total, nextOffset: response.next_offset, limit: response.limit });
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
    [filters, pagesLoaded],
  );

  const refreshTaskDetail = useCallback(
    async (taskId: number, force?: boolean) => {
      const currentDetail = taskDetailRef.current;
      if (
        !force &&
        currentDetail &&
        currentDetail.id === taskId &&
        (currentDetail.status === 'done' || currentDetail.status === 'failed' || currentDetail.status === 'aborted')
      ) {
        return currentDetail;
      }
      try {
        const detail = await getTask(taskId);
        if (selectedTaskIdRef.current === taskId) {
          applyTaskDetail(detail);
        }
        setTasks((prev) => {
          const exists = prev.some((task) => task.id === detail.id);
          if (exists) {
            return sortTasksDesc(prev.map((task) => (task.id === detail.id ? detail : task)));
          }
          return sortTasksDesc([...prev, detail]);
        });
        return detail;
      } catch (apiError) {
        setError(apiError instanceof Error ? apiError.message : 'Task not found');
        return null;
      }
    },
    [applyTaskDetail],
  );

  useEffect(() => {
    void fetchTasks('initial');
    const interval = window.setInterval(() => {
      void fetchTasks('refresh');
    }, TASKS_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
    };
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

  const filtersApplied = useMemo(() => hasActiveFilters(filters), [filters]);
  const filterDraftMatchesApplied = useMemo(() => areFiltersEqual(filterDraft, filters), [filterDraft, filters]);

  const canLoadMore = useMemo(() => {
    return (
      listMeta.nextOffset !== null &&
      !isLoading &&
      !isLoadingMore &&
      pagesLoaded < TASK_LIST_MAX_PAGES &&
      tasks.length < listMeta.total
    );
  }, [listMeta.nextOffset, isLoading, isLoadingMore, pagesLoaded, tasks.length, listMeta.total]);

  const reachedPageLimit = useMemo(() => {
    return pagesLoaded >= TASK_LIST_MAX_PAGES && listMeta.nextOffset !== null;
  }, [pagesLoaded, listMeta.nextOffset]);

  const toggleStatusFilter = useCallback((status: TaskStatus) => {
    setFilterDraft((prev) => {
      const exists = prev.statuses.includes(status);
      const nextStatuses = exists ? prev.statuses.filter((value) => value !== status) : [...prev.statuses, status];
      return { ...prev, statuses: nextStatuses };
    });
  }, []);

  const updateModelDraft = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    setFilterDraft((prev) => ({ ...prev, codexModel: value }));
  }, []);

  const updateBranchDraft = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setFilterDraft((prev) => ({ ...prev, branch: value }));
  }, []);

  const submitFilters = useCallback(
    (event?: FormEvent<HTMLFormElement>) => {
      if (event) {
        event.preventDefault();
      }
      const normalized = normalizeTaskFilters(filterDraft);
      setFilterDraft(normalized);
      setFilters(normalized);
      setPagesLoaded(1);
      void fetchTasks('filters', 1, normalized);
    },
    [filterDraft, fetchTasks],
  );

  const resetFilters = useCallback(() => {
    const noActiveFilters =
      !filters.statuses.length && !filters.codexModel && !filters.branch &&
      !filterDraft.statuses.length &&
      !filterDraft.codexModel &&
      !filterDraft.branch;
    if (noActiveFilters) {
      return;
    }
    setFilters(initialTaskFilters);
    setFilterDraft(initialTaskFilters);
    setPagesLoaded(1);
    void fetchTasks('filters', 1, initialTaskFilters);
  }, [filterDraft, filters, fetchTasks]);

  const loadMore = useCallback(() => {
    if (!canLoadMore) {
      return;
    }
    const nextPages = pagesLoaded + 1;
    setPagesLoaded(nextPages);
    void fetchTasks('loadMore', nextPages);
  }, [canLoadMore, pagesLoaded, fetchTasks]);

  const openDrawer = useCallback(() => {
    setIsDrawerOpen(true);
    setActionError(null);
    setActionNotice(null);
  }, []);

  const closeDrawer = useCallback(() => {
    setIsDrawerOpen(false);
    setConfirmAction(null);
    setActionError(null);
    setActionNotice(null);
  }, []);

  const selectTask = useCallback(
    (task: Task) => {
      updateSelectedTaskId(task.id);
      applyTaskDetail(task);
      openDrawer();
      void refreshTaskDetail(task.id, true);
    },
    [updateSelectedTaskId, applyTaskDetail, openDrawer, refreshTaskDetail],
  );

  const lookupTask = useCallback(
    async (event?: FormEvent<HTMLFormElement>) => {
      if (event) {
        event.preventDefault();
      }
      const numericId = Number(taskLookupId);
      if (!numericId || Number.isNaN(numericId)) {
        return;
      }
      const detail = await refreshTaskDetail(numericId, true);
      if (detail) {
        updateSelectedTaskId(detail.id);
        applyTaskDetail(detail);
        openDrawer();
      }
    },
    [taskLookupId, refreshTaskDetail, updateSelectedTaskId, applyTaskDetail, openDrawer],
  );

  const requestAbortTask = useCallback(() => {
    setConfirmAction('abort');
    setActionError(null);
  }, []);

  const requestDeleteTask = useCallback(() => {
    setConfirmAction('delete');
    setActionError(null);
  }, []);

  const cancelConfirmation = useCallback(() => {
    setConfirmAction(null);
  }, []);

  const executeConfirmation = useCallback(async () => {
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
        updateSelectedTaskId(null);
        setIsDrawerOpen(false);
        await fetchTasks('refresh');
      }
    } catch (apiError) {
      setActionError(apiError instanceof Error ? apiError.message : 'Action failed');
    } finally {
      setIsActionLoading(false);
      setConfirmAction(null);
    }
  }, [taskDetail, confirmAction, applyTaskDetail, refreshTaskDetail, fetchTasks, updateSelectedTaskId]);

  const requestQuickAbort = useCallback((taskId: number) => {
    setConfirmQuickAbort(taskId);
  }, []);

  const clearQuickAbort = useCallback(() => {
    setConfirmQuickAbort(null);
  }, []);

  const performQuickAbort = useCallback(
    async (taskId: number) => {
      setQuickActionLoading(taskId);
      try {
        await abortTask(taskId);
        await fetchTasks('refresh');
        setConfirmQuickAbort(null);
      } catch (apiError) {
        setError(apiError instanceof Error ? apiError.message : 'Failed to abort task');
      } finally {
        setQuickActionLoading(null);
      }
    },
    [fetchTasks],
  );

  const updateTaskCredentials = useCallback(
    (taskId: number, credentials: TaskCredentialStatus) => {
      setTasks((prev) => {
        let updated = false;
        const next = prev.map((task) => {
          if (task.id !== taskId) {
            return task;
          }
          const existing = task.credentials;
          if (
            existing.gitlab_pat_available === credentials.gitlab_pat_available &&
            existing.gitlab_pat_last_updated === credentials.gitlab_pat_last_updated &&
            existing.chatgpt_session_available === credentials.chatgpt_session_available &&
            existing.chatgpt_session_last_updated === credentials.chatgpt_session_last_updated
          ) {
            return task;
          }
          updated = true;
          return { ...task, credentials };
        });
        return updated ? next : prev;
      });

      const currentDetail = taskDetailRef.current;
      if (currentDetail && currentDetail.id === taskId) {
        const creds = currentDetail.credentials;
        if (
          creds.gitlab_pat_available !== credentials.gitlab_pat_available ||
          creds.gitlab_pat_last_updated !== credentials.gitlab_pat_last_updated ||
          creds.chatgpt_session_available !== credentials.chatgpt_session_available ||
          creds.chatgpt_session_last_updated !== credentials.chatgpt_session_last_updated
        ) {
          applyTaskDetail({ ...currentDetail, credentials });
        }
      }
    },
    [applyTaskDetail],
  );

  const clearTaskDetail = useCallback(() => {
    applyTaskDetail(null);
    updateSelectedTaskId(null);
  }, [applyTaskDetail, updateSelectedTaskId]);

  const navigateToSubmit = useCallback(
    (task: Task, _mode: 'retry' | 'clone') => {
      const navigator = navigateRef.current;
      if (!navigator) {
        return;
      }
      const submitState = {
        projectId: task.project_id,
        prompt: task.prompt,
        targetBranch: task.target_branch || '',
        branchName: task.branch || '',
        codexModel: task.codex_model || '',
        codexReasoningEffort: task.codex_reasoning_effort || 'medium',
        mrTitle: task.mr_title || '',
      };
      navigator('/', { state: submitState });
    },
    [],
  );

  return {
    tasks,
    listMeta,
    isLoading,
    isLoadingMore,
    filters,
    filterDraft,
    filtersApplied,
    filterDraftMatchesApplied,
    models,
    modelsError,
    error,
    selectedTaskId,
    taskDetail,
    taskLookupId,
    isDrawerOpen,
    confirmAction,
    confirmQuickAbort,
    quickActionLoading,
    isActionLoading,
    actionError,
    actionNotice,
    canLoadMore,
    reachedPageLimit,
    toggleStatusFilter,
    updateModelDraft,
    updateBranchDraft,
    submitFilters,
    resetFilters,
    loadMore,
    setTaskLookupId,
    lookupTask,
    openDrawer,
    closeDrawer,
    selectTask,
    requestAbortTask,
    requestDeleteTask,
    cancelConfirmation,
    executeConfirmation,
    requestQuickAbort,
    clearQuickAbort,
    performQuickAbort,
    refreshTaskDetail,
    fetchTasks,
    updateSelectedTaskId,
    applyTaskDetail,
    updateTaskCredentials,
    clearTaskDetail,
    navigateToSubmit,
    setActionNoticeMessage: setActionNotice,
    setErrorMessage: setError,
  };
}
