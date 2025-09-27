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


class TaskLogSnapshot(SQLModel):
    task_id: int
    entries: List[str]
