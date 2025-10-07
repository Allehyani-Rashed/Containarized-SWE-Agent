"""Retention and quota policy enforcement for project caches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .errors import ProjectCacheError
from .git_ops import command_error, directory_size_bytes, git_env, run_git_command
from .metadata import load_metadata, parse_iso8601, write_metadata


@dataclass(slots=True)
class PolicyOutcome:
    metadata: dict
    pruned: bool
    size_bytes: int


def enforce_policy(
    project_root: Path,
    *,
    quota_mb: int | None,
    prune_after_hours: int | None,
    dry_run: bool,
    log_fn: Callable[[str], None],
) -> PolicyOutcome:
    repo_path = project_root.expanduser().resolve()
    if not repo_path.exists():
        log_fn(f"Cache path {repo_path} missing; skipping policy enforcement")
        return PolicyOutcome(metadata={}, pruned=False, size_bytes=0)

    metadata = load_metadata(repo_path)
    now = datetime.now(timezone.utc)

    env = git_env()

    last_pruned_at = parse_iso8601(metadata.get("last_pruned_at")) if isinstance(metadata, dict) else None
    prune_due = False
    if isinstance(prune_after_hours, int) and prune_after_hours > 0:
        cutoff = now - timedelta(hours=prune_after_hours)
        if last_pruned_at is None or last_pruned_at < cutoff:
            prune_due = True

    pruned = False

    if prune_due:
        if dry_run:
            log_fn(
                f"RUNNER_GIT_DRY_RUN=1 set; would run 'git gc --prune=now --aggressive' for cache at {repo_path}",
            )
        else:
            log_fn(f"Running git gc --prune=now --aggressive for cache at {repo_path}")
            gc_result = run_git_command(
                ["git", "gc", "--prune=now", "--aggressive"],
                repo_path,
                env,
            )
            if gc_result.returncode != 0:
                raise command_error(repo_path, gc_result, identifier=str(repo_path))
            metadata["last_pruned_at"] = now.isoformat()
            pruned = True

    size_bytes = directory_size_bytes(repo_path)
    metadata["last_recorded_size_bytes"] = size_bytes
    metadata["last_refreshed_at"] = now.isoformat()

    if isinstance(quota_mb, int) and quota_mb > 0:
        quota_bytes = quota_mb * 1024 * 1024
        if size_bytes > quota_bytes:
            if dry_run:
                log_fn(
                    f"RUNNER_GIT_DRY_RUN=1 set; cache size {size_bytes / (1024 * 1024):.2f} MB exceeds quota {quota_mb} MB",
                )
            else:
                if not prune_due:
                    log_fn(
                        f"Cache size {size_bytes / (1024 * 1024):.2f} MB exceeds quota {quota_mb} MB; running git gc --prune=now",
                    )
                    gc_result = run_git_command(
                        ["git", "gc", "--prune=now"],
                        repo_path,
                        env,
                    )
                    if gc_result.returncode != 0:
                        raise command_error(repo_path, gc_result, identifier=str(repo_path))
                    metadata["last_pruned_at"] = now.isoformat()
                    size_bytes = directory_size_bytes(repo_path)
                    metadata["last_recorded_size_bytes"] = size_bytes
                    pruned = True
                if size_bytes > quota_bytes:
                    raise ProjectCacheError(
                        (
                            f"Cache at {repo_path} remains above quota after pruning ({size_bytes / (1024 * 1024):.2f} MB > {quota_mb} MB). "
                            "Increase the project quota, clear the cache directory, or move large assets (such as Git LFS) to alternative storage."
                        ),
                        reason="cache-quota-exceeded",
                    )

    if not dry_run:
        write_metadata(repo_path, metadata)

    return PolicyOutcome(metadata=metadata, pruned=pruned, size_bytes=size_bytes)


__all__ = ["PolicyOutcome", "enforce_policy"]

