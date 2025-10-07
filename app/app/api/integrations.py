from __future__ import annotations

from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session

from ..database import get_session
from ..dependencies import get_worker_optional
from ..integrations import (
    ChatGPTSessionError,
    GitLabPATVerificationError,
    clear_chatgpt_session_bundle,
    clear_gitlab_pat_token,
    get_gitlab_pat_status,
    set_chatgpt_session_bundle,
    set_gitlab_pat_token,
    verify_gitlab_pat,
)
from ..schemas import (
    ChatGPTSessionClearRequest,
    ChatGPTSessionImportRequest,
    GitLabPATClearRequest,
    GitLabPATRotateRequest,
    GitLabPATStatus,
    GitLabPATVerifyRequest,
)
from ..worker import TaskQueueManager

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/pat", response_model=GitLabPATStatus)
def read_gitlab_pat_status(session: Session = Depends(get_session)) -> GitLabPATStatus:
    return get_gitlab_pat_status(session)


@router.post("/pat", response_model=GitLabPATStatus)
def rotate_gitlab_pat(
    payload: GitLabPATRotateRequest,
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    token = (payload.token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token is required")

    active_task_ids: List[int] = worker.get_active_task_ids() if worker is not None else []

    with session.begin():
        credential = set_gitlab_pat_token(
            session,
            token,
            payload.updated_by,
            affected_task_ids=active_task_ids,
        )

    if worker is not None:
        worker.notify_gitlab_pat_stored(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


@router.delete("/pat", response_model=GitLabPATStatus)
def clear_gitlab_pat(
    payload: GitLabPATClearRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    actor = payload.updated_by if payload else None

    active_task_ids: List[int] = worker.get_active_task_ids() if worker is not None else []

    with session.begin():
        credential = clear_gitlab_pat_token(
            session,
            actor,
            affected_task_ids=active_task_ids,
        )

    if worker is not None:
        worker.notify_gitlab_pat_cleared(credential.updated_by, credential.updated_at)
        worker.fail_pending_tasks_due_to_missing_pat(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


@router.post("/pat/verify", response_model=GitLabPATStatus)
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


@router.post("/pat/session", response_model=GitLabPATStatus)
def import_chatgpt_session(
    payload: ChatGPTSessionImportRequest,
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    bundle = (payload.bundle or "").strip()
    if not bundle:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session bundle is required")

    try:
        active_task_ids: List[int] = worker.get_active_task_ids() if worker is not None else []

        with session.begin():
            credential = set_chatgpt_session_bundle(
                session,
                bundle,
                payload.updated_by,
                affected_task_ids=active_task_ids,
            )
    except ChatGPTSessionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if worker is not None:
        worker.notify_chatgpt_session_rotated(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


@router.delete("/pat/session", response_model=GitLabPATStatus)
def clear_chatgpt_session(
    payload: ChatGPTSessionClearRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> GitLabPATStatus:
    actor = payload.updated_by if payload else None

    active_task_ids: List[int] = worker.get_active_task_ids() if worker is not None else []

    with session.begin():
        credential = clear_chatgpt_session_bundle(
            session,
            actor,
            affected_task_ids=active_task_ids,
        )

    if worker is not None:
        worker.notify_chatgpt_session_cleared(credential.updated_by, credential.updated_at)

    return get_gitlab_pat_status(session)


__all__ = ["router"]
