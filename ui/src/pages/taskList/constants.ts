import { TaskStatus } from '../../types';

export const TASK_LIST_PAGE_SIZE = 25;
export const TASK_LIST_API_WINDOW = 200;
export const TASK_LIST_MAX_PAGES = Math.floor(TASK_LIST_API_WINDOW / TASK_LIST_PAGE_SIZE);

export const TASK_STATUS_OPTIONS: TaskStatus[] = ['pending', 'running', 'done', 'failed', 'aborted'];

export const LOGS_POLL_INTERVAL_MS = 1000;
export const TASKS_POLL_INTERVAL_MS = 5000;
export const PAT_POLL_INTERVAL_MS = 15000; // documented for banner hooks, kept here for context.
