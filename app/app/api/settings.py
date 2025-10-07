from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..database import get_session
from ..schemas import ConcurrencySettings, ConcurrencySettingsUpdate
from ..settings_store import resolve_project_concurrency_setting, set_project_concurrency_limit
from ..worker import DEFAULT_MAX_CONCURRENCY, TaskQueueManager
from ..dependencies import get_worker, get_worker_optional
from ..services.audit import normalize_actor

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/concurrency", response_model=ConcurrencySettings)
def get_concurrency_settings(
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> ConcurrencySettings:
    limit, updated_at, updated_by = resolve_project_concurrency_setting(session)
    effective_limit = limit
    worker_pool_size = DEFAULT_MAX_CONCURRENCY
    parallel_enabled = False
    if worker is not None:
        configured_limit = worker.get_project_concurrency_limit()
        worker_pool_size = worker.get_worker_pool_size()
        effective_limit = min(configured_limit, worker_pool_size)
        parallel_enabled = worker.parallel_enabled
    return ConcurrencySettings(
        project_limit=limit,
        effective_project_limit=effective_limit,
        worker_pool_size=worker_pool_size,
        parallel_enabled=parallel_enabled,
        updated_at=updated_at,
        updated_by=updated_by,
    )


@router.patch("/concurrency", response_model=ConcurrencySettings)
def update_concurrency_settings(
    payload: ConcurrencySettingsUpdate,
    session: Session = Depends(get_session),
    worker: TaskQueueManager | None = Depends(get_worker_optional),
) -> ConcurrencySettings:
    limit = payload.project_limit
    if limit < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_limit must be at least 1")
    actor = normalize_actor(payload.actor)
    record = set_project_concurrency_limit(session, limit, actor=actor)

    effective_limit = limit
    worker_pool_size = DEFAULT_MAX_CONCURRENCY
    parallel_enabled = False
    if worker is not None:
        worker.set_project_concurrency_limit(limit)
        configured_limit = worker.get_project_concurrency_limit()
        worker_pool_size = worker.get_worker_pool_size()
        effective_limit = min(configured_limit, worker_pool_size)
        parallel_enabled = worker.parallel_enabled

    return ConcurrencySettings(
        project_limit=limit,
        effective_project_limit=effective_limit,
        worker_pool_size=worker_pool_size,
        parallel_enabled=parallel_enabled,
        updated_at=record.updated_at,
        updated_by=record.updated_by,
    )


__all__ = ["router"]
