from __future__ import annotations

import re
import subprocess
from typing import Optional

from fastapi import HTTPException, status

from ..codex_models import (
    default_model_id,
    default_reasoning_effort,
    valid_model_ids,
    valid_reasoning_efforts,
)
from ..models import TaskChangeMode


_VALID_CODEX_MODEL_IDS = valid_model_ids()
_VALID_REASONING_EFFORTS = valid_reasoning_efforts()
_BRANCH_FORBIDDEN_PATTERN = re.compile(r"[\s~^:?*\\[\\]\\x00-\\x1F\\x7F]")


def normalize_non_empty(value: Optional[str], *, field: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} cannot be empty")
    return candidate


def normalize_gitlab_host(value: Optional[str]) -> str:
    host = normalize_non_empty(value, field="GitLab host")
    return host.rstrip("/")


def normalize_gitlab_project_path(value: Optional[str]) -> str:
    path = normalize_non_empty(value, field="GitLab project path")
    return path.strip("/")


def normalize_branch_name(raw: str) -> str:
    branch = (raw or "").strip()
    if not branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot be empty")
    if branch in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot be '.' or '..'")
    if branch.startswith("/") or branch.endswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot start or end with '/'")
    if branch.startswith("-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot start with '-'")
    if branch.endswith(".") or branch.endswith(" "):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot end with '.' or space")
    if branch.endswith(".lock"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot end with '.lock'")
    if ".." in branch or "@{" in branch or "//" in branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name contains invalid sequences")
    if branch.startswith("refs/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name cannot start with 'refs/'")
    if _BRANCH_FORBIDDEN_PATTERN.search(branch):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name contains invalid characters")
    if len(branch.encode("utf-8")) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name is too long (max 255 bytes)")

    try:
        subprocess.run(["git", "check-ref-format", "--branch", branch], check=True, capture_output=True)
    except FileNotFoundError:
        return branch
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Branch name is not a valid git reference") from exc

    return branch


def normalize_codex_model(model_id: Optional[str]) -> str:
    candidate = (model_id or "").strip()
    if not candidate:
        default = default_model_id()
        if default is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No Codex model configured")
        return default
    if candidate not in _VALID_CODEX_MODEL_IDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown Codex model requested")
    return candidate


def normalize_codex_reasoning_effort(value: Optional[str]) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return default_reasoning_effort()
    if candidate not in _VALID_REASONING_EFFORTS:
        allowed = ", ".join(sorted(_VALID_REASONING_EFFORTS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Codex reasoning effort; expected one of: {allowed}",
        )
    return candidate


def normalize_mr_title(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    candidate = " ".join((value or "").split())
    if not candidate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Merge request title cannot be empty")
    if len(candidate) > 240:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Merge request title cannot exceed 240 characters")
    return candidate


def normalize_change_mode(value: Optional[TaskChangeMode | str]) -> TaskChangeMode:
    if value is None:
        return TaskChangeMode.merge_request
    if isinstance(value, TaskChangeMode):
        return value
    candidate = (value or "").strip().lower().replace("-", "_")
    try:
        return TaskChangeMode(candidate)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in TaskChangeMode)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid change mode; expected one of: {allowed}",
        ) from exc


__all__ = [
    "normalize_branch_name",
    "normalize_change_mode",
    "normalize_codex_model",
    "normalize_codex_reasoning_effort",
    "normalize_gitlab_host",
    "normalize_gitlab_project_path",
    "normalize_mr_title",
    "normalize_non_empty",
]
