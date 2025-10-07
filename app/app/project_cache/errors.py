"""Error types for project cache operations."""

from __future__ import annotations


class ProjectCacheError(RuntimeError):
    """Raised when a project cache operation cannot complete safely."""

    def __init__(self, message: str, *, reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason


__all__ = ["ProjectCacheError"]

