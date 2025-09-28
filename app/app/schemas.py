from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, SQLModel

from .models import TaskStatus


class ProjectBase(SQLModel):
    name: str
    local_path: str
    default_branch: str
    gitlab_host: str
    gitlab_project_path: str


class ProjectCreate(ProjectBase):
    codex_token: Optional[str] = None


class ProjectRead(ProjectBase):
    id: int
    created_at: datetime
    codex_token_configured: bool
    codex_token_updated_at: Optional[datetime]
    repository_url: Optional[str] = None
    last_task_at: Optional[datetime] = None
    last_task_status: Optional[TaskStatus] = None
    allowlist_status: str = "unknown"
    active_task_count: int = 0
    total_task_count: int = 0


class ProjectUpdate(SQLModel):
    name: Optional[str] = None
    local_path: Optional[str] = None
    default_branch: Optional[str] = None
    gitlab_host: Optional[str] = None
    gitlab_project_path: Optional[str] = None
    codex_token: Optional[str | None] = Field(default=None)
    clear_codex_token: Optional[bool] = Field(default=None)
    actor: Optional[str] = None


class ProjectDeleteRequest(SQLModel):
    actor: Optional[str] = None


class ProjectTaskSummary(SQLModel):
    id: int
    status: TaskStatus
    prompt: str
    branch: Optional[str]
    codex_model: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    allowlist_size: int


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
    allowlist: List[str] = Field(default_factory=list)
    branch_name: Optional[str] = None
    codex_model: Optional[str] = None


class TaskRead(SQLModel):
    id: int
    project_id: int
    prompt: str
    status: TaskStatus
    allowlist: List[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    branch: Optional[str]
    mr_url: Optional[str]
    workspace_path: Optional[str]
    codex_agent_version: Optional[str]
    codex_invocation: Optional[str]
    codex_model: Optional[str]
    abort_requested: bool


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
    codex_model: Optional[str]
    abort_requested: bool


class CodexModelSummary(SQLModel):
    id: str
    label: str
    description: Optional[str] = None
    is_default: bool = False
