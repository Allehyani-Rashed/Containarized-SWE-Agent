from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse, urlunparse


from . import metrics

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9._-]+")
_OAUTH_TOKEN_PATTERN = re.compile(r"(oauth2:)([^@]+)(@)", re.IGNORECASE)

_CACHE_METADATA_FILENAME = "cache-metadata.json"
_SNAPSHOT_DIRNAME = "snapshots"
_DEFAULT_SNAPSHOT_RETENTION_HOURS = 168  # one week
_DEFAULT_SNAPSHOT_LIMIT = 20

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cache_metadata_path(repo_path: Path) -> Path:
    return repo_path.parent / _CACHE_METADATA_FILENAME


def _load_cache_metadata(repo_path: Path) -> dict[str, Any]:
    metadata_path = _cache_metadata_path(repo_path)
    try:
        raw = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    try:
        loaded = json.loads(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _write_cache_metadata(repo_path: Path, metadata: dict[str, Any]) -> None:
    metadata_path = _cache_metadata_path(repo_path)
    try:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    except OSError:
        logger.info("Failed to persist cache metadata at %s", metadata_path)


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _configured_additional_branches() -> list[str]:
    configured = os.environ.get("PROJECT_CACHE_ADDITIONAL_BRANCHES", "")
    branches = [branch.strip() for branch in configured.split(",") if branch.strip()]
    deduped: list[str] = []
    for branch in branches:
        if branch not in deduped:
            deduped.append(branch)
    return deduped


def get_cache_root() -> Path:
    """Return the root directory that stores project cache clones."""

    override = os.environ.get("PROJECT_CACHE_ROOT")
    if override:
        return Path(override).expanduser()
    return _project_root() / "project-cache"


def ensure_cache_root(cache_root: Path | None = None) -> Path:
    """Ensure the cache root exists and return the expanded path."""

    root = (cache_root or get_cache_root()).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalise_segment(value: str) -> str:
    segment = value.strip().lower().replace("/", "-")
    segment = _NON_SLUG_CHARS.sub("-", segment)
    return segment.strip("-")


def project_cache_slug(gitlab_host: str, project_path: str) -> str:
    """Create a deterministic slug for a GitLab project."""

    host_segment = _normalise_segment(gitlab_host or "")
    path_segment = _normalise_segment(project_path or "")
    parts = [part for part in (host_segment, path_segment) if part]
    slug = "-".join(parts) or "project"
    return re.sub(r"-+", "-", slug)


def project_cache_repo_path(gitlab_host: str, project_path: str) -> Path:
    """Return the directory where the canonical clone for a project lives."""

    return get_cache_root() / project_cache_slug(gitlab_host, project_path) / "repo"


def project_cache_identifier(gitlab_host: str, project_path: str) -> str:
    """Return a human-readable identifier for logging and metrics."""

    host = (gitlab_host or "").strip().rstrip("/")
    path = (project_path or "").strip().strip("/")
    if host and path:
        return f"{host}/{path}"
    if host:
        return host
    if path:
        return path
    return "<unknown-project>"


class ProjectCacheError(RuntimeError):
    """Raised when a project cache cannot be safely refreshed."""

    def __init__(self, message: str, *, reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason


def build_project_remote_url(
    gitlab_host: str,
    project_path: str,
    *,
    gitlab_token: str | None = None,
) -> str:
    host = (gitlab_host or "").strip()
    path = (project_path or "").strip().strip("/")
    if not host or not path:
        raise ProjectCacheError(
            "GitLab host and project path must be configured to bootstrap the cache",
            reason="missing-project",
        )

    parsed_host = urlparse(host)
    if not parsed_host.scheme:
        host = f"https://{host.lstrip('/')}"
        parsed_host = urlparse(host)
        if not parsed_host.scheme:
            raise ProjectCacheError(
                f"Unable to determine scheme for GitLab host '{gitlab_host}'",
                reason="invalid-host",
            )

    base_path = path if path.endswith(".git") else f"{path}.git"
    base_url = urlunparse(
        (
            parsed_host.scheme,
            parsed_host.netloc,
            "/" + base_path.lstrip("/"),
            "",
            "",
            "",
        ),
    )

    if not gitlab_token:
        return base_url

    quoted = quote(gitlab_token, safe="")
    netloc = f"oauth2:{quoted}@{parsed_host.netloc}"
    return urlunparse(
        (
            parsed_host.scheme,
            netloc,
            "/" + base_path.lstrip("/"),
            "",
            "",
            "",
        ),
    )


def bootstrap_project_cache(
    cache_path: Path,
    *,
    gitlab_host: str,
    gitlab_project_path: str,
    default_branch: str,
    gitlab_token: str | None = None,
    dry_run: bool = False,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """Ensure a cache repository exists by cloning it when missing."""

    log = log_fn or logger.info
    ensure_cache_root()

    branch = (default_branch or "").strip()
    if not branch:
        raise ProjectCacheError(
            "Project default branch is not configured; cannot bootstrap cache",
            reason="missing-default-branch",
        )

    repo_path = cache_path.expanduser()
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    project_slug = project_cache_slug(gitlab_host, gitlab_project_path)
    identifier = project_cache_identifier(gitlab_host, gitlab_project_path)
    operation = "bootstrap"
    start_time = time.perf_counter()
    commit_hash: str | None = None
    success = False

    log(f"Bootstrap requested for project cache {identifier} at {repo_path}")

    env = _git_env()
    askpass_path: Path | None = None

    try:
        if (repo_path / ".git").exists():
            try:
                commit_hash = _rev_parse_head(repo_path, env)
                short_hash = commit_hash[:12]
                log(
                    f"Project cache {identifier} already bootstrapped at {repo_path}; HEAD {branch}@{short_hash} ({commit_hash})",
                )
            except ProjectCacheError:
                raise
            else:
                success = True
                return

        if dry_run:
            log(
                f"RUNNER_GIT_DRY_RUN=1 set; skipping initial clone for cache {identifier} at {repo_path}",
            )
            if not repo_path.exists():
                repo_path.mkdir(parents=True, exist_ok=True)
            success = True
            return

        token = (gitlab_token or "").strip()
        if not token:
            raise ProjectCacheError(
                "GitLab PAT is required to bootstrap the project cache; store a PAT and retry",
                reason="missing-token",
            )

        remote_url = build_project_remote_url(gitlab_host, gitlab_project_path, gitlab_token=token)
        env["GITLAB_TOKEN"] = token
        env.setdefault("GIT_USERNAME", "oauth2")

        askpass_path = _create_askpass_helper()
        env["GIT_ASKPASS"] = str(askpass_path)
        log(f"Bootstrapping project cache {identifier} at {repo_path}")
        clone_result = subprocess.run(
            [
                "git",
                "clone",
                "--branch",
                branch,
                "--single-branch",
                remote_url,
                str(repo_path),
            ],
            cwd=str(repo_path.parent),
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if clone_result.returncode != 0:
            raise _command_error(repo_path.parent, clone_result)

        commit_hash = _rev_parse_head(repo_path, env)
        short_hash = commit_hash[:12]
        log(
            f"Project cache {identifier} bootstrapped at {repo_path}; HEAD {branch}@{short_hash} ({commit_hash})",
        )
        success = True
    except ProjectCacheError as exc:
        metrics.increment_operation_failure(operation, project_slug, reason=getattr(exc, "reason", "unknown"))
        raise
    except Exception:
        metrics.increment_operation_failure(operation, project_slug, reason="unexpected")
        raise
    finally:
        if askpass_path is not None:
            try:
                askpass_path.unlink()
            except OSError:
                logger.info("Failed to remove temporary askpass helper %s", askpass_path)

        duration = time.perf_counter() - start_time
        metrics.observe_operation_duration(operation, project_slug, dry_run=dry_run, seconds=duration)
        if success and commit_hash:
            metrics.set_cache_size(project_slug, _directory_size_bytes(repo_path))


def refresh_project_cache(
    project_root: Path,
    default_branch: str,
    *,
    gitlab_token: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    log_fn: Callable[[str], None] | None = None,
    project_identifier: str | None = None,
) -> str:
    """Ensure the project cache is clean and aligned to the default branch.

    Returns the HEAD commit hash after refresh. Raises ProjectCacheError if the
    cache is missing, not a git repository, dirty, or cannot be synced.
    """

    log = log_fn or logger.info
    repo_path = project_root.expanduser().resolve()
    project_slug = repo_path.parent.name or repo_path.name
    identifier = project_identifier or project_slug
    operation = "refresh"
    start_time = time.perf_counter()
    commit_hash: str | None = None
    success = False

    env = _git_env()
    if gitlab_token:
        env["GITLAB_TOKEN"] = gitlab_token
        env.setdefault("GIT_USERNAME", "oauth2")

    askpass_path: Path | None = None

    try:
        if not repo_path.exists():
            raise ProjectCacheError(
                (
                    f"Project cache missing at {repo_path}; run 'scripts/project_cache.py --refresh' to rebuild "
                    "or delete the directory so the next task can bootstrap a fresh clone."
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
                    f"Project cache at {repo_path} is not a git repository; run 'git fsck' to diagnose, execute "
                    "'scripts/project_cache.py --refresh' for automated repair, or delete the cache to allow a fresh bootstrap."
                ),
                reason="non-git-cache",
            )

        branch = (default_branch or "").strip()
        if not branch:
            raise ProjectCacheError(
                "Project default branch is not configured; cannot refresh cache",
                reason="missing-default-branch",
            )

        _ensure_git_repository(repo_path, env)
        _ensure_repository_integrity(repo_path, env, log, identifier)
        _ensure_worktree_clean(
            repo_path,
            env,
            allow_force=force,
            dry_run=dry_run,
            log_fn=log,
            identifier=identifier,
        )

        remote_exists = _remote_exists(repo_path, env, "origin")

        if gitlab_token:
            askpass_path = _create_askpass_helper()
            env["GIT_ASKPASS"] = str(askpass_path)

        remote_branch_exists = False
        if remote_exists:
            if dry_run:
                log(f"RUNNER_GIT_DRY_RUN=1 set; skipping git fetch origin {branch} for {identifier}")
            else:
                log(f"Fetching origin/{branch} for {identifier}")
                fetch_result = _run_git_command(
                    ["git", "fetch", "--tags", "--force", "origin", branch],
                    repo_path,
                    env,
                )
                if fetch_result.returncode != 0:
                    raise _command_error(
                        repo_path,
                        fetch_result,
                        identifier=identifier,
                        branch=branch,
                    )
            remote_branch_exists = _remote_branch_exists(repo_path, env, "origin", branch)
        else:
            log(f"No origin remote configured for project cache at {repo_path}; skipping fetch")

        local_branch_exists = _branch_exists(repo_path, env, branch)
        if not local_branch_exists:
            if remote_branch_exists and not dry_run:
                log(f"Creating local branch {branch} from origin/{branch} for {identifier}")
                checkout_result = _run_git_command(
                    ["git", "checkout", "-B", branch, f"origin/{branch}"],
                    repo_path,
                    env,
                )
                if checkout_result.returncode != 0:
                    raise _command_error(
                        repo_path,
                        checkout_result,
                        identifier=identifier,
                        branch=branch,
                    )
                local_branch_exists = True
            else:
                if remote_branch_exists:
                    message = (
                        f"Project cache at {repo_path} is missing local branch '{branch}' while origin/{branch} exists. "
                        f"Run 'git checkout -B {branch} origin/{branch}' and retry."
                    )
                elif remote_exists:
                    message = (
                        f"Origin remote configured for cache at {repo_path} but branch origin/{branch} is missing. "
                        "Update the project default branch or ensure it exists upstream."
                    )
                else:
                    message = (
                        f"Project cache at {repo_path} is missing local branch '{branch}'. Configure the branch before running tasks."
                    )
                raise ProjectCacheError(message, reason="missing-local-branch")

        log(f"Checking out {branch} for {identifier}")
        checkout_result = _run_git_command(["git", "checkout", branch], repo_path, env)
        if checkout_result.returncode != 0:
            raise _command_error(
                repo_path,
                checkout_result,
                identifier=identifier,
                branch=branch,
            )

        if remote_exists and remote_branch_exists:
            if dry_run:
                log(f"RUNNER_GIT_DRY_RUN=1 set; would reset {branch} to origin/{branch} for {identifier}")
            else:
                log(f"Resetting {branch} to origin/{branch} for {identifier}")
                reset_result = _run_git_command(
                    ["git", "reset", "--hard", f"origin/{branch}"],
                    repo_path,
                    env,
                )
                if reset_result.returncode != 0:
                    raise _command_error(
                        repo_path,
                        reset_result,
                        identifier=identifier,
                        branch=branch,
                    )
        elif remote_exists:
            raise ProjectCacheError(
                f"Origin remote configured but branch origin/{branch} missing for cache at {repo_path}; fetch the branch and retry",
                reason="missing-remote-branch",
            )

        if _repository_has_submodules(repo_path):
            if dry_run:
                log("RUNNER_GIT_DRY_RUN=1 set; skipping git submodule update --init --recursive")
            else:
                log(f"Updating git submodules recursively for {identifier}")
                submodule_result = _run_git_command(
                    ["git", "submodule", "update", "--init", "--recursive"],
                    repo_path,
                    env,
                )
                if submodule_result.returncode != 0:
                    raise _command_error(
                        repo_path,
                        submodule_result,
                        identifier=identifier,
                        branch=branch,
                    )

        if _repository_uses_lfs(repo_path, env):
            if shutil.which("git-lfs") is None:
                raise ProjectCacheError(
                    "Git LFS is required to refresh cache assets but 'git-lfs' was not found on PATH; install Git LFS and retry",
                    reason="git-lfs-missing",
                )
            if dry_run:
                log("RUNNER_GIT_DRY_RUN=1 set; skipping git lfs fetch/checkout")
            else:
                log(f"Fetching Git LFS objects for {identifier}")
                lfs_fetch_result = _run_git_command(["git", "lfs", "fetch"], repo_path, env)
                if lfs_fetch_result.returncode != 0:
                    raise _command_error(
                        repo_path,
                        lfs_fetch_result,
                        identifier=identifier,
                        branch=branch,
                    )
                log(f"Checking out Git LFS objects for {identifier}")
                lfs_checkout_result = _run_git_command(["git", "lfs", "checkout"], repo_path, env)
                if lfs_checkout_result.returncode != 0:
                    raise _command_error(
                        repo_path,
                        lfs_checkout_result,
                        identifier=identifier,
                        branch=branch,
                    )

        additional_branches = [
            candidate
            for candidate in _configured_additional_branches()
            if candidate and candidate != branch
        ]
        if additional_branches:
            for extra_branch in additional_branches:
                _sync_additional_branch(
                    repo_path,
                    env,
                    extra_branch,
                    log_fn=log,
                    identifier=identifier,
                    dry_run=dry_run,
                )

        _ensure_worktree_clean(
            repo_path,
            env,
            allow_force=False,
            dry_run=dry_run,
            log_fn=log,
            identifier=identifier,
        )

        commit_hash = _rev_parse_head(repo_path, env)
        short_hash = commit_hash[:12]
        log(f"Project cache {identifier} synced to {branch}@{short_hash} ({commit_hash})")
        success = True
        return commit_hash
    except ProjectCacheError as exc:
        metrics.increment_operation_failure(operation, project_slug, reason=getattr(exc, "reason", "unknown"))
        raise
    except Exception:
        metrics.increment_operation_failure(operation, project_slug, reason="unexpected")
        raise
    finally:
        if askpass_path is not None:
            try:
                askpass_path.unlink()
            except OSError:
                logger.info("Failed to remove temporary askpass helper %s", askpass_path)

        duration = time.perf_counter() - start_time
        metrics.observe_operation_duration(operation, project_slug, dry_run=dry_run, seconds=duration)
        if success and commit_hash not in {None, "dry-run-skip"}:
            metrics.set_cache_size(project_slug, _directory_size_bytes(repo_path))


def enforce_cache_policy(
    project_root: Path,
    *,
    quota_mb: int | None,
    prune_after_hours: int | None,
    dry_run: bool = False,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """Enforce per-project cache retention policies (quota + pruning)."""

    log = log_fn or logger.info
    repo_path = project_root.expanduser().resolve()
    if not repo_path.exists():
        log(f"Cache path {repo_path} missing; skipping policy enforcement")
        return
    metadata = _load_cache_metadata(repo_path)
    now = datetime.now(timezone.utc)

    env = _git_env()

    last_pruned_at = _parse_iso8601(metadata.get("last_pruned_at")) if isinstance(metadata, dict) else None
    prune_due = False
    if isinstance(prune_after_hours, int) and prune_after_hours > 0:
        cutoff = now - timedelta(hours=prune_after_hours)
        if last_pruned_at is None or last_pruned_at < cutoff:
            prune_due = True

    if prune_due:
        if dry_run:
            log(
                f"RUNNER_GIT_DRY_RUN=1 set; would run 'git gc --prune=now --aggressive' for cache at {repo_path}",
            )
        else:
            log(f"Running git gc --prune=now --aggressive for cache at {repo_path}")
            gc_result = _run_git_command(
                ["git", "gc", "--prune=now", "--aggressive"],
                repo_path,
                env,
            )
            if gc_result.returncode != 0:
                raise _command_error(repo_path, gc_result, identifier=str(repo_path))
            metadata["last_pruned_at"] = now.isoformat()

    size_bytes = _directory_size_bytes(repo_path)
    metadata["last_recorded_size_bytes"] = size_bytes
    metadata["last_refreshed_at"] = now.isoformat()

    if isinstance(quota_mb, int) and quota_mb > 0:
        quota_bytes = quota_mb * 1024 * 1024
        if size_bytes > quota_bytes:
            if dry_run:
                log(
                    f"RUNNER_GIT_DRY_RUN=1 set; cache size {size_bytes / (1024 * 1024):.2f} MB exceeds quota {quota_mb} MB",
                )
            else:
                if not prune_due:
                    log(
                        f"Cache size {size_bytes / (1024 * 1024):.2f} MB exceeds quota {quota_mb} MB; running git gc --prune=now",
                    )
                    gc_result = _run_git_command(
                        ["git", "gc", "--prune=now"],
                        repo_path,
                        env,
                    )
                    if gc_result.returncode != 0:
                        raise _command_error(repo_path, gc_result, identifier=str(repo_path))
                    metadata["last_pruned_at"] = now.isoformat()
                    size_bytes = _directory_size_bytes(repo_path)
                    metadata["last_recorded_size_bytes"] = size_bytes
                if size_bytes > quota_bytes:
                    raise ProjectCacheError(
                        (
                            f"Cache at {repo_path} remains above quota after pruning ({size_bytes / (1024 * 1024):.2f} MB > {quota_mb} MB). "
                            "Increase the project quota, clear the cache directory, or move large assets (such as Git LFS) to alternative storage."
                        ),
                        reason="cache-quota-exceeded",
                    )

    if not dry_run:
        _write_cache_metadata(repo_path, metadata)


def snapshot_project_cache(
    project_root: Path,
    *,
    commit_hash: str,
    branch: str,
    dry_run: bool = False,
    log_fn: Callable[[str], None] | None = None,
    retention_hours: int | None = None,
    max_snapshots: int | None = None,
) -> Path | None:
    """Create a git bundle snapshot of the cache for auditability."""

    if not commit_hash or commit_hash == "dry-run-skip":
        return None

    log = log_fn or logger.info
    repo_path = project_root.expanduser().resolve()

    enabled_env = os.environ.get("PROJECT_CACHE_SNAPSHOT_ENABLED")
    if enabled_env is not None and not _is_truthy(enabled_env):
        log("Project cache snapshots disabled via PROJECT_CACHE_SNAPSHOT_ENABLED")
        return None

    retention_env = os.environ.get("PROJECT_CACHE_SNAPSHOT_RETENTION_HOURS")
    limit_env = os.environ.get("PROJECT_CACHE_MAX_SNAPSHOTS")

    retention = (
        int(retention_env)
        if retention_env and retention_env.strip().isdigit()
        else _DEFAULT_SNAPSHOT_RETENTION_HOURS
    )
    if retention_hours is not None:
        retention = retention_hours
    limit = (
        int(limit_env)
        if limit_env and limit_env.strip().isdigit()
        else _DEFAULT_SNAPSHOT_LIMIT
    )
    if max_snapshots is not None:
        limit = max_snapshots

    now = datetime.now(timezone.utc)
    snapshot_dir = repo_path.parent / _SNAPSHOT_DIRNAME
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    safe_branch = branch.replace(os.sep, "-") if branch else "branch"
    filename = f"{timestamp}-{safe_branch}-{commit_hash[:12]}.bundle"
    snapshot_path = snapshot_dir / filename

    if dry_run:
        log(f"RUNNER_GIT_DRY_RUN=1 set; would create cache snapshot at {snapshot_path}")
        return snapshot_path

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    env = _git_env()
    log(f"Creating cache snapshot bundle at {snapshot_path}")
    bundle_result = _run_git_command(
        ["git", "bundle", "create", str(snapshot_path), "HEAD"],
        repo_path,
        env,
    )
    if bundle_result.returncode != 0:
        raise _command_error(repo_path, bundle_result, identifier=str(repo_path))

    metadata = _load_cache_metadata(repo_path)
    snapshots: list[dict[str, Any]] = []
    if isinstance(metadata.get("snapshots"), list):
        snapshots = [snapshot for snapshot in metadata["snapshots"] if isinstance(snapshot, dict)]

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
        created_at = _parse_iso8601(snapshot.get("created_at"))
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
    if not dry_run:
        _write_cache_metadata(repo_path, metadata)

    project_slug = repo_path.parent.name or repo_path.name
    metrics.set_snapshot_count(project_slug, len(snapshots))

    return snapshot_path


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


def _run_git_command(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError) as exc:
        raise ProjectCacheError(
            f"git command {' '.join(args)} failed in {cwd}: {exc}",
            reason="git-command-error",
        ) from exc


def _command_error(
    cwd: Path,
    result: subprocess.CompletedProcess,
    *,
    identifier: str | None = None,
    branch: str | None = None,
) -> ProjectCacheError:
    stdout = _scrub_sensitive_data(result.stdout.decode("utf-8", errors="ignore").strip())
    stderr = _scrub_sensitive_data(result.stderr.decode("utf-8", errors="ignore").strip())
    details = stderr or stdout or "unknown error"
    if isinstance(result.args, (list, tuple)):
        command = " ".join(str(part) for part in result.args)
    else:
        command = str(result.args)
    command = _scrub_sensitive_data(command)
    friendly = _friendly_git_error(cwd, command, details, result.returncode, identifier=identifier, branch=branch)
    if friendly:
        return ProjectCacheError(friendly, reason="git-command-error")
    return ProjectCacheError(
        f"git command '{command}' failed in {cwd} (exit {result.returncode}): {details}",
        reason="git-command-error",
    )


def _ensure_git_repository(repo_path: Path, env: dict[str, str]) -> None:
    result = _run_git_command([
        "git",
        "rev-parse",
        "--is-inside-work-tree",
    ], repo_path, env)
    if result.returncode != 0 or result.stdout.strip().lower() != b"true":
        raise ProjectCacheError(
            (
                f"Project cache at {repo_path} is not a git repository; run 'git fsck' for details, "
                "repair with 'scripts/project_cache.py --refresh', or remove the cache so it can be bootstrapped again."
            ),
            reason="non-git-cache",
        )


def _ensure_worktree_clean(
    repo_path: Path,
    env: dict[str, str],
    *,
    allow_force: bool,
    dry_run: bool,
    log_fn: Callable[[str], None] | None,
    identifier: str,
) -> None:
    status_result = _run_git_command(["git", "status", "--porcelain"], repo_path, env)
    if status_result.returncode != 0:
        raise _command_error(repo_path, status_result, identifier=identifier)
    if status_result.stdout.strip():
        if not allow_force:
            raise ProjectCacheError(
                (
                    f"Project cache at {repo_path} has uncommitted changes; exit without modifying the cache. "
                    "Re-run with '--force' (scripts/project_cache.py --refresh --force) to discard local edits after backing them up."
                ),
                reason="dirty-worktree",
            )
        message_prefix = f"Force refresh requested for {identifier}"
        if dry_run:
            if log_fn:
                log_fn(f"RUNNER_GIT_DRY_RUN=1 set; would discard uncommitted changes for {identifier}")
            return
        if log_fn:
            log_fn(f"{message_prefix}; discarding uncommitted changes")
        reset_result = _run_git_command(["git", "reset", "--hard"], repo_path, env)
        if reset_result.returncode != 0:
            raise _command_error(repo_path, reset_result, identifier=identifier)
        clean_result = _run_git_command(["git", "clean", "-fd"], repo_path, env)
        if clean_result.returncode != 0:
            raise _command_error(repo_path, clean_result, identifier=identifier)
        status_after = _run_git_command(["git", "status", "--porcelain"], repo_path, env)
        if status_after.returncode != 0:
            raise _command_error(repo_path, status_after, identifier=identifier)
        if status_after.stdout.strip():
            raise ProjectCacheError(
                (
                    f"Project cache at {repo_path} could not be cleaned automatically; inspect the repository manually or delete the cache before retrying."
                ),
                reason="dirty-worktree",
            )


def _remote_exists(repo_path: Path, env: dict[str, str], remote: str) -> bool:
    remotes_result = _run_git_command(["git", "remote"], repo_path, env)
    if remotes_result.returncode != 0:
        raise _command_error(repo_path, remotes_result)
    remotes = {
        entry.strip()
        for entry in remotes_result.stdout.decode("utf-8", errors="ignore").splitlines()
        if entry.strip()
    }
    return remote in remotes


def _branch_exists(repo_path: Path, env: dict[str, str], branch: str) -> bool:
    result = _run_git_command(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        repo_path,
        env,
    )
    return result.returncode == 0


def _remote_branch_exists(repo_path: Path, env: dict[str, str], remote: str, branch: str) -> bool:
    result = _run_git_command(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"],
        repo_path,
        env,
    )
    return result.returncode == 0


def _rev_parse_head(repo_path: Path, env: dict[str, str]) -> str:
    result = _run_git_command(["git", "rev-parse", "HEAD"], repo_path, env)
    if result.returncode != 0:
        raise _command_error(repo_path, result)
    return result.stdout.decode("utf-8", errors="ignore").strip()


def _directory_size_bytes(path: Path) -> int:
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += _directory_size_bytes(Path(entry.path))
                    else:
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _create_askpass_helper() -> Path:
    fd, path_str = tempfile.mkstemp(prefix="codex-cache-askpass-", suffix=".sh")
    path = Path(path_str)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("#!/usr/bin/env bash\n")
        handle.write("printf '%s' \"${GITLAB_TOKEN}\"\n")
    path.chmod(0o700)
    return path


def _repository_has_submodules(repo_path: Path) -> bool:
    gitmodules_path = repo_path / ".gitmodules"
    if not gitmodules_path.exists():
        return False
    try:
        content = gitmodules_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(content.strip())


def _repository_uses_lfs(repo_path: Path, env: dict[str, str]) -> bool:
    attributes_result = _run_git_command(["git", "ls-files", "-z", "*.gitattributes"], repo_path, env)
    if attributes_result.returncode != 0:
        return False
    output = attributes_result.stdout.decode("utf-8", errors="ignore")
    for relative_path in (entry for entry in output.split("\0") if entry):
        candidate = repo_path / relative_path
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if "filter=lfs" in text:
            return True
    return False


def _sync_additional_branch(
    repo_path: Path,
    env: dict[str, str],
    branch: str,
    *,
    log_fn: Callable[[str], None],
    identifier: str,
    dry_run: bool,
) -> None:
    if dry_run:
        log_fn(f"RUNNER_GIT_DRY_RUN=1 set; would fetch origin/{branch} for {identifier}")
        return

    fetch_result = _run_git_command([
        "git",
        "fetch",
        "--tags",
        "--force",
        "origin",
        branch,
    ], repo_path, env)
    if fetch_result.returncode != 0:
        raise _command_error(repo_path, fetch_result, identifier=identifier, branch=branch)
    log_fn(f"Fetched origin/{branch} while refreshing cache {identifier}")

    if not _branch_exists(repo_path, env, branch):
        checkout_result = _run_git_command([
            "git",
            "branch",
            branch,
            f"origin/{branch}",
        ], repo_path, env)
        if checkout_result.returncode != 0:
            raise _command_error(repo_path, checkout_result, identifier=identifier, branch=branch)
        log_fn(f"Created local tracking branch {branch} for cache {identifier}")


def _friendly_git_error(
    cwd: Path,
    command: str,
    details: str,
    returncode: int,
    *,
    identifier: str | None = None,
    branch: str | None = None,
) -> str | None:
    detail_lower = details.lower()
    if any(phrase in detail_lower for phrase in ("authentication failed", "access denied", "could not read username")):
        context = []
        if identifier:
            context.append(f"for {identifier}")
        if branch:
            context.append(f"while syncing branch '{branch}'")
        context_suffix = f" ({' '.join(context)})" if context else ""
        return (
            f"Git authentication failed{context_suffix} while running '{command}' in {cwd}: {details}. "
            "Verify the stored PAT via POST /integrations/pat/verify (Settings → Integrations → Verify PAT) or rerun 'scripts/codex pat store'."
        )
    if "couldn't find remote ref" in detail_lower or "could not find remote ref" in detail_lower:
        branch = None
        for part in command.split():
            if part.startswith("origin/"):
                branch = part
                break
        missing_ref = branch or "Requested remote reference"
        return (
            f"{missing_ref} not found while refreshing project cache at {cwd}: {details}. "
            "Ensure the project default branch exists upstream, update the project metadata, or re-bootstrap the cache before retrying."
        )
    if "repository not found" in detail_lower:
        return (
            f"Git repository not found while running '{command}' in {cwd}: {details}. "
            "Confirm the GitLab host, project path, and PAT permissions."
        )
    if returncode == 128 and "fatal" in detail_lower and "could not read from remote repository" in detail_lower:
        return (
            f"Unable to read from remote repository while running '{command}' in {cwd}: {details}. "
            "Check network access and validate the stored credentials."
        )
    return None


def _ensure_repository_integrity(
    repo_path: Path,
    env: dict[str, str],
    log_fn: Callable[[str], None],
    identifier: str,
) -> None:
    fsck_result = _run_git_command(["git", "fsck", "--no-dangling"], repo_path, env)
    if fsck_result.returncode != 0:
        details = fsck_result.stderr.decode("utf-8", errors="ignore").strip() or fsck_result.stdout.decode("utf-8", errors="ignore").strip()
        log_fn(
            f"git fsck reported issues for {identifier}: {details or 'unknown error'}",
        )
        raise ProjectCacheError(
            (
                f"Project cache at {repo_path} appears corrupted; run 'git fsck' for details, execute 'scripts/project_cache.py --refresh' "
                "to attempt repair, or delete the cache directory before retrying."
            ),
            reason="corrupted-cache",
        )


def _scrub_sensitive_data(value: str) -> str:
    if not value:
        return value
    sanitized = _OAUTH_TOKEN_PATTERN.sub(r"\1<redacted>\3", value)
    return sanitized
