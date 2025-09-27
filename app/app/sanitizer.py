from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, List

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACES_ROOT = REPO_ROOT / "workspaces"
logger = logging.getLogger(__name__)

# Fallback patterns used if a project does not provide a .codexignore
DEFAULT_DENY_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.env",
    "*.env.*",
    "id_*",
    "id-*",
    "*.pem",
    "*.key",
    "*.crt",
    ".aws",
    ".aws/**",
    ".kube",
    ".kube/**",
    "node_modules",
    "node_modules/**",
    "dist",
    "dist/**",
    "build",
    "build/**",
    "target",
    "target/**",
    "__pycache__",
    "__pycache__/**",
    "*.log",
    "logs",
    "logs/**",
    "*.cache",
    ".cache",
    ".cache/**",
    "venv",
    "venv/**",
    ".venv",
    ".venv/**",
    "workspaces",
    "workspaces/**",
)

ANDROID_BUILD_PATTERNS: tuple[str, ...] = (
    ".gradle",
    ".gradle/**",
    "**/.gradle",
    "**/.gradle/**",
    "**/build",
    "**/build/**",
    "**/outputs/**/*.apk",
    "**/outputs/**/*.aab",
    "**/outputs/**/*.aar",
)


def load_codexignore_patterns(project_root: Path) -> List[str]:
    """Return deny patterns sourced from .codexignore, or defaults when missing."""
    ignore_file = project_root / ".codexignore"
    patterns: list[str] = []
    if ignore_file.exists():
        for raw_line in ignore_file.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    if not patterns:
        patterns.extend(DEFAULT_DENY_PATTERNS)
    # Always ensure internal workspaces are excluded even if omitted by the project.
    if not any(entry.rstrip("/") == "workspaces" for entry in patterns):
        patterns.append("workspaces/")
    for android_pattern in ANDROID_BUILD_PATTERNS:
        if android_pattern not in patterns:
            patterns.append(android_pattern)
    return patterns


def _should_exclude(rel_path: Path, patterns: Iterable[str]) -> bool:
    rel_posix = rel_path.as_posix()
    pure = PurePosixPath(rel_posix)
    for pattern in patterns:
        if not pattern:
            continue
        normalized = pattern.rstrip("/")
        if pure.match(pattern) or pure.match(normalized):
            return True
        if fnmatch(rel_posix, pattern) or fnmatch(rel_posix, normalized):
            return True
        if rel_posix == normalized:
            return True
        if rel_posix.startswith(f"{normalized}/"):
            return True
    return False


def _ignore_builder(source_root: Path, patterns: Iterable[str]):
    patterns_list = list(patterns)

    def _ignore(path: str, names: List[str]) -> List[str]:
        current_dir = Path(path)
        ignored: list[str] = []
        for name in names:
            candidate = (current_dir / name).resolve()
            try:
                relative = candidate.relative_to(source_root)
            except ValueError:
                # Outside the source root; skip filtering.
                continue
            if _should_exclude(relative, patterns_list):
                ignored.append(name)
        return ignored

    return _ignore


def _collect_tracked_paths(target_dir: Path) -> set[str]:
    git_dir = target_dir / ".git"
    if not git_dir.exists():
        return set()

    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    result = _run_git_command(["git", "ls-files", "-z"], target_dir, env)
    if result.returncode != 0:
        return set()

    tracked: set[str] = set()
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        tracked.add(entry.decode("utf-8", errors="ignore"))
    return tracked


def _chunked(iterable: Iterable[str], size: int) -> Iterator[list[str]]:
    chunk: list[str] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _mark_skip_worktree(target_dir: Path, paths: Iterable[str]) -> None:
    materialized = [path for path in paths if path]
    if not materialized:
        return

    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    for batch in _chunked(materialized, 100):
        _run_git_command(["git", "update-index", "--skip-worktree", *batch], target_dir, env, warn_on_error=True)


def _remove_denied_entries(target_dir: Path, patterns: Iterable[str]) -> None:
    patterns_list = list(patterns)
    tracked_paths = _collect_tracked_paths(target_dir)
    skip_candidates: set[str] = set()

    for root, dirs, files in os.walk(target_dir, topdown=True):
        current_dir = Path(root)

        for name in list(dirs):
            candidate = current_dir / name
            try:
                relative = candidate.relative_to(target_dir)
            except ValueError:
                continue
            if _should_exclude(relative, patterns_list):
                rel_posix = relative.as_posix()
                for tracked in list(tracked_paths):
                    if tracked == rel_posix or tracked.startswith(f"{rel_posix}/"):
                        skip_candidates.add(tracked)
                        tracked_paths.discard(tracked)
                shutil.rmtree(candidate, ignore_errors=True)
                dirs.remove(name)

        for name in list(files):
            candidate = current_dir / name
            try:
                relative = candidate.relative_to(target_dir)
            except ValueError:
                continue
            if _should_exclude(relative, patterns_list):
                rel_posix = relative.as_posix()
                if rel_posix in tracked_paths:
                    skip_candidates.add(rel_posix)
                    tracked_paths.discard(rel_posix)
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    logger.debug("Failed to remove denied file %s: %s", candidate, exc)

    _mark_skip_worktree(target_dir, skip_candidates)


def sanitize_workspace(
    project_root: Path,
    task_id: int,
    *,
    default_branch: str | None = None,
    gitlab_token: str | None = None,
) -> Path:
    """Copy a sanitized version of the project into workspaces/<task_id>/safe."""
    source_root = project_root.resolve()
    if not source_root.exists():
        raise FileNotFoundError(f"Project path does not exist: {source_root}")

    target_dir = WORKSPACES_ROOT / str(task_id) / "safe"
    target_parent = target_dir.parent
    target_parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    patterns = load_codexignore_patterns(source_root)
    if "workspaces" not in {p.rstrip("/") for p in patterns}:
        patterns.append("workspaces/")

    shutil.copytree(
        source_root,
        target_dir,
        symlinks=True,
        ignore=_ignore_builder(source_root, patterns),
    )

    _prepare_git_workspace(target_dir, default_branch=default_branch, gitlab_token=gitlab_token)
    _remove_denied_entries(target_dir, patterns)
    return target_dir


def _prepare_git_workspace(target_dir: Path, default_branch: str | None, gitlab_token: str | None) -> None:
    """Reset tracked changes, align with the default branch, and drop untracked files."""
    git_dir = target_dir / ".git"
    if not git_dir.exists():
        return

    base_env = os.environ.copy()
    base_env.setdefault("GIT_TERMINAL_PROMPT", "0")

    _run_git_command(["git", "reset", "--hard", "HEAD"], target_dir, base_env, warn_on_error=True)

    if default_branch:
        _checkout_default_branch(target_dir, default_branch, gitlab_token)

    _run_git_command(["git", "clean", "-fdx"], target_dir, base_env, warn_on_error=True)


def _checkout_default_branch(target_dir: Path, branch: str, gitlab_token: str | None) -> None:
    """Ensure the sanitized workspace uses the default branch, preferring the remote state."""
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")

    askpass_path: Path | None = None
    if gitlab_token:
        env["GITLAB_TOKEN"] = gitlab_token
        env.setdefault("GIT_USERNAME", "oauth2")
        askpass_path = _create_askpass_helper()
        env["GIT_ASKPASS"] = str(askpass_path)

    remote_ref = f"refs/remotes/origin/{branch}"
    try:
        fetch_result = _run_git_command(
            ["git", "fetch", "--tags", "--force", "origin", branch],
            target_dir,
            env,
            warn_on_error=True,
        )

        if fetch_result.returncode == 0 and _git_ref_exists(remote_ref, target_dir, env):
            checkout_cmd = ["git", "checkout", "-B", branch, f"origin/{branch}"]
            checkout_result = _run_git_command(checkout_cmd, target_dir, env, warn_on_error=True)
            if checkout_result.returncode == 0:
                _run_git_command(["git", "reset", "--hard", "HEAD"], target_dir, env, warn_on_error=True)
                return

        local_ref = f"refs/heads/{branch}"
        if _git_ref_exists(local_ref, target_dir, env):
            checkout_result = _run_git_command(["git", "checkout", branch], target_dir, env, warn_on_error=True)
            if checkout_result.returncode == 0:
                _run_git_command(["git", "reset", "--hard", "HEAD"], target_dir, env, warn_on_error=True)
                return

        logger.warning(
            "Default branch %s is unavailable inside sanitized workspace %s; proceeding with existing HEAD",
            branch,
            target_dir,
        )
    finally:
        if askpass_path is not None:
            try:
                askpass_path.unlink()
            except OSError:
                logger.info("Failed to remove temporary askpass helper %s", askpass_path)


def _git_ref_exists(ref: str, target_dir: Path, env: dict[str, str]) -> bool:
    result = _run_git_command(["git", "show-ref", "--verify", "--quiet", ref], target_dir, env)
    return result.returncode == 0


def _run_git_command(
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None,
    *,
    warn_on_error: bool = False,
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError) as exc:
        if warn_on_error:
            logger.warning("git command %s failed in %s: %s", " ".join(args), cwd, exc)
        raise

    if warn_on_error and result.returncode != 0:
        stdout = result.stdout.decode("utf-8", errors="ignore").strip()
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        logger.warning(
            "git command %s failed in %s (exit %s): %s %s",
            " ".join(args),
            cwd,
            result.returncode,
            stdout,
            stderr,
        )
    return result


def _create_askpass_helper() -> Path:
    fd, path_str = tempfile.mkstemp(prefix="codex-askpass-", suffix=".sh")
    path = Path(path_str)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("#!/usr/bin/env bash\n")
        handle.write("printf '%s' \"${GITLAB_TOKEN}\"\n")
    path.chmod(0o700)
    return path
