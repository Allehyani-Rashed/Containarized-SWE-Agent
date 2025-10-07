"""Snapshot creation and pruning for project cache repositories."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .git_ops import command_error, git_env, run_git_command
from .metadata import load_metadata, write_metadata, parse_iso8601
from .utils import is_truthy

logger = logging.getLogger(__name__)

SNAPSHOT_DIRNAME = "snapshots"
DEFAULT_RETENTION_HOURS = 168  # one week
DEFAULT_SNAPSHOT_LIMIT = 20


@dataclass(slots=True)
class SnapshotOutcome:
    created_path: Path | None
    removed_paths: list[Path]
    metadata: dict[str, Any]


def create_snapshot(
    repo_path: Path,
    *,
    commit_hash: str,
    branch: str,
    dry_run: bool,
    log_fn: Callable[[str], None],
    retention_hours: int | None = None,
    max_snapshots: int | None = None,
) -> SnapshotOutcome:
    if not commit_hash or commit_hash == "dry-run-skip":
        return SnapshotOutcome(created_path=None, removed_paths=[], metadata=load_metadata(repo_path))

    log = log_fn
    retention_env = os.environ.get("PROJECT_CACHE_SNAPSHOT_RETENTION_HOURS")
    limit_env = os.environ.get("PROJECT_CACHE_MAX_SNAPSHOTS")

    retention = (
        int(retention_env)
        if retention_env and retention_env.strip().isdigit()
        else DEFAULT_RETENTION_HOURS
    )
    if retention_hours is not None:
        retention = retention_hours
    limit = (
        int(limit_env)
        if limit_env and limit_env.strip().isdigit()
        else DEFAULT_SNAPSHOT_LIMIT
    )
    if max_snapshots is not None:
        limit = max_snapshots

    enabled_env = os.environ.get("PROJECT_CACHE_SNAPSHOT_ENABLED")
    if enabled_env is not None and not is_truthy(enabled_env):
        log("Project cache snapshots disabled via PROJECT_CACHE_SNAPSHOT_ENABLED")
        metadata = load_metadata(repo_path)
        return SnapshotOutcome(created_path=None, removed_paths=[], metadata=metadata)

    now = datetime.now(timezone.utc)
    snapshot_dir = repo_path.parent / SNAPSHOT_DIRNAME
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    safe_branch = branch.replace(os.sep, "-") if branch else "branch"
    filename = f"{timestamp}-{safe_branch}-{commit_hash[:12]}.bundle"
    snapshot_path = snapshot_dir / filename

    if dry_run:
        log(f"RUNNER_GIT_DRY_RUN=1 set; would create cache snapshot at {snapshot_path}")
        metadata = load_metadata(repo_path)
        snapshots = list(_existing_snapshots(metadata))
        snapshots.append(
            {
                "path": str(snapshot_path),
                "created_at": now.isoformat(),
                "commit": commit_hash,
                "branch": branch,
            }
        )
        metadata["snapshots"] = snapshots
        metadata["last_snapshot_at"] = now.isoformat()
        return SnapshotOutcome(created_path=snapshot_path, removed_paths=[], metadata=metadata)

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    env = git_env()
    log(f"Creating cache snapshot bundle at {snapshot_path}")
    bundle_result = run_git_command([
        "git",
        "bundle",
        "create",
        str(snapshot_path),
        "HEAD",
    ], repo_path, env)
    if bundle_result.returncode != 0:
        raise command_error(repo_path, bundle_result, identifier=str(repo_path))

    metadata = load_metadata(repo_path)
    snapshots = list(_existing_snapshots(metadata))
    snapshots.append(
        {
            "path": str(snapshot_path),
            "created_at": now.isoformat(),
            "commit": commit_hash,
            "branch": branch,
        },
    )

    cutoff = now - timedelta(hours=max(retention, 0))
    retained: list[dict[str, Any]] = []
    removed_paths: list[Path] = []
    for snapshot in sorted(snapshots, key=lambda entry: entry.get("created_at", "")):
        created_at = parse_iso8601(snapshot.get("created_at"))
        path_value = snapshot.get("path")
        path = Path(path_value) if isinstance(path_value, str) and path_value else None
        if created_at and created_at < cutoff:
            if path is not None:
                removed_paths.append(path)
            continue
        retained.append(snapshot)

    snapshots = retained
    if limit > 0 and len(snapshots) > limit:
        overflow = len(snapshots) - limit
        removed = snapshots[:overflow]
        snapshots = snapshots[overflow:]
        for entry in removed:
            path_value = entry.get("path")
            if isinstance(path_value, str) and path_value:
                removed_paths.append(Path(path_value))

    if dry_run:
        for path in removed_paths:
            log(f"RUNNER_GIT_DRY_RUN=1 set; would remove snapshot {path}")
    else:
        for path in removed_paths:
            if not path:
                continue
            try:
                path.unlink()
                log(f"Removed expired cache snapshot {path}")
            except OSError:
                logger.info("Failed to remove snapshot %s", path)

    metadata["snapshots"] = snapshots
    metadata["last_snapshot_at"] = now.isoformat()
    write_metadata(repo_path, metadata)

    return SnapshotOutcome(created_path=snapshot_path, removed_paths=removed_paths, metadata=metadata)


def _existing_snapshots(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(metadata.get("snapshots"), list):
        return [snapshot for snapshot in metadata["snapshots"] if isinstance(snapshot, dict)]
    return []


__all__ = ["DEFAULT_RETENTION_HOURS", "DEFAULT_SNAPSHOT_LIMIT", "SNAPSHOT_DIRNAME", "SnapshotOutcome", "create_snapshot"]
