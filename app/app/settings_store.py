from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlmodel import Session

from .models import RunnerSetting

PROJECT_CONCURRENCY_KEY = "project_max_concurrency"
PROJECT_CONCURRENCY_ENV = "PROJECT_MAX_CONCURRENCY_DEFAULT"
PROJECT_CONCURRENCY_DEFAULT = 10


def _parse_positive_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    return parsed


def default_project_concurrency() -> int:
    env_value = os.getenv(PROJECT_CONCURRENCY_ENV)
    return _parse_positive_int(env_value, PROJECT_CONCURRENCY_DEFAULT)


def resolve_project_concurrency_setting(
    session: Session,
) -> Tuple[int, Optional[datetime], Optional[str]]:
    record = session.get(RunnerSetting, PROJECT_CONCURRENCY_KEY)
    fallback = default_project_concurrency()
    if record is None or record.value is None:
        return fallback, None, None
    limit = _parse_positive_int(record.value, fallback)
    return limit, record.updated_at, record.updated_by


def get_project_concurrency_limit(session: Session) -> int:
    limit, _, _ = resolve_project_concurrency_setting(session)
    return limit


def set_project_concurrency_limit(
    session: Session,
    limit: int,
    *,
    actor: Optional[str] = None,
) -> RunnerSetting:
    if limit < 1:
        raise ValueError("Project concurrency limit must be at least 1")
    record = session.get(RunnerSetting, PROJECT_CONCURRENCY_KEY)
    now = datetime.now(timezone.utc)
    value = str(limit)
    if record is None:
        record = RunnerSetting(
            key=PROJECT_CONCURRENCY_KEY,
            value=value,
            updated_at=now,
            updated_by=actor,
        )
    else:
        record.value = value
        record.updated_at = now
        record.updated_by = actor
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
