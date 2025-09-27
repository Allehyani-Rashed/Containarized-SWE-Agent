from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from .allowlist import normalize_user_allowlist
from .database import engine, get_session, init_db
from .models import Project, Task, TaskStatus
from .integrations import (
    ChatGPTSessionError,
    GitLabPATVerificationError,
    clear_chatgpt_session_bundle,
    clear_gitlab_pat_token,
    get_gitlab_pat_status,
    set_chatgpt_session_bundle,
    set_gitlab_pat_token,
    verify_gitlab_pat,
)
from .schemas import (
    ChatGPTSessionClearRequest,
    ChatGPTSessionImportRequest,
    GitLabPATClearRequest,
    GitLabPATRotateRequest,
    GitLabPATStatus,
    GitLabPATVerifyRequest,
    ProjectCreate,
    ProjectRead,
    TaskCreate,
    TaskLogSnapshot,
    TaskRead,
)
from .secrets import get_secret_manager
from .worker import TaskQueueManager

_worker: TaskQueueManager | None = None


def get_worker() -> TaskQueueManager:
    if _worker is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Worker not ready")
    return _worker


def get_worker_optional() -> TaskQueueManager | None:
    return _worker


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _worker
    init_db()
    worker = TaskQueueManager(engine)
    _worker = worker
    try:
        yield
    finally:
        worker.shutdown()
        _worker = None


app = FastAPI(title="Containerized Codex Agent", lifespan=lifespan)


integrations_router = APIRouter(prefix="/integrations", tags=["integrations"])


@integrations_router.get("/pat", response_model=GitLabPATStatus)
def read_gitlab_pat_status(session: Session = Depends(get_session)) -> GitLabPATStatus:
    return get_gitlab_pat_status(session)


@integrations_router.post("/pat", response_model=GitLabPATStatus)
def rotate_gitlab_pat(
    payload: GitLabPATRotateRequest,
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token is required")

    with session.begin():
        credential = set_gitlab_pat_token(session, token, payload.updated_by)

    if worker is not None:
        worker.notify_gitlab_pat_stored(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


@integrations_router.delete("/pat", response_model=GitLabPATStatus)
def clear_gitlab_pat(
    payload: GitLabPATClearRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    actor = payload.updated_by if payload else None

    with session.begin():
        credential = clear_gitlab_pat_token(session, actor)

    if worker is not None:
        worker.notify_gitlab_pat_cleared(credential.updated_by, credential.updated_at)
        worker.fail_pending_tasks_due_to_missing_pat(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


@integrations_router.post("/pat/verify", response_model=GitLabPATStatus)
def verify_gitlab_pat_route(
    payload: GitLabPATVerifyRequest | None = Body(default=None),
    session: Session = Depends(get_session),
) -> GitLabPATStatus:
    actor = payload.actor if payload else None
    requested_host = payload.gitlab_host if payload else None
    try:
        return verify_gitlab_pat(session, actor, requested_host)
    except GitLabPATVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@integrations_router.post("/pat/session", response_model=GitLabPATStatus)
def import_chatgpt_session(
    payload: ChatGPTSessionImportRequest,
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    bundle = (payload.bundle or "").strip()
    if not bundle:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session bundle is required")

    try:
        with session.begin():
            credential = set_chatgpt_session_bundle(session, bundle, payload.updated_by)
    except ChatGPTSessionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if worker is not None:
        worker.notify_chatgpt_session_rotated(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


@integrations_router.delete("/pat/session", response_model=GitLabPATStatus)
def clear_chatgpt_session(
    payload: ChatGPTSessionClearRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    actor = payload.updated_by if payload else None

    with session.begin():
        credential = clear_chatgpt_session_bundle(session, actor)

    if worker is not None:
        worker.notify_chatgpt_session_cleared(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


app.include_router(integrations_router)



def _project_to_read(project: Project) -> ProjectRead:
    return ProjectRead.model_validate(
        project,
        from_attributes=True,
        update={
            "codex_token_configured": bool(project.codex_token_encrypted),
            "codex_token_updated_at": project.codex_token_updated_at,
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    data = payload.model_dump()
    raw_codex_token = (data.pop("codex_token", None) or "").strip()
    project = Project(**data)
    if raw_codex_token:
        manager = get_secret_manager()
        project.codex_token_encrypted = manager.encrypt(raw_codex_token)
        project.codex_token_updated_at = datetime.now(timezone.utc)
    session.add(project)
    session.commit()
    session.refresh(project)
    return _project_to_read(project)


@app.get("/projects", response_model=List[ProjectRead])
def list_projects(session: Session = Depends(get_session)) -> List[ProjectRead]:
    projects = session.exec(select(Project).order_by(Project.id)).all()
    return [_project_to_read(project) for project in projects]


@app.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    worker: TaskQueueManager = Depends(get_worker),
) -> Task:
    project = session.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    pat_status = get_gitlab_pat_status(session)
    if not pat_status.configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitLab PAT not configured; rotate a token via /integrations/pat",
        )

    normalized_allowlist = normalize_user_allowlist(payload.allowlist or [])

    task = Task(
        project_id=payload.project_id,
        prompt=payload.prompt,
        allowlist=normalized_allowlist,
        status=TaskStatus.pending,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    worker.register_task(task.id)
    worker.enqueue(task.id)
    return task


@app.get("/tasks", response_model=List[TaskRead])
def list_tasks(session: Session = Depends(get_session)) -> List[Task]:
    tasks = session.exec(select(Task).order_by(Task.created_at.desc())).all()
    return tasks


@app.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, session: Session = Depends(get_session)) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@app.get("/tasks/{task_id}/logs")
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
        return TaskLogSnapshot(task_id=task_id, entries=entries)

    async def event_generator():
        async for entry in worker.stream_logs(task_id):
            yield f"data: {entry}\n\n"
        yield "event: done\ndata: complete\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
