export type CacheStatus = 'missing' | 'present' | 'ready' | string;

export type Project = {
  id: number;
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  created_at: string;
  codex_token_configured: boolean;
  codex_token_updated_at: string | null;
  repository_url: string | null;
  last_task_at: string | null;
  last_task_status: TaskStatus | null;
  allowlist_status: ProjectAllowlistStatus;
  active_task_count: number;
  total_task_count: number;
  cache_path: string;
  cache_status: CacheStatus;
  cache_quota_mb: number | null;
  cache_prune_after_hours: number | null;
  last_cache_commit: string | null;
};

export type ProjectAllowlistStatus = 'unknown' | 'empty' | 'custom';

export type ProjectTaskSummary = {
  id: number;
  status: TaskStatus;
  prompt: string;
  branch: string | null;
  codex_model: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  allowlist_size: number;
  cache_commit: string | null;
};

export type ProjectDetail = Project & {
  recent_tasks: ProjectTaskSummary[];
};

export type PatStatus = {
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

export type TaskStatus = 'pending' | 'running' | 'done' | 'failed' | 'aborted';

export type Task = {
  id: number;
  project_id: number;
  prompt: string;
  status: TaskStatus;
  allowlist: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  branch: string | null;
  mr_url: string | null;
  workspace_path: string | null;
  codex_agent_version: string | null;
  codex_invocation: string | null;
  codex_model: string | null;
  abort_requested: boolean;
  cache_commit: string | null;
};

export type TaskListResponse = {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
};

export type TaskLogsSnapshot = {
  task_id: number;
  entries: string[];
  status: TaskStatus;
  branch: string | null;
  codex_model: string | null;
  abort_requested: boolean;
};

export type ProjectCreatePayload = {
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  codex_token: string | null;
  cache_quota_mb?: number | null;
  cache_prune_after_hours?: number | null;
};

export type ProjectUpdatePayload = Partial<{
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  codex_token: string | null;
  clear_codex_token: boolean;
  cache_quota_mb: number | null;
  cache_prune_after_hours: number | null;
  actor: string | null;
}>;

export type ProjectDeletePayload = {
  actor?: string | null;
};

export type TaskCreatePayload = {
  project_id: number;
  prompt: string;
  allowlist: string[];
  branch_name?: string;
  codex_model?: string;
};

export type PatStorePayload = {
  token: string;
  updated_by: string | null;
};

export type PatClearPayload = {
  updated_by?: string;
};

export type SessionPayload = {
  bundle: string;
  updated_by: string | null;
};

export type SessionClearPayload = {
  updated_by?: string;
};

export type PatVerifyPayload = {
  gitlab_host?: string;
};

export type CodexModel = {
  id: string;
  label: string;
  description?: string | null;
  is_default: boolean;
};
