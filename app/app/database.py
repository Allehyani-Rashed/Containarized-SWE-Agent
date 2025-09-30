from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy import inspect, text

from .models import Project


logger = logging.getLogger(__name__)

DEFAULT_DB_FILENAME = "app.db"
DB_ENV_VAR = "APP_DATABASE_URL"


def _build_database_url() -> str:
    env_url = os.getenv(DB_ENV_VAR)
    if env_url:
        return env_url
    db_path = Path(__file__).resolve().parent.parent / DEFAULT_DB_FILENAME
    return f"sqlite:///{db_path}"


database_url = _build_database_url()


_def_connect_args: dict[str, object] | None = None


def _engine_kwargs() -> dict[str, object]:
    global _def_connect_args
    if _def_connect_args is None:
        if database_url.startswith("sqlite"):
            _def_connect_args = {"connect_args": {"check_same_thread": False}}
        else:
            _def_connect_args = {}
    return dict(_def_connect_args)


def get_engine():
    return create_engine(database_url, **_engine_kwargs())


# Initialize shared engine lazily to play well with tests that may override env vars later.
engine = get_engine()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_project_columns(engine)
    _ensure_task_columns(engine)
    _ensure_integration_columns(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _ensure_project_columns(db_engine) -> None:
    try:
        inspector = inspect(db_engine)
        column_info = inspector.get_columns("project")
    except Exception as exc:
        logger.exception("Failed to inspect project table for schema updates: %s", exc)
        return

    columns = {column["name"] for column in column_info}

    if "local_path" in columns:
        _drop_legacy_project_local_path(db_engine, column_info)
        inspector = inspect(db_engine)
        column_info = inspector.get_columns("project")
        columns = {column["name"] for column in column_info}
    statements: dict[str, str] = {
        "gitlab_token": "ALTER TABLE project ADD COLUMN gitlab_token VARCHAR",
        "codex_token_encrypted": "ALTER TABLE project ADD COLUMN codex_token_encrypted VARCHAR",
        "codex_token_updated_at": "ALTER TABLE project ADD COLUMN codex_token_updated_at DATETIME",
        "cache_quota_mb": "ALTER TABLE project ADD COLUMN cache_quota_mb INTEGER",
        "cache_prune_after_hours": "ALTER TABLE project ADD COLUMN cache_prune_after_hours INTEGER",
    }

    pending = {name: ddl for name, ddl in statements.items() if name not in columns}
    if not pending:
        return

    with db_engine.begin() as connection:
        for ddl in pending.values():
            connection.execute(text(ddl))


def _drop_legacy_project_local_path(
    db_engine, column_info: list[dict[str, object]]
) -> None:
    columns_to_copy = [column["name"] for column in column_info if column["name"] != "local_path"]

    with db_engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        try:
            connection.exec_driver_sql("ALTER TABLE project RENAME TO project_local_path_legacy")
            Project.__table__.create(connection, checkfirst=False)
            if columns_to_copy:
                column_csv = ", ".join(columns_to_copy)
                insert_sql = (
                    f"INSERT INTO project ({column_csv}) SELECT {column_csv} FROM project_local_path_legacy"
                )
                connection.exec_driver_sql(insert_sql)
            connection.exec_driver_sql("DROP TABLE project_local_path_legacy")
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _ensure_task_columns(db_engine) -> None:
    try:
        inspector = inspect(db_engine)
        columns = {column_info["name"] for column_info in inspector.get_columns("task")}
    except Exception as exc:
        logger.exception("Failed to inspect task table for schema updates: %s", exc)
        return

    statements: dict[str, str] = {
        "codex_agent_version": "ALTER TABLE task ADD COLUMN codex_agent_version VARCHAR",
        "codex_invocation": "ALTER TABLE task ADD COLUMN codex_invocation VARCHAR",
        "codex_model": "ALTER TABLE task ADD COLUMN codex_model VARCHAR",
        "codex_reasoning_effort": "ALTER TABLE task ADD COLUMN codex_reasoning_effort VARCHAR",
        "abort_requested": "ALTER TABLE task ADD COLUMN abort_requested BOOLEAN NOT NULL DEFAULT 0",
        "cache_commit": "ALTER TABLE task ADD COLUMN cache_commit VARCHAR",
    }

    pending = {name: ddl for name, ddl in statements.items() if name not in columns}
    if not pending:
        return

    with db_engine.begin() as connection:
        for ddl in pending.values():
            connection.execute(text(ddl))



def _ensure_integration_columns(db_engine) -> None:
    try:
        inspector = inspect(db_engine)
        columns = {
            column_info["name"]
            for column_info in inspector.get_columns("integrationcredential")
        }
    except Exception as exc:
        logger.exception("Failed to inspect integration credential table for schema updates: %s", exc)
        return

    statements = {
        "verification_status": "ALTER TABLE integrationcredential ADD COLUMN verification_status VARCHAR",
        "verification_checked_at": "ALTER TABLE integrationcredential ADD COLUMN verification_checked_at DATETIME",
        "verification_error": "ALTER TABLE integrationcredential ADD COLUMN verification_error VARCHAR",
        "verification_host": "ALTER TABLE integrationcredential ADD COLUMN verification_host VARCHAR",
    }

    pending = {name: ddl for name, ddl in statements.items() if name not in columns}
    if not pending:
        return

    with db_engine.begin() as connection:
        for ddl in pending.values():
            connection.execute(text(ddl))
