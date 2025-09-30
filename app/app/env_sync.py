from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from sqlmodel import Session, select

from .database import engine, init_db
from .integrations import (
    ChatGPTSessionError,
    get_gitlab_pat_status,
    set_chatgpt_session_bundle,
    set_gitlab_pat_token,
)
from .models import Project
from .secrets import SecretError, get_secret_manager

ENV_ACTOR_FALLBACK = "env-sync"
SESSION_BUNDLE_DEFAULT = "chatgpt_session_bundle.json"


class EnvSyncError(RuntimeError):
    """Raised when automatic credential synchronisation fails."""


@dataclass
class EnvConfig:
    gitlab_pat: Optional[str]
    codex_token: Optional[str]
    project_name: Optional[str]
    project_default_branch: Optional[str]
    gitlab_host: Optional[str]
    gitlab_project_path: Optional[str]
    session_bundle_path: Optional[Path]
    session_bundle_inline: Optional[str]
    actor: str = ENV_ACTOR_FALLBACK


@dataclass
class EnvSyncResult:
    gitlab_pat_updated: bool = False
    session_bundle_updated: bool = False
    session_bundle_error: Optional[str] = None
    project_created: bool = False
    project_updated: bool = False
    codex_token_updated: bool = False
    project_id: Optional[int] = None


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a dotenv-style file into a key/value mapping."""
    if not path.exists():
        raise EnvSyncError(f"env file not found: {path}")

    env: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value:
            if (value[0] == value[-1]) and value[0] in {'"', "'"}:
                value = value[1:-1]
        env[key] = value
    return env


def _read_session_bundle(config: EnvConfig, repo_root: Path) -> Optional[str]:
    if config.session_bundle_inline:
        bundle = config.session_bundle_inline.strip()
        return bundle or None

    candidate_path = config.session_bundle_path
    if candidate_path is None:
        default_path = repo_root / SESSION_BUNDLE_DEFAULT
        if default_path.exists():
            candidate_path = default_path

    if candidate_path is None:
        return None

    try:
        data = candidate_path.expanduser().read_text(encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 - surface readable failure
        raise EnvSyncError(f"failed to read session bundle: {exc}") from exc
    bundle = data.strip()
    return bundle or None


def _locate_project(session: Session, config: EnvConfig) -> Optional[Project]:
    statement = None
    if config.gitlab_host and config.gitlab_project_path:
        statement = (
            select(Project)
            .where(Project.gitlab_host == config.gitlab_host)
            .where(Project.gitlab_project_path == config.gitlab_project_path)
        )
    elif config.project_name:
        statement = select(Project).where(Project.name == config.project_name)
    if statement is None:
        return None
    return session.exec(statement).first()


def _ensure_project(session: Session, config: EnvConfig) -> EnvSyncResult:
    result = EnvSyncResult()
    project = _locate_project(session, config)

    if project is None:
        required_fields = [
            config.project_name,
            config.project_default_branch,
            config.gitlab_host,
            config.gitlab_project_path,
        ]
        if all(required_fields):
            project = Project(
                name=config.project_name,  # type: ignore[arg-type]
                default_branch=config.project_default_branch,  # type: ignore[arg-type]
                gitlab_host=config.gitlab_host,  # type: ignore[arg-type]
                gitlab_project_path=config.gitlab_project_path,  # type: ignore[arg-type]
            )
            session.add(project)
            session.flush()
            result.project_created = True
            result.project_id = project.id
        else:
            return result
    else:
        result.project_id = project.id

    updated = False
    fields = {
        "name": config.project_name,
        "default_branch": config.project_default_branch,
        "gitlab_host": config.gitlab_host,
        "gitlab_project_path": config.gitlab_project_path,
    }
    for field, value in fields.items():
        if value and getattr(project, field) != value:
            setattr(project, field, value)
            updated = True

    if config.codex_token:
        manager = get_secret_manager()
        existing = None
        if project.codex_token_encrypted:
            try:
                existing = manager.decrypt(project.codex_token_encrypted)
            except SecretError:
                existing = None
        if existing != config.codex_token:
            project.codex_token_encrypted = manager.encrypt(config.codex_token)
            project.codex_token_updated_at = datetime.now(timezone.utc)
            updated = True
            result.codex_token_updated = True

    if updated:
        session.add(project)
        result.project_updated = True

    return result


def sync_credentials(config: EnvConfig, *, repo_root: Optional[Path] = None) -> EnvSyncResult:
    """Sync credentials based on env-derived configuration."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]

    init_db()
    result = EnvSyncResult()
    with Session(engine) as session:
        with session.begin():
            if config.gitlab_pat:
                set_gitlab_pat_token(session, config.gitlab_pat, config.actor)
                result.gitlab_pat_updated = True

            bundle_error: Optional[str] = None
            bundle: Optional[str]
            try:
                bundle = _read_session_bundle(config, repo_root)
            except EnvSyncError as exc:
                bundle = None
                bundle_error = str(exc)

            if bundle:
                try:
                    set_chatgpt_session_bundle(session, bundle, config.actor)
                except ChatGPTSessionError as exc:
                    bundle_error = str(exc)
                else:
                    result.session_bundle_updated = True

            if bundle_error:
                result.session_bundle_error = bundle_error

            project_result = _ensure_project(session, config)
            result.project_created = project_result.project_created
            result.project_updated = project_result.project_updated
            result.codex_token_updated = project_result.codex_token_updated
            result.project_id = project_result.project_id

    return result


def get_current_status() -> Dict[str, bool]:
    """Return a snapshot of whether key credentials are configured."""
    init_db()
    with Session(engine) as session:
        status = get_gitlab_pat_status(session)
        project_count = session.exec(select(Project)).all()
    return {
        "gitlab_pat": status.configured,
        "chatgpt_session": status.session_configured,
        "project_registered": bool(project_count),
    }
