from __future__ import annotations

"""FastAPI router registrations for the orchestrator service."""

from fastapi import FastAPI

from .diagnostics import router as diagnostics_router
from .integrations import router as integrations_router
from .models import router as models_router
from .projects import router as projects_router
from .settings import router as settings_router
from .tasks import router as tasks_router


def register_routers(app: FastAPI) -> None:
    """Attach all domain-specific routers to the FastAPI application."""

    app.include_router(integrations_router)
    app.include_router(settings_router)
    app.include_router(models_router)
    app.include_router(projects_router)
    app.include_router(tasks_router)
    app.include_router(diagnostics_router)


__all__ = ["register_routers"]
