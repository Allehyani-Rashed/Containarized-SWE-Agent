from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from ..allowlist import normalize_user_allowlist
from ..database import get_session
from ..dependencies import get_worker
from ..models import Project, Task, TaskChangeMode, TaskStatus
from ..schemas import (
    GitLabBranchList,
    GitLabBranchSummary,
    ProjectCreate,
    ProjectDeleteRequest,
    ProjectDetail,
    ProjectRead,
    ProjectTaskSummary,
    ProjectUpdate,
)
from ..services.audit import normalize_actor, record_audit_event
from ..services.gitlab import build_gitlab_branches_url, clean_gitlab_error, resolve_project_gitlab_token
from ..services.projects import collect_project_metrics, ensure_unique_project, project_to_read
from ..services.validators import (
    normalize_branch_name,
    normalize_codex_model,
    normalize_gitlab_host,
    normalize_gitlab_project_path,
    normalize_non_empty,
)
from ..services.workspaces import remove_workspace
from ..worker import TaskQueueManager
from ..codex_models import default_reasoning_effort

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)) -> ProjectRead:
    data = payload.model_dump()
    allowlist_entries = data.pop("allowlist", [])

    name = normalize_non_empty(data.get("name"), field="Project name")
    default_branch = normalize_branch_name(data.get("default_branch") or "")
    gitlab_host = normalize_gitlab_host(data.get("gitlab_host"))
    gitlab_project_path = normalize_gitlab_project_path(data.get("gitlab_project_path"))

    for numeric_field in ("cache_quota_mb", "cache_prune_after_hours"):
        value = data.get(numeric_field)
        if value is None:
            continue
        if value < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{numeric_field.replace('_', ' ')} must be non-negative",
            )

    ensure_unique_project(
        session,
        gitlab_host=gitlab_host,
        gitlab_project_path=gitlab_project_path,
    )

    project = Project(
        name=name,
        default_branch=default_branch,
        gitlab_host=gitlab_host,
        gitlab_project_path=gitlab_project_path,
        cache_quota_mb=data.get("cache_quota_mb"),
        cache_prune_after_hours=data.get("cache_prune_after_hours"),
        allowlist=normalize_user_allowlist(allowlist_entries or []),
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_to_read(project)


@router.get("", response_model=List[ProjectRead])
def list_projects(session: Session = Depends(get_session)) -> List[ProjectRead]:
    projects = session.exec(select(Project).order_by(Project.id)).all()
    metrics = collect_project_metrics(session, projects)
    return [
        project_to_read(project, metrics.get(project.id) if project.id is not None else None)
        for project in projects
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project_detail(project_id: int, session: Session = Depends(get_session)) -> ProjectDetail:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    metrics = collect_project_metrics(session, [project])
    extras = metrics.get(project_id, {})

    recent_rows = session.exec(
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.created_at.desc())
        .limit(10)
    ).all()

    recent_tasks = [
        ProjectTaskSummary(
            id=task.id,
            status=task.status,
            prompt=task.prompt,
            branch=task.branch,
            target_branch=task.target_branch,
            mr_title=task.mr_title,
            change_mode=task.change_mode or TaskChangeMode.merge_request,
            commit_sha=task.commit_sha,
            commit_url=task.commit_url,
            codex_model=task.codex_model or normalize_codex_model(None),
            codex_reasoning_effort=(task.codex_reasoning_effort or default_reasoning_effort()),
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
            cache_commit=task.cache_commit,
        )
        for task in recent_rows
    ]

    summary = project_to_read(project, extras)
    payload = summary.model_dump()
    payload["recent_tasks"] = recent_tasks
    return ProjectDetail(**payload)


@router.get("/{project_id}/branches", response_model=GitLabBranchList)
def list_project_branches(
    project_id: int,
    session: Session = Depends(get_session),
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> GitLabBranchList:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    token = resolve_project_gitlab_token(session, project)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Configure a GitLab PAT to list branches",
        )

    url = build_gitlab_branches_url(project, page=page, per_page=per_page, search=search)
    request = Request(url, method="GET")
    request.add_header("PRIVATE-TOKEN", token)
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "codex-local-agent/branch-list")

    try:
        with urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            if not (200 <= status_code < 300):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=clean_gitlab_error(f"GitLab responded with status {status_code}"),
                )

            payload = response.read()
            try:
                data = json.loads(payload)
            except JSONDecodeError as exc:  # noqa: BLE001 - normalize upstream error
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="GitLab returned an unexpected response",
                ) from exc

            if not isinstance(data, list):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="GitLab returned an unexpected response",
                )

            branches: List[GitLabBranchSummary] = []
            for entry in data:
                name = entry.get("name") if isinstance(entry, dict) else None
                if not name:
                    continue
                branches.append(GitLabBranchSummary(name=name, default=bool(entry.get("default", False))))

            next_page_header = response.headers.get("X-Next-Page") if response.headers else None
            next_page = None
            if next_page_header:
                trimmed = str(next_page_header).strip()
                if trimmed:
                    try:
                        next_page = int(trimmed)
                    except ValueError:
                        next_page = None

            return GitLabBranchList(items=branches, next_page=next_page)
    except HTTPException:
        raise
    except HTTPError as exc:  # pragma: no cover - exercised via URLError in tests
        detail = clean_gitlab_error(f"GitLab responded with status {exc.code}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        detail = clean_gitlab_error(f"Unable to reach GitLab: {reason}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001 - surface unexpected runtime issues
        detail = clean_gitlab_error(f"Unexpected error: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    payload_data = payload.model_dump(exclude_unset=True)
    actor = normalize_actor(payload_data.pop("actor", None))

    updated_fields: list[str] = []
    numeric_fields = {"cache_quota_mb", "cache_prune_after_hours"}

    if "name" in payload_data:
        name = normalize_non_empty(payload_data["name"], field="Project name")
        if project.name != name:
            project.name = name
            updated_fields.append("name")

    if "default_branch" in payload_data:
        default_branch = normalize_branch_name(payload_data["default_branch"] or "")
        if project.default_branch != default_branch:
            project.default_branch = default_branch
            updated_fields.append("default_branch")

    if "gitlab_host" in payload_data:
        gitlab_host = normalize_gitlab_host(payload_data["gitlab_host"])
        if project.gitlab_host != gitlab_host:
            project.gitlab_host = gitlab_host
            updated_fields.append("gitlab_host")

    if "gitlab_project_path" in payload_data:
        gitlab_project_path = normalize_gitlab_project_path(payload_data["gitlab_project_path"])
        if project.gitlab_project_path != gitlab_project_path:
            project.gitlab_project_path = gitlab_project_path
            updated_fields.append("gitlab_project_path")

    for field in numeric_fields:
        if field not in payload_data:
            continue
        value = payload_data[field]
        if value is not None and value < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field.replace('_', ' ')} must be non-negative",
            )
        if getattr(project, field) != value:
            setattr(project, field, value)
            updated_fields.append(field)

    if "allowlist" in payload_data:
        allowlist_entries = payload_data["allowlist"] or []
        normalized_entries = normalize_user_allowlist(allowlist_entries)
        if project.allowlist != normalized_entries:
            project.allowlist = normalized_entries
            updated_fields.append("allowlist")

    session.add(project)

    details_bits = [f"project_id={project_id}"]
    if updated_fields:
        details_bits.append(f"fields={','.join(updated_fields)}")
    audit_details = ", ".join(details_bits)
    if updated_fields:
        record_audit_event(session, "project.updated", actor, audit_details)

    ensure_unique_project(
        session,
        gitlab_host=project.gitlab_host,
        gitlab_project_path=project.gitlab_project_path,
        exclude_id=project.id,
    )

    session.commit()
    session.refresh(project)

    metrics = collect_project_metrics(session, [project])
    return project_to_read(project, metrics.get(project_id))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    payload: ProjectDeleteRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager = Depends(get_worker),
) -> Response:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    active_count = session.exec(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.status.in_([TaskStatus.pending, TaskStatus.running]),
        )
    ).one()
    if active_count and int(active_count) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has running or pending tasks; abort them before deletion",
        )

    actor = normalize_actor(payload.actor if payload else None)
    audit_details = f"project_id={project_id}"

    tasks = session.exec(select(Task).where(Task.project_id == project_id)).all()
    task_ids = [task.id for task in tasks if task.id is not None]
    workspaces = [task.workspace_path for task in tasks]

    for task in tasks:
        session.delete(task)

    session.delete(project)
    record_audit_event(session, "project.deleted", actor, audit_details)
    session.commit()

    for task_id in task_ids:
        worker.handle_task_deleted(task_id)
    for path in workspaces:
        remove_workspace(path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
