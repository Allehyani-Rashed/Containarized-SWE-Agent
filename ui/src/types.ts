export type CacheStatus = 'missing' | 'present' | 'ready' | string;

export type TaskChangeMode = 'merge_request' | 'branch_commit';

export type Project = {
  id: number;
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  created_at: string;
  repository_url: string | null;
  last_task_at: string | null;
  last_task_status: TaskStatus | null;
  allowlist_status: ProjectAllowlistStatus;
  allowlist: string[];
  active_task_count: number;
  total_task_count: number;
  cache_path: string;
  cache_status: CacheStatus;
  cache_quota_mb: number | null;
  cache_prune_after_hours: number | null;
  last_cache_commit: string | null;
  last_active_count: number | null;
};

export type ProjectAllowlistStatus = 'unknown' | 'empty' | 'custom';

export type ProjectTaskSummary = {
  id: number;
  status: TaskStatus;
  prompt: string;
  branch: string | null;
  target_branch: string | null;
  mr_title: string | null;
  change_mode: TaskChangeMode;
  commit_sha: string | null;
  commit_url: string | null;
  codex_model: string | null;
  codex_reasoning_effort: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
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
  active_credential: 'session' | 'none';
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
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  branch: string | null;
  target_branch: string | null;
  mr_title: string | null;
  mr_url: string | null;
  change_mode: TaskChangeMode;
  commit_sha: string | null;
  commit_url: string | null;
  workspace_path: string | null;
  codex_agent_version: string | null;
  codex_invocation: string | null;
  codex_model: string | null;
  codex_reasoning_effort: string | null;
  abort_requested: boolean;
  cache_commit: string | null;
  credentials: TaskCredentialStatus;
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
  target_branch: string | null;
  change_mode: TaskChangeMode;
  commit_sha: string | null;
  commit_url: string | null;
  codex_model: string | null;
  codex_reasoning_effort: string | null;
  abort_requested: boolean;
  credentials: TaskCredentialStatus;
};

export type ProjectCreatePayload = {
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  cache_quota_mb?: number | null;
  cache_prune_after_hours?: number | null;
  allowlist: string[];
};

export type ProjectUpdatePayload = Partial<{
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  cache_quota_mb: number | null;
  cache_prune_after_hours: number | null;
  actor: string | null;
  allowlist: string[];
}>;

export type ProjectDeletePayload = {
  actor?: string | null;
};

export type TaskCreatePayload = {
  project_id: number;
  prompt: string;
  branch_name?: string;
  target_branch?: string;
  codex_model?: string;
  codex_reasoning_effort?: string;
  mr_title?: string;
  change_mode?: TaskChangeMode;
};

export type PatStorePayload = {
  token: string;
  updated_by?: string | null;
};

export type PatClearPayload = {
  updated_by?: string;
};

export type SessionPayload = {
  bundle: string;
  updated_by?: string | null;
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

export type ProjectBranch = {
  name: string;
  default: boolean;
};

export type ProjectBranchList = {
  items: ProjectBranch[];
  next_page: number | null;
};

export type ConcurrencySettings = {
  project_limit: number;
  effective_project_limit: number;
  worker_pool_size: number;
  parallel_enabled: boolean;
  updated_at: string | null;
  updated_by: string | null;
};

export type ConcurrencySettingsUpdatePayload = {
  project_limit: number;
};

export type TaskCredentialStatus = {
  gitlab_pat_available: boolean;
  gitlab_pat_last_updated: string | null;
  chatgpt_session_available: boolean;
  chatgpt_session_last_updated: string | null;
};
