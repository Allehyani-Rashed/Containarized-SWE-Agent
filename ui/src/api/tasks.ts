import { Task, TaskCreatePayload, TaskListResponse, TaskLogsSnapshot, TaskStatus } from '../types';
import { request } from './client';

export type TaskListParams = {
  statuses?: TaskStatus[];
  codexModel?: string;
  branch?: string;
  projectId?: number;
  limit?: number;
  offset?: number;
};

export function listTasks(params: TaskListParams = {}): Promise<TaskListResponse> {
  const search = new URLSearchParams();

  if (params.statuses && params.statuses.length) {
    search.set('statuses', params.statuses.join(','));
  }
  if (params.codexModel) {
    search.set('codex_model', params.codexModel);
  }
  if (params.branch) {
    search.set('branch', params.branch);
  }
  if (typeof params.projectId === 'number') {
    search.set('project_id', String(params.projectId));
  }
  if (typeof params.limit === 'number') {
    search.set('limit', String(params.limit));
  }
  if (typeof params.offset === 'number' && params.offset > 0) {
    search.set('offset', String(params.offset));
  }

  const query = search.toString();
  const suffix = query ? `?${query}` : '';
  return request<TaskListResponse>(`/tasks${suffix}`);
}

export function createTask(payload: TaskCreatePayload): Promise<Task> {
  return request<Task>('/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getTask(taskId: number): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`);
}

export function getTaskLogs(taskId: number): Promise<TaskLogsSnapshot> {
  const params = new URLSearchParams({ follow: '0' });
  return request<TaskLogsSnapshot>(`/tasks/${taskId}/logs?${params.toString()}`);
}

export function abortTask(
  taskId: number,
  payload?: { actor?: string | null; reason?: string | null },
): Promise<Task> {
  const body = payload ? JSON.stringify(payload) : JSON.stringify({});
  return request<Task>(`/tasks/${taskId}/abort`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
}

export function deleteTask(
  taskId: number,
  payload?: { actor?: string | null },
): Promise<void> {
  const init: { method: string; headers?: Record<string, string>; body?: string } = {
    method: 'DELETE',
  };
  if (payload) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(payload);
  }
  return request<void>(`/tasks/${taskId}`, init);
}
