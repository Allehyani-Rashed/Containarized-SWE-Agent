from __future__ import annotations

import logging
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func
from sqlmodel import Session, select

from .allowlist import normalize_user_allowlist
from .codex_models import (
    default_model_id,
    default_reasoning_effort,
    iter_models,
    valid_model_ids,
    valid_reasoning_efforts,
)
from .database import engine, get_session, init_db
from .models import AuditLog, Project, Task, TaskStatus
from .project_cache import project_cache_repo_path
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
    CodexModelSummary,
    GitLabPATClearRequest,
    GitLabPATRotateRequest,
    GitLabPATStatus,
    GitLabPATVerifyRequest,
    ProjectCreate,
    ProjectDeleteRequest,
    ProjectDetail,
    ProjectRead,
    ProjectTaskSummary,
    ProjectUpdate,
    TaskAbortRequest,
    TaskCreate,
    TaskDeleteRequest,
    TaskLogSnapshot,
    TaskListResponse,
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


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACES_ROOT = REPO_ROOT / "workspaces"


logger = logging.getLogger(__name__)


def _record_audit_event(session: Session, action: str, actor: str | None, details: str | None) -> None:
    entry = AuditLog(action=action, actor=actor, details=details)
    session.add(entry)


def _normalize_actor(actor: str | None) -> str | None:
    if actor is None:
        return None
    actor = actor.strip()
    return actor or None


def _normalize_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    value = reason.strip()
    return value or None


def _normalize_non_empty(value: str | None, *, field: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} cannot be empty",
        )
    return candidate


def _normalize_gitlab_host(value: str | None) -> str:
    host = _normalize_non_empty(value, field="GitLab host")
    return host.rstrip("/")


def _normalize_gitlab_project_path(value: str | None) -> str:
    path = _normalize_non_empty(value, field="GitLab project path")
    return path.strip("/")


def _ensure_unique_project(
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project already registered for {repository}",
        )


def _remove_workspace(path_str: str | None) -> None:
    if not path_str:
        return
    try:
        candidate = Path(path_str).resolve()
    except OSError as exc:
        logger.warning("Unable to resolve workspace path %s: %s", path_str, exc)
        return
    try:
        workspace_root = WORKSPACES_ROOT.resolve()
    except OSError as exc:
        logger.warning("Unable to resolve workspaces root %s: %s", WORKSPACES_ROOT, exc)
        return
    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        return
    if candidate.is_dir():
        try:
            shutil.rmtree(candidate)
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("Failed to remove workspace directory %s: %s", candidate, exc)
    else:
        try:
            candidate.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("Failed to remove workspace file %s: %s", candidate, exc)


def _build_repository_url(project: Project) -> str:
    host = (project.gitlab_host or "").rstrip("/")
    path = (project.gitlab_project_path or "").lstrip("/")
    if not host:
        return path
    if not path:
        return host
    return f"{host}/{path}"


def _derive_last_activity(task: Task | None) -> datetime | None:
    if task is None:
        return None
    for candidate in (task.finished_at, task.started_at, task.created_at):
        if candidate is not None:
            return candidate
    return None


def _derive_allowlist_status(task: Task | None) -> str:
    if task is None:
        return "unknown"
    allowlist = task.allowlist or []
    return "custom" if allowlist else "empty"


def _collect_project_metrics(
    session: Session,
    projects: Sequence[Project],
) -> Dict[int, Dict[str, Any]]:
    metrics: Dict[int, Dict[str, Any]] = {}
    project_ids = [project.id for project in projects if project.id is not None]
    for project in projects:
        if project.id is None:
            continue
        metrics[project.id] = {
            "last_task_at": None,
            "last_task_status": None,
            "allowlist_status": "unknown",
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
        .where(
            Task.project_id.in_(project_ids),
            Task.status.in_([TaskStatus.pending, TaskStatus.running]),
        )
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
        data["last_task_at"] = _derive_last_activity(task)
        data["last_task_status"] = task.status
        data["last_cache_commit"] = task.cache_commit
        data["allowlist_status"] = _derive_allowlist_status(task)
        if len(seen) == len(project_ids):
            break

    return metrics


def _task_to_read(task: Task) -> TaskRead:
    payload = TaskRead.model_validate(task)
    if not payload.codex_model:
        payload.codex_model = _normalize_codex_model(None)
    if not payload.codex_reasoning_effort:
        payload.codex_reasoning_effort = default_reasoning_effort()
    return payload


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


_VALID_CODEX_MODEL_IDS = valid_model_ids()
_VALID_REASONING_EFFORTS = valid_reasoning_efforts()
_BRANCH_FORBIDDEN_PATTERN = re.compile(r"[\s~^:?*\\[\\]\\x00-\\x1F\\x7F]")


def _normalize_branch_name(raw: str) -> str:
    branch = (raw or "").strip()
    if not branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot be empty")
    if branch in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot be '.' or '..'")
    if branch.startswith("/") or branch.endswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot start or end with '/'")
    if branch.startswith("-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot start with '-'")
    if branch.endswith(".") or branch.endswith(" "):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot end with '.' or space")
    if branch.endswith(".lock"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot end with '.lock'")
    if ".." in branch or "@{" in branch or "//" in branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name contains invalid sequences")
    if branch.startswith("refs/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot start with 'refs/'")
    if _BRANCH_FORBIDDEN_PATTERN.search(branch):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name contains invalid characters")
    if len(branch.encode("utf-8")) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name is too long (max 255 bytes)")

    try:
        subprocess.run(
            ["git", "check-ref-format", "--branch", branch],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        # Fallback validation already performed; continue without git binary.
        return branch
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name is not a valid git reference") from exc

    return branch


def _normalize_codex_model(model_id: str | None) -> str:
    candidate = (model_id or "").strip()
    if not candidate:
        default = default_model_id()
        if default is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No Codex model configured")
        return default
    if candidate not in _VALID_CODEX_MODEL_IDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown Codex model requested")
    return candidate


def _normalize_codex_reasoning_effort(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return default_reasoning_effort()
    if candidate not in _VALID_REASONING_EFFORTS:
        allowed = ", ".join(sorted(_VALID_REASONING_EFFORTS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Codex reasoning effort; expected one of: {allowed}",
        )
    return candidate


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



def _project_to_read(project: Project, extras: Dict[str, Any] | None = None) -> ProjectRead:
    cache_path = str(project_cache_repo_path(project.gitlab_host, project.gitlab_project_path))
    repo_exists = Path(cache_path).exists()
    cache_git_dir = Path(cache_path) / ".git"
    cache_status = "ready" if cache_git_dir.exists() else ("present" if repo_exists else "missing")
    update_payload: Dict[str, Any] = {
        "codex_token_configured": bool(project.codex_token_encrypted),
        "codex_token_updated_at": project.codex_token_updated_at,
        "repository_url": _build_repository_url(project),
        "cache_path": cache_path,
        "cache_status": cache_status,
        "cache_quota_mb": project.cache_quota_mb,
        "cache_prune_after_hours": project.cache_prune_after_hours,
        "last_cache_commit": None,
    }
    if extras:
        update_payload.update(extras)
    return ProjectRead.model_validate(
        project,
        from_attributes=True,
        update=update_payload,
    )


@app.get("/metrics")
def metrics_endpoint() -> Response:
    payload = generate_latest()
    return Response(payload, media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/models", response_model=List[CodexModelSummary])
def list_codex_models() -> List[CodexModelSummary]:
    return [
        CodexModelSummary(
            id=model.id,
            label=model.label,
            description=model.description,
            is_default=model.is_default,
        )
        for model in iter_models()
    ]


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    data = payload.model_dump()
    raw_codex_token = (data.pop("codex_token", None) or "").strip()

    name = _normalize_non_empty(data.get("name"), field="Project name")
    default_branch = _normalize_branch_name(data.get("default_branch") or "")
    gitlab_host = _normalize_gitlab_host(data.get("gitlab_host"))
    gitlab_project_path = _normalize_gitlab_project_path(data.get("gitlab_project_path"))

    for numeric_field in ("cache_quota_mb", "cache_prune_after_hours"):
        value = data.get(numeric_field)
        if value is None:
            continue
        if value < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{numeric_field.replace('_', ' ')} must be non-negative",
            )

    _ensure_unique_project(
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
    )
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
    metrics = _collect_project_metrics(session, projects)
    return [
        _project_to_read(project, metrics.get(project.id) if project.id is not None else None)
        for project in projects
    ]


@app.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project_detail(project_id: int, session: Session = Depends(get_session)) -> ProjectDetail:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    metrics = _collect_project_metrics(session, [project])
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
            codex_model=task.codex_model or _normalize_codex_model(None),
            codex_reasoning_effort=(task.codex_reasoning_effort or default_reasoning_effort()),
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
            allowlist_size=len(task.allowlist or []),
            cache_commit=task.cache_commit,
        )
        for task in recent_rows
    ]

    summary = _project_to_read(project, extras)
    payload = summary.model_dump()
    payload["recent_tasks"] = recent_tasks
    return ProjectDetail(**payload)


@app.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    payload_data = payload.model_dump(exclude_unset=True)
    actor = _normalize_actor(payload_data.pop("actor", None))
    clear_codex_flag = bool(payload_data.pop("clear_codex_token", False))
    _codex_marker = object()
    codex_token_value = payload_data.pop("codex_token", _codex_marker)
    codex_token_provided = codex_token_value is not _codex_marker

    updated_fields: list[str] = []
    numeric_fields = {"cache_quota_mb", "cache_prune_after_hours"}

    if "name" in payload_data:
        name = _normalize_non_empty(payload_data["name"], field="Project name")
        if project.name != name:
            project.name = name
            updated_fields.append("name")

    if "default_branch" in payload_data:
        default_branch = _normalize_branch_name(payload_data["default_branch"] or "")
        if project.default_branch != default_branch:
            project.default_branch = default_branch
            updated_fields.append("default_branch")

    if "gitlab_host" in payload_data:
        gitlab_host = _normalize_gitlab_host(payload_data["gitlab_host"])
        if project.gitlab_host != gitlab_host:
            project.gitlab_host = gitlab_host
            updated_fields.append("gitlab_host")

    if "gitlab_project_path" in payload_data:
        gitlab_project_path = _normalize_gitlab_project_path(payload_data["gitlab_project_path"])
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

    manager = get_secret_manager()
    codex_token_state = None
    if codex_token_provided:
        raw_value = (codex_token_value or "").strip()
        if raw_value:
            project.codex_token_encrypted = manager.encrypt(raw_value)
            project.codex_token_updated_at = datetime.now(timezone.utc)
            codex_token_state = "updated"
        else:
            project.codex_token_encrypted = None
            project.codex_token_updated_at = None
            codex_token_state = "cleared"
    elif clear_codex_flag:
        project.codex_token_encrypted = None
        project.codex_token_updated_at = None
        codex_token_state = "cleared"

    session.add(project)

    details_bits = [f"project_id={project_id}"]
    if updated_fields:
        details_bits.append(f"fields={','.join(updated_fields)}")
    if codex_token_state:
        details_bits.append(f"codex_token={codex_token_state}")
    audit_details = ", ".join(details_bits)
    if updated_fields or codex_token_state:
        _record_audit_event(session, "project.updated", actor, audit_details)

    _ensure_unique_project(
        session,
        gitlab_host=project.gitlab_host,
        gitlab_project_path=project.gitlab_project_path,
        exclude_id=project.id,
    )

    session.commit()
    session.refresh(project)

    metrics = _collect_project_metrics(session, [project])
    return _project_to_read(project, metrics.get(project_id))


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
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

    actor = _normalize_actor(payload.actor if payload else None)
    audit_details = f"project_id={project_id}"

    tasks = session.exec(select(Task).where(Task.project_id == project_id)).all()
    task_ids = [task.id for task in tasks if task.id is not None]
    workspaces = [task.workspace_path for task in tasks]

    for task in tasks:
        session.delete(task)

    session.delete(project)
    _record_audit_event(session, "project.deleted", actor, audit_details)
    session.commit()

    for task_id in task_ids:
        worker.handle_task_deleted(task_id)
    for path in workspaces:
        _remove_workspace(path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
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

    normalized_allowlist = normalize_user_allowlist(payload.allowlist or [])
    branch_override = _normalize_branch_name(payload.branch_name) if payload.branch_name else None
    codex_model = _normalize_codex_model(payload.codex_model)
    reasoning_effort = _normalize_codex_reasoning_effort(payload.codex_reasoning_effort)

    task = Task(
        project_id=payload.project_id,
        prompt=payload.prompt,
        allowlist=normalized_allowlist,
        status=TaskStatus.pending,
        branch=branch_override,
        codex_model=codex_model,
        codex_reasoning_effort=reasoning_effort,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    worker.register_task(task.id)
    worker.enqueue(task.id)
    return _task_to_read(task)


@app.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    session: Session = Depends(get_session),
    statuses: str | None = Query(default=None, description="Comma-separated list of task statuses to include"),
    codex_model: str | None = Query(default=None, description="Filter by Codex model identifier"),
    branch: str | None = Query(default=None, description="Case-insensitive substring match on branch name"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of tasks to return"),
    offset: int = Query(default=0, ge=0, description="Number of matching tasks to skip"),
) -> TaskListResponse:
    filters = []

    if statuses:
        candidates = [value.strip() for value in statuses.split(",") if value.strip()]
        statuses: set[TaskStatus] = set()
        invalid: list[str] = []
        for candidate in candidates:
            try:
                statuses.add(TaskStatus(candidate))
            except ValueError:
                invalid.append(candidate)
        if invalid:
            formatted = ", ".join(sorted(dict.fromkeys(invalid)))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid task status value(s): {formatted}",
            )
        if statuses:
            filters.append(Task.status.in_(list(statuses)))

    if codex_model is not None:
        normalized_model = _normalize_codex_model(codex_model)
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

    items = [_task_to_read(row) for row in rows]
    next_offset = offset + limit if offset + limit < total else None

    return TaskListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
    )


@app.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, session: Session = Depends(get_session)) -> TaskRead:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _task_to_read(task)


@app.post("/tasks/{task_id}/abort", response_model=TaskRead)
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

    actor = _normalize_actor(payload.actor if payload else None)
    reason = _normalize_reason(payload.reason if payload else None)
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
        _record_audit_event(session, "task.abort.pending", actor, audit_details)
        session.commit()
        worker.record_task_log(task_id, log_message)
        worker.mark_task_aborted(task_id)
        session.refresh(task)
        return _task_to_read(task)

    task.abort_requested = True
    session.add(task)
    _record_audit_event(session, "task.abort.requested", actor, audit_details)
    session.commit()
    worker.record_task_log(task_id, log_message)
    worker.request_abort(task_id)
    session.refresh(task)
    return _task_to_read(task)


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
        return TaskLogSnapshot(
            task_id=task_id,
            entries=entries,
            status=task.status,
            branch=task.branch,
            codex_model=task.codex_model,
            codex_reasoning_effort=task.codex_reasoning_effort or default_reasoning_effort(),
            abort_requested=bool(task.abort_requested),
        )

    async def event_generator():
        async for entry in worker.stream_logs(task_id):
            yield f"data: {entry}\n\n"
        terminal_event = worker.get_terminal_event(task_id) or "done"
        if terminal_event == "aborted":
            yield "event: aborted\ndata: aborted\n\n"
        elif terminal_event == "deleted":
            yield "event: deleted\ndata: deleted\n\n"
        else:
            yield "event: done\ndata: complete\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
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

    actor = _normalize_actor(payload.actor if payload else None)
    audit_details = f"task_id={task_id}"

    workspace_path = task.workspace_path

    _record_audit_event(session, "task.deleted", actor, audit_details)
    session.delete(task)
    session.commit()

    worker.handle_task_deleted(task_id)
    _remove_workspace(workspace_path)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
