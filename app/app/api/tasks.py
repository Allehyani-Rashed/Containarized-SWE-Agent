from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlmodel import Session, select

from ..codex_models import default_reasoning_effort
from ..database import get_session
from ..dependencies import get_worker, get_worker_optional
from ..integrations import get_gitlab_pat_status
from ..models import Project, Task, TaskChangeMode, TaskStatus
from ..schemas import (
    TaskAbortRequest,
    TaskCreate,
    TaskCredentialStatus,
    TaskDeleteRequest,
    TaskListResponse,
    TaskLogSnapshot,
    TaskRead,
)
from ..services.audit import normalize_actor, normalize_reason, record_audit_event
from ..services.tasks import task_to_read
from ..services.validators import (
    normalize_branch_name,
    normalize_change_mode,
    normalize_codex_model,
    normalize_codex_reasoning_effort,
    normalize_mr_title,
)
from ..services.workspaces import remove_workspace
from ..worker import TaskQueueManager

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    worker: TaskQueueManager = Depends(get_worker),
) -> TaskRead:
    project = session.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    pat_status = get_gitlab_pat_status(session)
    if not pat_status.configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitLab PAT not configured; rotate a token via /integrations/pat",
        )

    branch_override = normalize_branch_name(payload.branch_name) if payload.branch_name else None
    target_branch_override = normalize_branch_name(payload.target_branch) if payload.target_branch else None
    codex_model = normalize_codex_model(payload.codex_model)
    reasoning_effort = normalize_codex_reasoning_effort(payload.codex_reasoning_effort)
    mr_title = normalize_mr_title(payload.mr_title)
    change_mode = normalize_change_mode(payload.change_mode)

    target_branch = target_branch_override or project.default_branch
    if not target_branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project default branch missing; set one before submitting tasks",
        )

    task = Task(
        project_id=payload.project_id,
        prompt=payload.prompt,
        status=TaskStatus.pending,
        branch=branch_override,
        target_branch=target_branch,
        mr_title=mr_title,
        change_mode=change_mode,
        codex_model=codex_model,
        codex_reasoning_effort=reasoning_effort,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    worker.register_task(task.id)
    worker.enqueue(task.id)
    return task_to_read(task, worker)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    session: Session = Depends(get_session),
    statuses: str | None = Query(default=None, description="Comma-separated list of task statuses to include"),
    codex_model: str | None = Query(default=None, description="Filter by Codex model identifier"),
    branch: str | None = Query(default=None, description="Case-insensitive substring match on branch name"),
    project_id: int | None = Query(default=None, ge=1, description="Filter by project ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of tasks to return"),
    offset: int = Query(default=0, ge=0, description="Number of matching tasks to skip"),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> TaskListResponse:
    filters = []

    if project_id is not None:
        filters.append(Task.project_id == project_id)

    if statuses:
        candidates = [value.strip() for value in statuses.split(",") if value.strip()]
        status_filters: set[TaskStatus] = set()
        invalid: list[str] = []
        for candidate in candidates:
            try:
                status_filters.add(TaskStatus(candidate))
            except ValueError:
                invalid.append(candidate)
        if invalid:
            formatted = ", ".join(sorted(dict.fromkeys(invalid)))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid task status value(s): {formatted}",
            )
        if status_filters:
            filters.append(Task.status.in_(list(status_filters)))

    if codex_model is not None:
        normalized_model = normalize_codex_model(codex_model)
        filters.append(Task.codex_model == normalized_model)

    if branch:
        branch_query = branch.strip().lower()
        if branch_query:
            filters.append(Task.branch.is_not(None))
            filters.append(func.lower(Task.branch).like(f"%{branch_query}%"))

    base_query = select(Task)
    if filters:
        for clause in filters:
            base_query = base_query.where(clause)

    total_query = select(func.count()).select_from(base_query.subquery())
    total = session.exec(total_query).one()

    rows = session.exec(
        base_query.order_by(Task.created_at.desc(), Task.id.desc()).offset(offset).limit(limit)
    ).all()

    items = [task_to_read(row, worker) for row in rows]
    next_offset = offset + limit if offset + limit < total else None

    return TaskListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
    )


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> TaskRead:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task_to_read(task, worker)


@router.post("/{task_id}/abort", response_model=TaskRead)
def abort_task(
    task_id: int,
    payload: TaskAbortRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager = Depends(get_worker),
) -> TaskRead:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status in {TaskStatus.done, TaskStatus.failed, TaskStatus.aborted}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task already completed")

    actor = normalize_actor(payload.actor if payload else None)
    reason = normalize_reason(payload.reason if payload else None)
    timestamp = datetime.now(timezone.utc)

    message_bits: list[str] = ["Abort requested by operator"]
    if actor:
        message_bits.append(f"({actor})")
    if reason:
        message_bits.append(f"- {reason}")
    log_message = " ".join(message_bits)

    details_parts = [f"task_id={task_id}"]
    if reason:
        details_parts.append(f"reason={reason}")
    audit_details = ", ".join(details_parts)

    if task.status == TaskStatus.pending:
        task.abort_requested = True
        task.status = TaskStatus.aborted
        task.finished_at = timestamp
        session.add(task)
        record_audit_event(session, "task.abort.pending", actor, audit_details)
        session.commit()
        worker.record_task_log(task_id, log_message)
        worker.mark_task_aborted(task_id)
        session.refresh(task)
        return task_to_read(task, worker)

    task.abort_requested = True
    session.add(task)
    record_audit_event(session, "task.abort.requested", actor, audit_details)
    session.commit()
    worker.record_task_log(task_id, log_message)
    worker.request_abort(task_id)
    session.refresh(task)
    return task_to_read(task, worker)


@router.get("/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    follow: int = 1,
    session: Session = Depends(get_session),
    worker: TaskQueueManager = Depends(get_worker),
):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if not follow:
        entries = worker.get_logs_snapshot(task_id)
        credentials = TaskCredentialStatus.model_validate(worker.get_task_credentials(task_id))
        return TaskLogSnapshot(
            task_id=task_id,
            entries=entries,
            status=task.status,
            branch=task.branch,
            target_branch=task.target_branch,
            change_mode=task.change_mode or TaskChangeMode.merge_request,
            commit_sha=task.commit_sha,
            commit_url=task.commit_url,
            codex_model=task.codex_model,
            codex_reasoning_effort=task.codex_reasoning_effort or default_reasoning_effort(),
            abort_requested=bool(task.abort_requested),
            credentials=credentials,
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        async for entry in worker.stream_logs(task_id):
            if isinstance(entry, dict):
                event_name = entry.get("event", "message")
                payload = entry.get("payload", {})
                if "timestamp" in entry and isinstance(payload, dict):
                    payload = dict(payload)
                    payload.setdefault("timestamp", entry["timestamp"])
                data = json.dumps(payload, default=str)
                yield f"event: {event_name}\ndata: {data}\n\n"
            else:
                yield f"data: {entry}\n\n"
        terminal_event = worker.get_terminal_event(task_id) or "done"
        if terminal_event == "aborted":
            yield "event: aborted\ndata: aborted\n\n"
        elif terminal_event == "deleted":
            yield "event: deleted\ndata: deleted\n\n"
        else:
            yield "event: done\ndata: complete\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    payload: TaskDeleteRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager = Depends(get_worker),
) -> Response:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task.status in {TaskStatus.pending, TaskStatus.running}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task must complete before it can be deleted",
        )

    actor = normalize_actor(payload.actor if payload else None)
    audit_details = f"task_id={task_id}"

    workspace_path = task.workspace_path

    record_audit_event(session, "task.deleted", actor, audit_details)
    session.delete(task)
    session.commit()

    worker.handle_task_deleted(task_id)
    remove_workspace(workspace_path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
