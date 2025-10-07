from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from ..models import AuditLog


def record_audit_event(session: Session, action: str, actor: Optional[str], details: Optional[str]) -> None:
    """Persist an audit log entry."""

    entry = AuditLog(action=action, actor=actor, details=details)
    session.add(entry)


def normalize_actor(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    candidate = actor.strip()
    return candidate or None


def normalize_reason(reason: Optional[str]) -> Optional[str]:
    if reason is None:
        return None
    candidate = reason.strip()
    return candidate or None


__all__ = ["normalize_actor", "normalize_reason", "record_audit_event"]
