from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.dialects.sqlite import JSON
from sqlmodel import Field, SQLModel


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class AgentType(str, Enum):
    codex = "codex"
    claude_code = "claude-code"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    local_path: str
    default_branch: str
    gitlab_host: str
    gitlab_project_path: str
    gitlab_token: Optional[str] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, nullable=False)
    codex_token_encrypted: Optional[str] = Field(default=None, nullable=True)
    codex_token_updated_at: Optional[datetime] = Field(default=None, nullable=True)


class IntegrationCredential(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True, unique=True)
    token_encrypted: Optional[str] = Field(default=None, nullable=True)
    updated_at: Optional[datetime] = Field(default=None, nullable=True)
    updated_by: Optional[str] = Field(default=None, nullable=True)
    verification_status: Optional[str] = Field(default=None, nullable=True)
    verification_checked_at: Optional[datetime] = Field(default=None, nullable=True)
    verification_error: Optional[str] = Field(default=None, nullable=True)
    verification_host: Optional[str] = Field(default=None, nullable=True)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utc_now, nullable=False)
    actor: Optional[str] = Field(default=None, nullable=True)
    action: str
    details: Optional[str] = Field(default=None, nullable=True)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", nullable=False, index=True)
    prompt: str
    status: TaskStatus = Field(default=TaskStatus.pending, nullable=False)
    agent_type: AgentType = Field(default=AgentType.codex, nullable=False)
    model: Optional[str] = Field(default=None, nullable=True)
    allowlist: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, default=list),
    )
    created_at: datetime = Field(default_factory=_utc_now, nullable=False)
    started_at: Optional[datetime] = Field(default=None, nullable=True)
    finished_at: Optional[datetime] = Field(default=None, nullable=True)
    branch: Optional[str] = Field(default=None, nullable=True)
    mr_url: Optional[str] = Field(default=None, nullable=True)
    workspace_path: Optional[str] = Field(default=None, nullable=True)
    codex_agent_version: Optional[str] = Field(default=None, nullable=True)
    codex_invocation: Optional[str] = Field(default=None, nullable=True)
