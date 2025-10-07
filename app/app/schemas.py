from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, SQLModel

from .models import TaskChangeMode, TaskStatus


class ProjectBase(SQLModel):
    name: str
    default_branch: str
    gitlab_host: str
    gitlab_project_path: str


class ProjectCreate(ProjectBase):
    cache_quota_mb: Optional[int] = None
    cache_prune_after_hours: Optional[int] = None
    allowlist: List[str] = Field(default_factory=list)


class ProjectRead(ProjectBase):
    id: int
    created_at: datetime
    repository_url: Optional[str] = None
    last_task_at: Optional[datetime] = None
    last_task_status: Optional[TaskStatus] = None
    allowlist_status: str = "unknown"
    allowlist: List[str] = Field(default_factory=list)
    active_task_count: int = 0
    total_task_count: int = 0
    cache_path: str
    cache_status: str = "unknown"
    cache_quota_mb: Optional[int] = None
    cache_prune_after_hours: Optional[int] = None
    last_cache_commit: Optional[str] = None
    last_active_count: Optional[int] = None


class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    default_branch: Optional[str] = None
    gitlab_host: Optional[str] = None
    gitlab_project_path: Optional[str] = None
    actor: Optional[str] = None
    cache_quota_mb: Optional[int] = None
    cache_prune_after_hours: Optional[int] = None
    allowlist: Optional[List[str]] = None


class ConcurrencySettings(SQLModel):
    project_limit: int
    effective_project_limit: int
    worker_pool_size: int
    parallel_enabled: bool
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class ConcurrencySettingsUpdate(SQLModel):
    project_limit: int
    actor: Optional[str] = None


class ProjectDeleteRequest(SQLModel):
    actor: Optional[str] = None


class ProjectTaskSummary(SQLModel):
    id: int
    status: TaskStatus
    prompt: str
    branch: Optional[str]
    target_branch: Optional[str] = None
    mr_title: Optional[str] = None
    change_mode: TaskChangeMode = TaskChangeMode.merge_request
    commit_sha: Optional[str] = None
    commit_url: Optional[str] = None
    codex_model: Optional[str]
    codex_reasoning_effort: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    cache_commit: Optional[str] = None


class ProjectDetail(ProjectRead):
    recent_tasks: List[ProjectTaskSummary] = Field(default_factory=list)


class GitLabPATStatus(SQLModel):
    configured: bool
    updated_at: Optional[datetime]
    updated_by: Optional[str]
    session_configured: bool = False
    session_updated_at: Optional[datetime] = None
    session_updated_by: Optional[str] = None
    active_credential: str = "none"
    verification_status: Optional[str] = None
    verification_checked_at: Optional[datetime] = None
    verification_error: Optional[str] = None
    verification_host: Optional[str] = None


class GitLabPATRotateRequest(SQLModel):
    token: str
    updated_by: Optional[str] = None


class GitLabPATClearRequest(SQLModel):
    updated_by: Optional[str] = None


class GitLabPATVerifyRequest(SQLModel):
    gitlab_host: Optional[str] = None
    actor: Optional[str] = None


class ChatGPTSessionImportRequest(SQLModel):
    bundle: str
    updated_by: Optional[str] = None


class ChatGPTSessionClearRequest(SQLModel):
    updated_by: Optional[str] = None


class TaskCreate(SQLModel):
    project_id: int
    prompt: str
    branch_name: Optional[str] = None
    target_branch: Optional[str] = None
    codex_model: Optional[str] = None
    codex_reasoning_effort: Optional[str] = None
    mr_title: Optional[str] = None
    change_mode: Optional[TaskChangeMode] = None


class TaskRead(SQLModel):
    id: int
    project_id: int
    prompt: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    branch: Optional[str]
    target_branch: Optional[str]
    mr_title: Optional[str]
    mr_url: Optional[str]
    change_mode: TaskChangeMode = TaskChangeMode.merge_request
    commit_sha: Optional[str] = None
    commit_url: Optional[str] = None
    workspace_path: Optional[str]
    codex_agent_version: Optional[str]
    codex_invocation: Optional[str]
    codex_model: Optional[str]
    codex_reasoning_effort: Optional[str]
    abort_requested: bool
    cache_commit: Optional[str]
    credentials: "TaskCredentialStatus" = Field(default_factory=lambda: TaskCredentialStatus())


class TaskListResponse(SQLModel):
    items: List[TaskRead] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    next_offset: Optional[int] = None


class TaskAbortRequest(SQLModel):
    actor: Optional[str] = None
    reason: Optional[str] = None


class TaskDeleteRequest(SQLModel):
    actor: Optional[str] = None


class TaskLogSnapshot(SQLModel):
    task_id: int
    entries: List[str]
    status: TaskStatus
    branch: Optional[str]
    target_branch: Optional[str]
    change_mode: TaskChangeMode = TaskChangeMode.merge_request
    commit_sha: Optional[str] = None
    commit_url: Optional[str] = None
    codex_model: Optional[str]
    codex_reasoning_effort: Optional[str]
    abort_requested: bool
    credentials: "TaskCredentialStatus" = Field(default_factory=lambda: TaskCredentialStatus())


class CodexModelSummary(SQLModel):
    id: str
    label: str
    description: Optional[str] = None
    is_default: bool = False


class GitLabBranchSummary(SQLModel):
    name: str
    default: bool = False


class GitLabBranchList(SQLModel):
    items: List[GitLabBranchSummary] = Field(default_factory=list)
    next_page: Optional[int] = None


class TaskCredentialStatus(SQLModel):
    gitlab_pat_available: bool = False
    gitlab_pat_last_updated: Optional[datetime] = None
    chatgpt_session_available: bool = False
    chatgpt_session_last_updated: Optional[datetime] = None
