import { useCallback, useEffect, useRef, useState } from 'react';
import { getTaskLogs } from '../../api/tasks';
import { Task, TaskCredentialStatus } from '../../types';
import { LOGS_POLL_INTERVAL_MS } from './constants';
import { CopyState, TaskLogMetadata, TaskFilters } from './types';
import type { FetchContext } from './useTaskList';

export type UseTaskLogsOptions = {
  taskId: number | null;
  taskDetail: Task | null;
  isDrawerOpen: boolean;
  refreshTaskDetail: (taskId: number, force?: boolean) => Promise<Task | null>;
  fetchTasks: (context?: FetchContext, overridePages?: number, overrideFilters?: TaskFilters) => Promise<void>;
  updateTaskCredentials: (taskId: number, credentials: TaskCredentialStatus) => void;
  clearTaskDetail: () => void;
  closeDrawer: () => void;
  setActionNotice: (message: string | null) => void;
  setErrorMessage: (message: string | null) => void;
};

export type UseTaskLogsResult = {
  logs: string[];
  metadata: TaskLogMetadata | null;
  isStreaming: boolean;
  copyState: CopyState;
  copyLogs: () => Promise<void>;
  resetCopyFeedback: () => void;
};

export function useTaskLogs(options: UseTaskLogsOptions): UseTaskLogsResult {
  const {
    taskId,
    taskDetail,
    isDrawerOpen,
    refreshTaskDetail,
    fetchTasks,
    updateTaskCredentials,
    clearTaskDetail,
    closeDrawer,
    setActionNotice,
    setErrorMessage,
  } = options;

  const [logs, setLogs] = useState<string[]>([]);
  const [metadata, setMetadata] = useState<TaskLogMetadata | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [copyState, setCopyState] = useState<CopyState>('idle');

  const logStreamRequestRef = useRef(0);
  const logSkipRef = useRef(0);
  const copyResetRef = useRef<number | null>(null);

  useEffect(() => {
    if (!taskDetail) {
      return;
    }
    setMetadata({
      status: taskDetail.status,
      branch: taskDetail.branch ?? null,
      target_branch: taskDetail.target_branch ?? null,
      change_mode: taskDetail.change_mode ?? null,
      commit_sha: taskDetail.commit_sha ?? null,
      commit_url: taskDetail.commit_url ?? null,
      codex_model: taskDetail.codex_model ?? null,
      codex_reasoning_effort: taskDetail.codex_reasoning_effort ?? 'medium',
      abort_requested: taskDetail.abort_requested,
      credentials: taskDetail.credentials,
    });
  }, [taskDetail]);

  useEffect(() => {
    return () => {
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
    };
  }, []);

  const resetCopyFeedback = useCallback(() => {
    if (copyResetRef.current !== null) {
      window.clearTimeout(copyResetRef.current);
      copyResetRef.current = null;
    }
    setCopyState('idle');
  }, []);

  const copyLogs = useCallback(async () => {
    if (!logs.length) {
      return;
    }
    if (copyResetRef.current !== null) {
      window.clearTimeout(copyResetRef.current);
    }
    try {
      if (!navigator.clipboard) {
        throw new Error('Clipboard API unavailable');
      }
      await navigator.clipboard.writeText(logs.join('\n'));
      setCopyState('success');
      setErrorMessage(null);
      copyResetRef.current = window.setTimeout(() => {
        setCopyState('idle');
        copyResetRef.current = null;
      }, 2000);
    } catch (copyError) {
      setCopyState('error');
      const message = copyError instanceof Error ? copyError.message : 'Failed to copy logs';
      setErrorMessage(message);
      copyResetRef.current = window.setTimeout(() => {
        setCopyState('idle');
        copyResetRef.current = null;
      }, 2000);
    }
  }, [logs, setErrorMessage]);

  useEffect(() => {
    if (!taskId || !isDrawerOpen) {
      setIsStreaming(false);
      return;
    }

    let cancelled = false;
    const requestId = logStreamRequestRef.current + 1;
    logStreamRequestRef.current = requestId;
    let eventSource: EventSource | null = null;
    let credentialHandler: ((event: Event) => void) | null = null;

    const openStream = async () => {
      try {
        const snapshot = await getTaskLogs(taskId);
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        const snapshotEntries = snapshot.entries ?? [];
        setLogs(snapshotEntries);
        setCopyState('idle');
        setMetadata({
          status: snapshot.status,
          branch: snapshot.branch ?? null,
          target_branch: snapshot.target_branch ?? null,
          change_mode: snapshot.change_mode ?? null,
          commit_sha: snapshot.commit_sha ?? null,
          commit_url: snapshot.commit_url ?? null,
          codex_model: snapshot.codex_model ?? null,
          codex_reasoning_effort: snapshot.codex_reasoning_effort ?? 'medium',
          abort_requested: snapshot.abort_requested,
          credentials: snapshot.credentials,
        });
        logSkipRef.current = snapshotEntries.length;

        const shouldStream = snapshot.status === 'pending' || snapshot.status === 'running';
        if (!shouldStream) {
          setIsStreaming(false);
          return;
        }
      } catch {
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        setLogs([]);
        setMetadata(null);
        logSkipRef.current = 0;
      }

      if (cancelled || logStreamRequestRef.current !== requestId) {
        return;
      }

      eventSource = new EventSource(`/tasks/${taskId}/logs`);
      setIsStreaming(true);

      credentialHandler = (rawEvent: Event) => {
        if (cancelled || logStreamRequestRef.current !== requestId) {
          return;
        }
        const messageEvent = rawEvent as MessageEvent<string>;
        if (!messageEvent.data) {
          return;
        }
        try {
          const parsed = JSON.parse(messageEvent.data) as {
            task_id?: number;
            gitlab_pat_available?: boolean;
            gitlab_pat_last_updated?: string | null;
            chatgpt_session_available?: boolean;
            chatgpt_session_last_updated?: string | null;
          };
          const taskIdFromEvent = parsed.task_id;
          if (typeof taskIdFromEvent !== 'number') {
            return;
          }
          const updatedCredentials: TaskCredentialStatus = {
            gitlab_pat_available: Boolean(parsed.gitlab_pat_available),
            gitlab_pat_last_updated:
              typeof parsed.gitlab_pat_last_updated === 'string'
                ? parsed.gitlab_pat_last_updated
                : null,
            chatgpt_session_available: Boolean(parsed.chatgpt_session_available),
            chatgpt_session_last_updated:
              typeof parsed.chatgpt_session_last_updated === 'string'
                ? parsed.chatgpt_session_last_updated
                : null,
          };
          updateTaskCredentials(taskIdFromEvent, updatedCredentials);
          if (taskIdFromEvent === taskId) {
            setMetadata((prev) => (prev ? { ...prev, credentials: updatedCredentials } : prev));
          }
        } catch {
          // ignore malformed credential payloads
        }
      };

      eventSource.addEventListener('credential-event', credentialHandler);

      const closeStream = () => {
        if (eventSource) {
          if (credentialHandler) {
            eventSource.removeEventListener('credential-event', credentialHandler);
          }
          eventSource.close();
          eventSource = null;
          credentialHandler = null;
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
          setLogs((prev) => [...prev, message]);
        }
      };

      eventSource.addEventListener('done', () => {
        void (async () => {
          if (cancelled || logStreamRequestRef.current !== requestId) {
            return;
          }
          setIsStreaming(false);
          logSkipRef.current = 0;
          await refreshTaskDetail(taskId, true);
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
          await refreshTaskDetail(taskId, true);
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
          setLogs([]);
          setMetadata(null);
          setCopyState('idle');
          setActionNotice(null);
          clearTaskDetail();
          closeDrawer();
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
        if (credentialHandler) {
          eventSource.removeEventListener('credential-event', credentialHandler);
        }
        eventSource.close();
      }
      credentialHandler = null;
      if (logStreamRequestRef.current === requestId) {
        setIsStreaming(false);
      }
    };
  }, [
    taskId,
    isDrawerOpen,
    refreshTaskDetail,
    fetchTasks,
    updateTaskCredentials,
    clearTaskDetail,
    closeDrawer,
    setActionNotice,
  ]);

  useEffect(() => {
    if (!taskId || !isDrawerOpen) {
      return;
    }
    const interval = window.setInterval(() => {
      void refreshTaskDetail(taskId);
    }, LOGS_POLL_INTERVAL_MS);

    void refreshTaskDetail(taskId);

    return () => {
      window.clearInterval(interval);
    };
  }, [taskId, isDrawerOpen, refreshTaskDetail]);

  return {
    logs,
    metadata,
    isStreaming,
    copyState,
    copyLogs,
    resetCopyFeedback,
  };
}
