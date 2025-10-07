from __future__ import annotations

from typing import Dict, Optional
from urllib.parse import quote, urlencode

from sqlmodel import Session

from ..integrations import get_gitlab_pat_token
from ..models import Project


def resolve_project_gitlab_token(session: Session, project: Project) -> Optional[str]:
    project_token = (project.gitlab_token or "").strip()
    if project_token:
        return project_token
    token = get_gitlab_pat_token(session)
    if not token:
        return None
    candidate = token.strip()
    return candidate or None


def build_gitlab_branches_url(project: Project, *, page: int, per_page: int, search: Optional[str]) -> str:
    encoded_path = quote(project.gitlab_project_path.strip("/"), safe="")
    base = f"{project.gitlab_host.rstrip('/')}/api/v4/projects/{encoded_path}/repository/branches"
    params: Dict[str, str] = {"page": str(page), "per_page": str(per_page)}
    if search:
        params["search"] = search
    query = urlencode(params)
    return f"{base}?{query}"


def clean_gitlab_error(message: str, *, max_length: int = 240) -> str:
    clean = " ".join(str(message).split())
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1]}…"


__all__ = [
    "build_gitlab_branches_url",
    "clean_gitlab_error",
    "resolve_project_gitlab_token",
]
