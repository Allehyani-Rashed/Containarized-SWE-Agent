from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Sequence

from sqlalchemy import func
from sqlmodel import Session, select

from ..models import Project, Task, TaskStatus
from ..project_cache import project_cache_repo_path
from ..schemas import ProjectRead


def build_repository_url(project: Project) -> str:
    host = (project.gitlab_host or "").rstrip("/")
    path = (project.gitlab_project_path or "").lstrip("/")
    if not host:
        return path
    if not path:
        return host
    return f"{host}/{path}"


def ensure_unique_project(
    session: Session,
    *,
    gitlab_host: str,
    gitlab_project_path: str,
    exclude_id: int | None = None,
) -> None:
    query = select(Project).where(
        Project.gitlab_host == gitlab_host,
        Project.gitlab_project_path == gitlab_project_path,
    )
    if exclude_id is not None:
        query = query.where(Project.id != exclude_id)
    existing = session.exec(query).first()
    if existing is not None:
        repository = f"{gitlab_host}/{gitlab_project_path}" if gitlab_host else gitlab_project_path
        from fastapi import HTTPException, status  # localized import to avoid circular dependencies

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project already registered for {repository}",
        )


def derive_last_activity(task: Task | None) -> datetime | None:
    if task is None:
        return None
    for candidate in (task.finished_at, task.started_at, task.created_at):
        if candidate is not None:
            return candidate
    return None


def derive_allowlist_status(project: Project) -> str:
    entries = project.allowlist or []
    if entries:
        return "custom"
    return "empty"


def collect_project_metrics(session: Session, projects: Sequence[Project]) -> Dict[int, Dict[str, Any]]:
    metrics: Dict[int, Dict[str, Any]] = {}
    project_ids = [project.id for project in projects if project.id is not None]
    for project in projects:
        if project.id is None:
            continue
        metrics[project.id] = {
            "last_task_at": None,
            "last_task_status": None,
            "allowlist_status": derive_allowlist_status(project),
            "active_task_count": 0,
            "total_task_count": 0,
            "last_cache_commit": None,
        }

    if not project_ids:
        return metrics

    total_counts = session.exec(
        select(Task.project_id, func.count(Task.id))
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    ).all()
    for project_id, count in total_counts:
        data = metrics.get(project_id)
        if data is not None:
            data["total_task_count"] = int(count or 0)

    active_counts = session.exec(
        select(Task.project_id, func.count(Task.id))
        .where(Task.project_id.in_(project_ids), Task.status.in_([TaskStatus.pending, TaskStatus.running]))
        .group_by(Task.project_id)
    ).all()
    for project_id, count in active_counts:
        data = metrics.get(project_id)
        if data is not None:
            data["active_task_count"] = int(count or 0)

    recent_tasks = session.exec(
        select(Task)
        .where(Task.project_id.in_(project_ids))
        .order_by(Task.project_id, Task.created_at.desc(), Task.id.desc())
    ).all()

    seen: set[int] = set()
    for task in recent_tasks:
        project_id = task.project_id
        if project_id in seen:
            continue
        seen.add(project_id)
        data = metrics.get(project_id)
        if data is None:
            continue
        data["last_task_at"] = derive_last_activity(task)
        data["last_task_status"] = task.status
        data["last_cache_commit"] = task.cache_commit
        if len(seen) == len(project_ids):
            break

    return metrics


def project_to_read(project: Project, extras: Dict[str, Any] | None = None) -> ProjectRead:
    cache_path = str(project_cache_repo_path(project.gitlab_host, project.gitlab_project_path))
    repo_exists = Path(cache_path).exists()
    cache_git_dir = Path(cache_path) / ".git"
    cache_status = "ready" if cache_git_dir.exists() else ("present" if repo_exists else "missing")
    update_payload: Dict[str, Any] = {
        "repository_url": build_repository_url(project),
        "cache_path": cache_path,
        "cache_status": cache_status,
        "cache_quota_mb": project.cache_quota_mb,
        "cache_prune_after_hours": project.cache_prune_after_hours,
        "last_cache_commit": None,
        "last_active_count": project.last_active_count,
    }
    if extras:
        update_payload.update(extras)
    return ProjectRead.model_validate(
        project,
        from_attributes=True,
        update=update_payload,
    )


__all__ = [
    "build_repository_url",
    "collect_project_metrics",
    "derive_allowlist_status",
    "derive_last_activity",
    "ensure_unique_project",
    "project_to_read",
]
