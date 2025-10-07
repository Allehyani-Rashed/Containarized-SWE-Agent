"""Breakout sentinel handling for detecting workspace escape attempts."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .errors import ProjectCacheError
from .metadata import write_metadata

SENTINEL_FILENAME = ".codex-breakout-sentinel"


@dataclass(slots=True)
class SentinelState:
    path: Path
    token: str
    created_at: datetime


def sentinel_path(repo_path: Path) -> Path:
    return repo_path.parent / SENTINEL_FILENAME


def ensure_sentinel(
    repo_path: Path,
    metadata: dict[str, Any],
    *,
    log_fn: Callable[[str], None] | None = None,
    persist: bool = True,
) -> SentinelState:
    entry = _decode_entry(metadata)
    path = sentinel_path(repo_path)
    now = datetime.now(timezone.utc)

    if entry is None or not path.exists():
        token = secrets.token_hex(32)
        if log_fn:
            log_fn(f"Writing breakout sentinel at {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(token, encoding="utf-8")
        except OSError as exc:
            raise ProjectCacheError(
                f"Failed to write breakout sentinel at {path}: {exc}",
                reason="breakout-sentinel-write",
            ) from exc
        entry = {
            "path": str(path),
            "token": token,
            "created_at": now.isoformat(),
        }
        metadata["breakout_sentinel"] = entry
        if persist:
            write_metadata(repo_path, metadata)
    created_at = _parse_created_at(entry.get("created_at")) or now
    return SentinelState(path=path, token=entry["token"], created_at=created_at)


def validate_sentinel(repo_path: Path, metadata: dict[str, Any]) -> SentinelState:
    entry = _decode_entry(metadata)
    path = sentinel_path(repo_path)
    if entry is None:
        raise ProjectCacheError(
            f"Breakout sentinel metadata missing for cache at {repo_path}; re-bootstrap the cache",
            reason="breakout-sentinel-missing",
        )

    expected_path = Path(entry.get("path") or path)
    token = entry.get("token") or ""
    if expected_path != path:
        expected_path = path
    if not path.exists():
        raise ProjectCacheError(
            f"Breakout sentinel missing at {path}; inspect for workspace breakout attempts",
            reason="breakout-sentinel-missing",
        )

    try:
        on_disk = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ProjectCacheError(
            f"Breakout sentinel at {path} could not be read: {exc}",
            reason="breakout-sentinel-missing",
        ) from exc
    if not token or on_disk != token:
        raise ProjectCacheError(
            f"Breakout sentinel at {path} has unexpected contents; investigate for escape attempts",
            reason="breakout-sentinel-mismatch",
        )

    created_at = _parse_created_at(entry.get("created_at")) or datetime.now(timezone.utc)
    return SentinelState(path=path, token=token, created_at=created_at)


def _decode_entry(metadata: dict[str, Any]) -> dict[str, Any] | None:
    entry = metadata.get("breakout_sentinel")
    if isinstance(entry, dict) and "token" in entry:
        return entry
    return None


def _parse_created_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = ["SENTINEL_FILENAME", "SentinelState", "ensure_sentinel", "sentinel_path", "validate_sentinel"]
