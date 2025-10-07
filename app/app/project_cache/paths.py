"""Primitives for locating project cache repositories and identifiers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import ProjectCacheError

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9._-]+")


def project_root() -> Path:
    """Return the repository root for the orchestrator codebase."""

    # ``paths.py`` sits under ``app/app/project_cache`` so ``parents[3]`` is the
    # repository root regardless of how the package is imported.
    return Path(__file__).resolve().parents[3]


def get_cache_root() -> Path:
    """Return the root directory storing project cache clones.

    The location can be overridden via the ``PROJECT_CACHE_ROOT`` environment
    variable which is resolved relative to the current user (``~`` expansion).
    """

    override = os.environ.get("PROJECT_CACHE_ROOT")
    if override:
        return Path(override).expanduser()
    return project_root() / "project-cache"


def ensure_cache_root(cache_root: Path | None = None) -> Path:
    """Ensure the cache root exists and return the expanded path."""

    root = (cache_root or get_cache_root()).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


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


def build_project_remote_url(
    gitlab_host: str,
    project_path: str,
    *,
    gitlab_token: str | None = None,
) -> str:
    """Construct the authenticated Git URL used for cache bootstrapping."""

    from urllib.parse import quote, urlparse, urlunparse

    host = (gitlab_host or "").strip()
    path = (project_path or "").strip().strip("/")
    if not host or not path:
        raise ProjectCacheError(
            "GitLab host and project path must be configured to bootstrap the project cache",
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


def _normalise_segment(value: str) -> str:
    segment = value.strip().lower().replace("/", "-")
    segment = _NON_SLUG_CHARS.sub("-", segment)
    return segment.strip("-")


__all__ = [
    "build_project_remote_url",
    "ensure_cache_root",
    "get_cache_root",
    "project_cache_identifier",
    "project_cache_repo_path",
    "project_cache_slug",
    "project_root",
]

