"""Git helper utilities consumed by project cache workflows."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable
import re

from .errors import ProjectCacheError

logger = logging.getLogger(__name__)

MAX_GIT_LOG_CHARS = 512
OAUTH_TOKEN_PATTERN = re.compile(r"(oauth2:)([^@]+)(@)", re.IGNORECASE)


def git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


def run_git_command(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
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


def log_git_result(
    log: Callable[[str], None],
    description: str,
    result: subprocess.CompletedProcess,
    *,
    duration: float | None = None,
) -> None:
    segments = [description, f"exit {result.returncode}"]
    if duration is not None:
        segments.append(f"{duration:.2f}s")
    log("; ".join(segments))

    for label, payload in (("stdout", result.stdout), ("stderr", result.stderr)):
        if not payload:
            continue
        text = scrub_sensitive_data(payload.decode("utf-8", errors="ignore").strip())
        if not text:
            continue
        if len(text) > MAX_GIT_LOG_CHARS:
            text = f"{text[: MAX_GIT_LOG_CHARS - 3]}..."
        log(f"{description} {label}: {text}")


def command_error(
    cwd: Path,
    result: subprocess.CompletedProcess,
    *,
    identifier: str | None = None,
    branch: str | None = None,
) -> ProjectCacheError:
    stdout = scrub_sensitive_data(result.stdout.decode("utf-8", errors="ignore").strip())
    stderr = scrub_sensitive_data(result.stderr.decode("utf-8", errors="ignore").strip())
    details = stderr or stdout or "unknown error"
    if isinstance(result.args, (list, tuple)):
        command = " ".join(str(part) for part in result.args)
    else:
        command = str(result.args)
    command = scrub_sensitive_data(command)
    friendly = friendly_git_error(cwd, command, details, result.returncode, identifier=identifier, branch=branch)
    if friendly:
        return ProjectCacheError(friendly, reason="git-command-error")
    return ProjectCacheError(
        f"git command '{command}' failed in {cwd} (exit {result.returncode}): {details}",
        reason="git-command-error",
    )


def ensure_git_repository(repo_path: Path, env: dict[str, str]) -> None:
    result = run_git_command([
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


def ensure_worktree_clean(
    repo_path: Path,
    env: dict[str, str],
    *,
    allow_force: bool,
    dry_run: bool,
    log_fn: Callable[[str], None] | None,
    identifier: str,
) -> None:
    status_result = run_git_command(["git", "status", "--porcelain"], repo_path, env)
    if status_result.returncode != 0:
        raise command_error(repo_path, status_result, identifier=identifier)
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
        reset_result = run_git_command(["git", "reset", "--hard"], repo_path, env)
        if reset_result.returncode != 0:
            raise command_error(repo_path, reset_result, identifier=identifier)
        clean_result = run_git_command(["git", "clean", "-fd"], repo_path, env)
        if clean_result.returncode != 0:
            raise command_error(repo_path, clean_result, identifier=identifier)
        status_after = run_git_command(["git", "status", "--porcelain"], repo_path, env)
        if status_after.returncode != 0:
            raise command_error(repo_path, status_after, identifier=identifier)
        if status_after.stdout.strip():
            raise ProjectCacheError(
                (
                    f"Project cache at {repo_path} could not be cleaned automatically; inspect the repository manually or delete the cache before retrying."
                ),
                reason="dirty-worktree",
            )


def remote_exists(repo_path: Path, env: dict[str, str], remote: str) -> bool:
    remotes_result = run_git_command(["git", "remote"], repo_path, env)
    if remotes_result.returncode != 0:
        raise command_error(repo_path, remotes_result)
    remotes = {
        entry.strip()
        for entry in remotes_result.stdout.decode("utf-8", errors="ignore").splitlines()
        if entry.strip()
    }
    return remote in remotes


def branch_exists(repo_path: Path, env: dict[str, str], branch: str) -> bool:
    result = run_git_command(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        repo_path,
        env,
    )
    return result.returncode == 0


def remote_branch_exists(repo_path: Path, env: dict[str, str], remote: str, branch: str) -> bool:
    result = run_git_command(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"],
        repo_path,
        env,
    )
    return result.returncode == 0


def rev_parse_head(repo_path: Path, env: dict[str, str]) -> str:
    result = run_git_command(["git", "rev-parse", "HEAD"], repo_path, env)
    if result.returncode != 0:
        raise command_error(repo_path, result)
    return result.stdout.decode("utf-8", errors="ignore").strip()


def directory_size_bytes(path: Path) -> int:
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += directory_size_bytes(Path(entry.path))
                    else:
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def create_askpass_helper() -> Path:
    fd, path_str = tempfile.mkstemp(prefix="codex-cache-askpass-", suffix=".sh")
    path = Path(path_str)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("#!/usr/bin/env bash\n")
        handle.write("printf '%s' \"${GITLAB_TOKEN}\"\n")
    path.chmod(0o700)
    return path


def repository_has_submodules(repo_path: Path) -> bool:
    gitmodules_path = repo_path / ".gitmodules"
    try:
        content = gitmodules_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(content.strip())


def repository_uses_lfs(repo_path: Path, env: dict[str, str]) -> bool:
    attributes_result = run_git_command(["git", "ls-files", "-z", "*.gitattributes"], repo_path, env)
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


def sync_additional_branch(
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

    fetch_result = run_git_command([
        "git",
        "fetch",
        "--tags",
        "--force",
        "origin",
        branch,
    ], repo_path, env)
    if fetch_result.returncode != 0:
        raise command_error(repo_path, fetch_result, identifier=identifier, branch=branch)
    log_fn(f"Fetched origin/{branch} while refreshing cache {identifier}")

    if not branch_exists(repo_path, env, branch):
        checkout_result = run_git_command([
            "git",
            "branch",
            branch,
            f"origin/{branch}",
        ], repo_path, env)
        if checkout_result.returncode != 0:
            raise command_error(repo_path, checkout_result, identifier=identifier, branch=branch)
        log_fn(f"Created local tracking branch {branch} for cache {identifier}")


def friendly_git_error(
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


def ensure_repository_integrity(
    repo_path: Path,
    env: dict[str, str],
    log_fn: Callable[[str], None],
    identifier: str,
) -> None:
    fsck_result = run_git_command(["git", "fsck", "--no-dangling"], repo_path, env)
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


def scrub_sensitive_data(value: str) -> str:
    if not value:
        return value
    return OAUTH_TOKEN_PATTERN.sub(r"\1<redacted>\3", value)


def configured_additional_branches() -> list[str]:
    configured = os.environ.get("PROJECT_CACHE_ADDITIONAL_BRANCHES", "")
    branches = [branch.strip() for branch in configured.split(",") if branch.strip()]
    deduped: list[str] = []
    for branch in branches:
        if branch not in deduped:
            deduped.append(branch)
    return deduped


__all__ = [
    "branch_exists",
    "command_error",
    "configured_additional_branches",
    "create_askpass_helper",
    "directory_size_bytes",
    "ensure_git_repository",
    "ensure_repository_integrity",
    "ensure_worktree_clean",
    "friendly_git_error",
    "git_env",
    "log_git_result",
    "remote_branch_exists",
    "remote_exists",
    "repository_has_submodules",
    "repository_uses_lfs",
    "rev_parse_head",
    "run_git_command",
    "scrub_sensitive_data",
    "sync_additional_branch",
]
