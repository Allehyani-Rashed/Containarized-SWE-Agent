"""High-level service orchestrating project cache workflows."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import metrics as metrics_module
from . import git_ops as project_cache_git_ops
from .errors import ProjectCacheError
from .locking import cache_operation_lock
from .metadata import load_metadata, write_metadata
from .paths import (
    build_project_remote_url,
    ensure_cache_root,
    project_cache_identifier,
    project_cache_repo_path,
    project_cache_slug,
)
from .policy import PolicyOutcome, enforce_policy
from .sentinel import ensure_sentinel, validate_sentinel
from .snapshots import SnapshotOutcome, create_snapshot


@dataclass(slots=True)
class RefreshEvent:
    identifier: str
    commit_hash: str
    duration_seconds: float
    dry_run: bool


@dataclass(slots=True)
class SnapshotPrunedEvent:
    identifier: str
    removed_path: Path


@dataclass(slots=True)
class BreakoutEvent:
    identifier: str
    repo_path: Path
    reason: str


@dataclass(slots=True)
class ProjectCacheCallbacks:
    on_refresh_complete: Callable[[RefreshEvent], None] | None = None
    on_snapshot_pruned: Callable[[SnapshotPrunedEvent], None] | None = None
    on_breakout_detected: Callable[[BreakoutEvent], None] | None = None


class ProjectCacheService:
    """Facade for cache bootstrap, refresh, policy, and snapshot operations."""

    def __init__(
        self,
        *,
        cache_root: Path | None = None,
        metrics=metrics_module,
        callbacks: ProjectCacheCallbacks | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._cache_root_override = cache_root
        self._metrics = metrics
        self._callbacks = callbacks or ProjectCacheCallbacks()
        self._logger = logger or logging.getLogger(__name__)

    def repo_path_for(self, gitlab_host: str, project_path: str) -> Path:
        root = ensure_cache_root(self._cache_root_override)
        slug = project_cache_slug(gitlab_host, project_path)
        return root / slug / "repo"

    def identifier_for(self, gitlab_host: str, project_path: str) -> str:
        return project_cache_identifier(gitlab_host, project_path)

    def bootstrap(
        self,
        *,
        gitlab_host: str,
        project_path: str,
        default_branch: str,
        gitlab_token: str | None = None,
        dry_run: bool = False,
        log_fn: Callable[[str], None] | None = None,
    ) -> Path:
        log = log_fn or self._logger.info
        ensure_cache_root(self._cache_root_override)

        branch = (default_branch or "").strip()
        if not branch:
            raise ProjectCacheError(
                "Project default branch is not configured; cannot bootstrap cache",
                reason="missing-default-branch",
            )

        repo_path = self.repo_path_for(gitlab_host, project_path)
        repo_path.parent.mkdir(parents=True, exist_ok=True)

        project_slug = project_cache_slug(gitlab_host, project_path)
        identifier = self.identifier_for(gitlab_host, project_path)
        operation = "bootstrap"
        start_time = time.perf_counter()
        commit_hash: str | None = None
        success = False

        env = project_cache_git_ops.git_env()
        askpass_path: Path | None = None

        try:
            with cache_operation_lock(repo_path, identifier=identifier, log_fn=log):
                if (repo_path / ".git").exists():
                    metadata = load_metadata(repo_path)
                    ensure_sentinel(repo_path, metadata, log_fn=log)
                    commit_hash = project_cache_git_ops.rev_parse_head(repo_path, env)
                    short_hash = commit_hash[:12]
                    log(
                        f"Project cache {identifier} already bootstrapped at {repo_path}; HEAD {branch}@{short_hash} ({commit_hash})",
                    )
                    success = True
                    return repo_path

                if dry_run:
                    log(
                        f"RUNNER_GIT_DRY_RUN=1 set; skipping initial clone for cache {identifier} at {repo_path}",
                    )
                    if not repo_path.exists():
                        repo_path.mkdir(parents=True, exist_ok=True)
                    metadata = load_metadata(repo_path)
                    ensure_sentinel(repo_path, metadata, log_fn=log)
                    success = True
                    return repo_path

                token = (gitlab_token or "").strip()
                if not token:
                    raise ProjectCacheError(
                        "GitLab PAT is required to bootstrap the project cache; store a PAT and retry",
                        reason="missing-token",
                    )

                remote_url = build_project_remote_url(gitlab_host, project_path, gitlab_token=token)
                env["GITLAB_TOKEN"] = token
                env.setdefault("GIT_USERNAME", "oauth2")

                askpass_path = project_cache_git_ops.create_askpass_helper()
                env["GIT_ASKPASS"] = str(askpass_path)
                log(f"Bootstrapping project cache {identifier} at {repo_path}")
                clone_start = time.perf_counter()
                clone_result = project_cache_git_ops.run_git_command(
                    [
                        "git",
                        "clone",
                        "--branch",
                        branch,
                        "--single-branch",
                        remote_url,
                        str(repo_path),
                    ],
                    repo_path.parent,
                    env,
                )
                clone_duration = time.perf_counter() - clone_start
                project_cache_git_ops.log_git_result(
                    log,
                    f"git clone {identifier}",
                    clone_result,
                    duration=clone_duration,
                )
                if clone_result.returncode != 0:
                    raise project_cache_git_ops.command_error(repo_path.parent, clone_result)

                commit_hash = project_cache_git_ops.rev_parse_head(repo_path, env)
                short_hash = commit_hash[:12]
                log(
                    f"Project cache {identifier} bootstrapped at {repo_path}; HEAD {branch}@{short_hash} ({commit_hash})",
                )
                metadata = load_metadata(repo_path)
                ensure_sentinel(repo_path, metadata, log_fn=log)
                success = True
                return repo_path
        except ProjectCacheError as exc:
            self._metrics.increment_operation_failure(operation, project_slug, reason=getattr(exc, "reason", "unknown"))
            raise
        except Exception:
            self._metrics.increment_operation_failure(operation, project_slug, reason="unexpected")
            raise
        finally:
            if askpass_path is not None:
                try:
                    askpass_path.unlink()
                except OSError:
                    self._logger.info("Failed to remove temporary askpass helper %s", askpass_path)

            duration = time.perf_counter() - start_time
            self._metrics.observe_operation_duration(operation, project_slug, dry_run=dry_run, seconds=duration)
            if success and commit_hash:
                self._metrics.set_cache_size(project_slug, project_cache_git_ops.directory_size_bytes(repo_path))

    def refresh(
        self,
        *,
        gitlab_host: str,
        project_path: str,
        default_branch: str,
        gitlab_token: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        log_fn: Callable[[str], None] | None = None,
        identifier_override: str | None = None,
    ) -> str:
        log = log_fn or self._logger.info
        repo_path = self.repo_path_for(gitlab_host, project_path)
        project_slug = project_cache_slug(gitlab_host, project_path)
        identifier = identifier_override or self.identifier_for(gitlab_host, project_path)
        operation = "refresh"
        start_time = time.perf_counter()
        commit_hash: str | None = None
        success = False

        env = project_cache_git_ops.git_env()
        if gitlab_token:
            env["GITLAB_TOKEN"] = gitlab_token
            env.setdefault("GIT_USERNAME", "oauth2")

        askpass_path: Path | None = None

        repo_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with cache_operation_lock(repo_path, identifier=identifier, log_fn=log):
                if not repo_path.exists():
                    raise ProjectCacheError(
                        (
                            f"Project cache missing at {repo_path}; run 'scripts/project_cache.py --refresh' to rebuild or delete the directory so the next task can bootstrap a fresh clone."
                        ),
                        reason="missing-cache",
                    )

                git_dir = repo_path / ".git"
                if not git_dir.exists():
                    if dry_run:
                        log(
                            f"RUNNER_GIT_DRY_RUN=1 set; skipping refresh for uninitialised cache at {repo_path}",
                        )
                        commit_hash = "dry-run-skip"
                        success = True
                        return commit_hash
                    raise ProjectCacheError(
                        (
                            f"Project cache at {repo_path} is not a git repository; run 'git fsck' to diagnose, execute 'scripts/project_cache.py --refresh' for automated repair, or delete the cache to allow a fresh bootstrap."
                        ),
                        reason="non-git-cache",
                    )

                branch = (default_branch or "").strip()
                if not branch:
                    raise ProjectCacheError(
                        "Project default branch is not configured; cannot refresh cache",
                        reason="missing-default-branch",
                    )

                metadata = load_metadata(repo_path)
                try:
                    validate_sentinel(repo_path, metadata)
                except ProjectCacheError as exc:
                    self._emit_breakout(identifier, repo_path, getattr(exc, "reason", "unknown"))
                    raise

                project_cache_git_ops.ensure_git_repository(repo_path, env)
                project_cache_git_ops.ensure_repository_integrity(repo_path, env, log, identifier)
                project_cache_git_ops.ensure_worktree_clean(
                    repo_path,
                    env,
                    allow_force=force,
                    dry_run=dry_run,
                    log_fn=log,
                    identifier=identifier,
                )

                remote_exists_flag = project_cache_git_ops.remote_exists(repo_path, env, "origin")

                if gitlab_token:
                    askpass_path = project_cache_git_ops.create_askpass_helper()
                    env["GIT_ASKPASS"] = str(askpass_path)

                remote_branch_exists_flag = False
                if remote_exists_flag:
                    if dry_run:
                        log(f"RUNNER_GIT_DRY_RUN=1 set; skipping git fetch origin {branch} for {identifier}")
                    else:
                        log(f"Fetching origin/{branch} for {identifier}")
                        fetch_start = time.perf_counter()
                        fetch_result = project_cache_git_ops.run_git_command(
                            ["git", "fetch", "--tags", "--force", "origin", branch],
                            repo_path,
                            env,
                        )
                        fetch_duration = time.perf_counter() - fetch_start
                        project_cache_git_ops.log_git_result(
                            log,
                            f"git fetch origin/{branch} for {identifier}",
                            fetch_result,
                            duration=fetch_duration,
                        )
                        if fetch_result.returncode != 0:
                            raise project_cache_git_ops.command_error(
                                repo_path,
                                fetch_result,
                                identifier=identifier,
                                branch=branch,
                            )
                    remote_branch_exists_flag = project_cache_git_ops.remote_branch_exists(repo_path, env, "origin", branch)
                else:
                    log(f"No origin remote configured for project cache at {repo_path}; skipping fetch")

                local_branch_exists = project_cache_git_ops.branch_exists(repo_path, env, branch)
                if not local_branch_exists:
                    if remote_branch_exists_flag and not dry_run:
                        log(f"Creating local branch {branch} from origin/{branch} for {identifier}")
                        checkout_start = time.perf_counter()
                        checkout_result = project_cache_git_ops.run_git_command(
                            ["git", "checkout", "-B", branch, f"origin/{branch}"],
                            repo_path,
                            env,
                        )
                        checkout_duration = time.perf_counter() - checkout_start
                        project_cache_git_ops.log_git_result(
                            log,
                            f"git checkout {branch}",
                            checkout_result,
                            duration=checkout_duration,
                        )
                        if checkout_result.returncode != 0:
                            raise project_cache_git_ops.command_error(
                                repo_path,
                                checkout_result,
                                identifier=identifier,
                                branch=branch,
                            )
                    elif not remote_branch_exists_flag:
                        log(f"Local branch {branch} not found and origin/{branch} missing for {identifier}")

                if not dry_run:
                    checkout_result = project_cache_git_ops.run_git_command(["git", "checkout", branch], repo_path, env)
                    if checkout_result.returncode != 0:
                        raise project_cache_git_ops.command_error(repo_path, checkout_result, identifier=identifier, branch=branch)

                    reset_result = project_cache_git_ops.run_git_command(["git", "reset", "--hard", f"origin/{branch}"], repo_path, env)
                    if reset_result.returncode != 0:
                        raise project_cache_git_ops.command_error(repo_path, reset_result, identifier=identifier, branch=branch)
                else:
                    log(f"RUNNER_GIT_DRY_RUN=1 set; skipping checkout/reset for {identifier}")

                if project_cache_git_ops.repository_has_submodules(repo_path):
                    if dry_run:
                        log("RUNNER_GIT_DRY_RUN=1 set; would update submodules recursively")
                    else:
                        log(f"Updating submodules recursively for {identifier}")
                        submodule_start = time.perf_counter()
                        submodule_result = project_cache_git_ops.run_git_command(
                            ["git", "submodule", "update", "--init", "--recursive"],
                            repo_path,
                            env,
                        )
                        submodule_duration = time.perf_counter() - submodule_start
                        project_cache_git_ops.log_git_result(
                            log,
                            "git submodule update --init --recursive",
                            submodule_result,
                            duration=submodule_duration,
                        )
                        if submodule_result.returncode != 0:
                            raise project_cache_git_ops.command_error(
                                repo_path,
                                submodule_result,
                                identifier=identifier,
                                branch=branch,
                            )

                if project_cache_git_ops.repository_uses_lfs(repo_path, env):
                    if shutil.which("git-lfs") is None:
                        raise ProjectCacheError(
                            "Git LFS is required to refresh cache assets but 'git-lfs' was not found on PATH; install Git LFS and retry",
                            reason="git-lfs-missing",
                        )
                    if dry_run:
                        log("RUNNER_GIT_DRY_RUN=1 set; skipping git lfs fetch/checkout")
                    else:
                        log(f"Fetching Git LFS objects for {identifier}")
                        lfs_fetch_start = time.perf_counter()
                        lfs_fetch_result = project_cache_git_ops.run_git_command(["git", "lfs", "fetch"], repo_path, env)
                        lfs_fetch_duration = time.perf_counter() - lfs_fetch_start
                        project_cache_git_ops.log_git_result(
                            log,
                            f"git lfs fetch for {identifier}",
                            lfs_fetch_result,
                            duration=lfs_fetch_duration,
                        )
                        if lfs_fetch_result.returncode != 0:
                            raise project_cache_git_ops.command_error(
                                repo_path,
                                lfs_fetch_result,
                                identifier=identifier,
                                branch=branch,
                            )
                        log(f"Checking out Git LFS objects for {identifier}")
                        lfs_checkout_start = time.perf_counter()
                        lfs_checkout_result = project_cache_git_ops.run_git_command(["git", "lfs", "checkout"], repo_path, env)
                        lfs_checkout_duration = time.perf_counter() - lfs_checkout_start
                        project_cache_git_ops.log_git_result(
                            log,
                            f"git lfs checkout for {identifier}",
                            lfs_checkout_result,
                            duration=lfs_checkout_duration,
                        )
                        if lfs_checkout_result.returncode != 0:
                            raise project_cache_git_ops.command_error(
                                repo_path,
                                lfs_checkout_result,
                                identifier=identifier,
                                branch=branch,
                            )

                additional_branches = [
                    candidate
                    for candidate in project_cache_git_ops.configured_additional_branches()
                    if candidate and candidate != branch
                ]
                if additional_branches:
                    for extra_branch in additional_branches:
                        project_cache_git_ops.sync_additional_branch(
                            repo_path,
                            env,
                            extra_branch,
                            log_fn=log,
                            identifier=identifier,
                            dry_run=dry_run,
                        )

                project_cache_git_ops.ensure_worktree_clean(
                    repo_path,
                    env,
                    allow_force=False,
                    dry_run=dry_run,
                    log_fn=log,
                    identifier=identifier,
                )

                commit_hash = project_cache_git_ops.rev_parse_head(repo_path, env)
                short_hash = commit_hash[:12]
                log(f"Project cache synced to {branch}@{short_hash} ({commit_hash}) for {identifier}")
                success = True
                return commit_hash
        except ProjectCacheError as exc:
            self._metrics.increment_operation_failure(operation, project_slug, reason=getattr(exc, "reason", "unknown"))
            raise
        except Exception:
            self._metrics.increment_operation_failure(operation, project_slug, reason="unexpected")
            raise
        finally:
            if askpass_path is not None:
                try:
                    askpass_path.unlink()
                except OSError:
                    self._logger.info("Failed to remove temporary askpass helper %s", askpass_path)

            duration = time.perf_counter() - start_time
            self._metrics.observe_operation_duration(operation, project_slug, dry_run=dry_run, seconds=duration)
            if success and commit_hash not in {None, "dry-run-skip"}:
                self._metrics.set_cache_size(project_slug, project_cache_git_ops.directory_size_bytes(repo_path))
                if self._callbacks.on_refresh_complete:
                    try:
                        self._callbacks.on_refresh_complete(
                            RefreshEvent(
                                identifier=identifier,
                                commit_hash=commit_hash,
                                duration_seconds=duration,
                                dry_run=dry_run,
                            )
                        )
                    except Exception:  # pragma: no cover - callbacks should not break main flow
                        self._logger.exception("Refresh callback failed for %s", identifier)

        return commit_hash or ""

    def enforce_policy(
        self,
        *,
        gitlab_host: str,
        project_path: str,
        quota_mb: int | None,
        prune_after_hours: int | None,
        dry_run: bool,
        log_fn: Callable[[str], None] | None = None,
    ) -> PolicyOutcome:
        log = log_fn or self._logger.info
        outcome = enforce_policy(
            self.repo_path_for(gitlab_host, project_path),
            quota_mb=quota_mb,
            prune_after_hours=prune_after_hours,
            dry_run=dry_run,
            log_fn=log,
        )
        return outcome

    def snapshot(
        self,
        *,
        gitlab_host: str,
        project_path: str,
        commit_hash: str,
        branch: str,
        dry_run: bool,
        log_fn: Callable[[str], None] | None = None,
        retention_hours: int | None = None,
        max_snapshots: int | None = None,
    ) -> SnapshotOutcome:
        log = log_fn or self._logger.info
        repo_path = self.repo_path_for(gitlab_host, project_path)
        outcome = create_snapshot(
            repo_path,
            commit_hash=commit_hash,
            branch=branch,
            dry_run=dry_run,
            log_fn=log,
            retention_hours=retention_hours,
            max_snapshots=max_snapshots,
        )

        metadata = outcome.metadata
        snapshots = metadata.get("snapshots")
        project_slug = project_cache_slug(gitlab_host, project_path)
        count = len(snapshots) if isinstance(snapshots, list) else 0
        self._metrics.set_snapshot_count(project_slug, count)

        if outcome.removed_paths and self._callbacks.on_snapshot_pruned:
            for removed in outcome.removed_paths:
                try:
                    self._callbacks.on_snapshot_pruned(
                        SnapshotPrunedEvent(
                            identifier=self.identifier_for(gitlab_host, project_path),
                            removed_path=removed,
                        )
                    )
                except Exception:  # pragma: no cover - callback hygiene
                    self._logger.exception("Snapshot prune callback failed for %s", removed)

        return outcome

    def _emit_breakout(self, identifier: str, repo_path: Path, reason: str) -> None:
        callback = self._callbacks.on_breakout_detected
        if callback is None:
            return
        try:
            callback(BreakoutEvent(identifier=identifier, repo_path=repo_path, reason=reason))
        except Exception:  # pragma: no cover - callback hygiene
            self._logger.exception("Breakout callback failed for %s", identifier)


__all__ = [
    "BreakoutEvent",
    "ProjectCacheCallbacks",
    "ProjectCacheService",
    "RefreshEvent",
    "SnapshotPrunedEvent",
]
