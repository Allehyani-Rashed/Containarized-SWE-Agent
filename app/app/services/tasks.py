from __future__ import annotations

from typing import Optional

from ..codex_models import default_reasoning_effort
from ..models import Task, TaskChangeMode
from ..schemas import TaskCredentialStatus, TaskRead
from ..worker import TaskQueueManager
from .validators import normalize_codex_model


def task_to_read(task: Task, worker: Optional[TaskQueueManager] = None) -> TaskRead:
    payload = TaskRead.model_validate(task)
    if not payload.change_mode:
        payload.change_mode = TaskChangeMode.merge_request
    if not payload.codex_model:
        payload.codex_model = normalize_codex_model(None)
    if not payload.codex_reasoning_effort:
        payload.codex_reasoning_effort = default_reasoning_effort()
    if worker is not None and payload.id is not None:
        credentials = worker.get_task_credentials(payload.id)
        payload.credentials = TaskCredentialStatus.model_validate(credentials)
    return payload


__all__ = ["task_to_read"]
