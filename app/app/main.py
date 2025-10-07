from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import register_routers
from .database import engine, init_db
from .dependencies import get_worker, get_worker_optional, set_worker
from .services.workspaces import WORKSPACES_ROOT
from .worker import TaskQueueManager


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    worker = TaskQueueManager(engine)
    set_worker(worker)
    try:
        yield
    finally:
        worker.shutdown()
        set_worker(None)


app = FastAPI(title="Containerized Codex Agent", lifespan=lifespan)

register_routers(app)

__all__ = ["app", "get_worker", "get_worker_optional", "WORKSPACES_ROOT"]
