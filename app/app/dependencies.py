from __future__ import annotations

from fastapi import HTTPException, status

from .worker import TaskQueueManager


_worker: TaskQueueManager | None = None


def set_worker(worker: TaskQueueManager | None) -> None:
    """Store the global TaskQueueManager instance used by API dependencies."""

    global _worker
    _worker = worker


def get_worker() -> TaskQueueManager:
    if _worker is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Worker not ready")
    return _worker


def get_worker_optional() -> TaskQueueManager | None:
    return _worker


__all__ = ["get_worker", "get_worker_optional", "set_worker"]
