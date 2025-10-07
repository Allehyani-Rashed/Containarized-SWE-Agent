import { TaskLogsSnapshot, TaskStatus } from '../../types';

export type TaskFilters = {
  statuses: TaskStatus[];
  codexModel: string;
  branch: string;
};

export const initialTaskFilters: TaskFilters = {
  statuses: [],
  codexModel: '',
  branch: '',
};

export type TaskListMeta = {
  total: number;
  nextOffset: number | null;
  limit: number;
};

export type CopyState = 'idle' | 'success' | 'error';

export type TaskLogMetadata = Pick<
  TaskLogsSnapshot,
  | 'status'
  | 'branch'
  | 'target_branch'
  | 'change_mode'
  | 'commit_sha'
  | 'commit_url'
  | 'codex_model'
  | 'codex_reasoning_effort'
  | 'abort_requested'
  | 'credentials'
>;

export type CredentialFetchError = string | null;
