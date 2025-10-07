"""Helpers for reading and writing cache metadata sidecar files."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_METADATA_FILENAME = "cache-metadata.json"


def metadata_path(repo_path: Path) -> Path:
    """Return the metadata file path for the given repository clone."""

    return repo_path.parent / CACHE_METADATA_FILENAME


def load_metadata(repo_path: Path) -> dict[str, Any]:
    """Load cache metadata, returning an empty mapping when missing."""

    path = metadata_path(repo_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def write_metadata(repo_path: Path, metadata: dict[str, Any]) -> None:
    """Persist metadata alongside the repository clone."""

    path = metadata_path(repo_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    except OSError:
        logger.info("Failed to persist cache metadata at %s", path)


def parse_iso8601(value: str | None) -> datetime | None:
    """Parse ISO-8601 strings returning timezone aware datetimes."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = ["CACHE_METADATA_FILENAME", "load_metadata", "metadata_path", "parse_iso8601", "write_metadata"]

