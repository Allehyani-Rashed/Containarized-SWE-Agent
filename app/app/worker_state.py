from __future__ import annotations

import logging
import shutil
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CredentialStatus:
    gitlab_pat_available: bool = False
    gitlab_pat_last_updated: Optional[datetime] = None
    chatgpt_session_available: bool = False
    chatgpt_session_last_updated: Optional[datetime] = None

    def set_gitlab_pat(self, available: bool) -> bool:
        changed = self.gitlab_pat_available != available
        self.gitlab_pat_available = available
        self.gitlab_pat_last_updated = _utc_now()
        return changed

    def set_chatgpt_session(self, available: bool) -> bool:
        changed = self.chatgpt_session_available != available
        self.chatgpt_session_available = available
        self.chatgpt_session_last_updated = _utc_now()
        return changed

    @staticmethod
    def _serialize(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "gitlab_pat_available": self.gitlab_pat_available,
            "gitlab_pat_last_updated": self._serialize(self.gitlab_pat_last_updated),
            "chatgpt_session_available": self.chatgpt_session_available,
            "chatgpt_session_last_updated": self._serialize(
                self.chatgpt_session_last_updated
            ),
        }


@dataclass
class TaskRuntimeState:
    """Runtime container for task-scoped worker state."""

    task_id: int
    log_directory: Path
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    completed: bool = False
    terminal_reason: Optional[str] = None
    log_flush_count: int = 0
    logs: List[str] = field(default_factory=list)
    redactions: List[str] = field(default_factory=list)
    credential_status: CredentialStatus = field(default_factory=CredentialStatus)
    cache_directories: Dict[str, Path] = field(default_factory=dict)
    abort_file: Optional[Path] = None
    abort_event: Event = field(default_factory=Event, repr=False)
    terminal_event: Event = field(default_factory=Event, repr=False)
    _pending_events: Deque[Dict[str, Any]] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        self._lock = Lock()
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_directory / f"{self.task_id}.log"

    def reset_for_run(self) -> None:
        """Reset transient flags ahead of a new execution attempt."""
        with self._lock:
            self.completed = False
            self.terminal_reason = None
            self.updated_at = _utc_now()
            self._pending_events.clear()
        self.abort_event.clear()
        self.terminal_event.clear()
        self.clear_abort_file()

    def update_credentials(
        self,
        *,
        gitlab_available: Optional[bool] = None,
        chatgpt_available: Optional[bool] = None,
        force: bool = False,
    ) -> bool:
        changed = False
        payload: Dict[str, Any] | None = None
        with self._lock:
            if gitlab_available is not None:
                changed |= self.credential_status.set_gitlab_pat(gitlab_available)
            if chatgpt_available is not None:
                changed |= self.credential_status.set_chatgpt_session(chatgpt_available)
            if changed:
                self.updated_at = _utc_now()
            if changed or force:
                payload = self.credential_status.as_payload()
        if payload is not None:
            enriched = dict(payload)
            enriched["task_id"] = self.task_id
            self.enqueue_event("credential-event", enriched)
        return changed

    def initialize_credentials(
        self,
        gitlab_available: bool,
        chatgpt_available: bool,
    ) -> None:
        changed = self.update_credentials(
            gitlab_available=gitlab_available,
            chatgpt_available=chatgpt_available,
        )
        if not changed:
            self.update_credentials(force=True)

    def credential_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            payload = self.credential_status.as_payload()
        payload["task_id"] = self.task_id
        return payload

    def enqueue_event(self, event: str, payload: Dict[str, Any]) -> None:
        record = {
            "event": event,
            "payload": dict(payload),
            "timestamp": _utc_now().isoformat(),
        }
        with self._lock:
            self._pending_events.append(record)

    def drain_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            events = list(self._pending_events)
            self._pending_events.clear()
        return events

    def register_cache_directory(self, name: str, path: Path) -> None:
        with self._lock:
            self.cache_directories[name] = path

    def consume_cache_directories(self) -> Dict[str, Path]:
        with self._lock:
            directories = dict(self.cache_directories)
            self.cache_directories.clear()
        return directories

    def remove_cache_directories(self) -> None:
        self.clear_abort_file()
        for path in self.consume_cache_directories().values():
            try:
                shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass

    def set_abort_file(self, path: Path) -> None:
        with self._lock:
            self.abort_file = path

    def signal_abort_marker(self) -> None:
        with self._lock:
            path = self.abort_file
        if path is None:
            return
        try:
            path.write_text("abort\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to update abort marker %s for task %s: %s", path, self.task_id, exc)

    def clear_abort_file(self) -> None:
        with self._lock:
            path = self.abort_file
            self.abort_file = None
        if path is None:
            return
        try:
            path.unlink()
        except OSError:
            pass

    def append_log(self, line: str) -> None:
        """Append a sanitized log line and persist it to disk."""
        with self._lock:
            self.logs.append(line)
            self.updated_at = _utc_now()
        self._persist_line(line)

    def snapshot(self) -> Tuple[List[str], bool]:
        with self._lock:
            return list(self.logs), self.completed

    def hydrate_from_disk(self) -> None:
        """Populate the in-memory buffer from persisted logs if present."""
        if not self.log_path.exists():
            return
        try:
            with self.log_path.open("r", encoding="utf-8") as handle:
                persisted = [line.rstrip("\n") for line in handle]
        except OSError as exc:  # noqa: BLE001 - best-effort persistence
            logger.warning(
                "Failed to read persisted logs for task %s from %s: %s",
                self.task_id,
                self.log_path,
                exc,
            )
            return
        with self._lock:
            if not self.logs:
                self.logs = persisted
            elif len(self.logs) < len(persisted):
                self.logs.extend(persisted[len(self.logs):])

    def mark_complete(self, reason: Optional[str]) -> None:
        with self._lock:
            self.completed = True
            self.terminal_reason = reason
            self.updated_at = _utc_now()
        self.abort_event.set()
        self.terminal_event.set()

    def register_redactions(self, secrets: List[str]) -> None:
        filtered = [value for value in secrets if value]
        if not filtered:
            return
        augmented: List[str] = []
        for value in filtered:
            augmented.append(value)
            augmented.append(f"oauth2:{value}")
        with self._lock:
            for value in augmented:
                if value not in self.redactions:
                    self.redactions.append(value)

    def clear_redactions(self) -> None:
        with self._lock:
            self.redactions.clear()

    def get_redactions(self) -> List[str]:
        with self._lock:
            return list(self.redactions)

    def get_terminal_reason(self) -> Optional[str]:
        with self._lock:
            return self.terminal_reason

    def teardown(self) -> None:
        """Remove transient state and best-effort delete the persisted log."""
        with self._lock:
            self.logs.clear()
            self.redactions.clear()
            self._pending_events.clear()
        try:
            self.log_path.unlink()
        except OSError:
            # Logs are archival; failure to delete is non-fatal.
            pass
        self.remove_cache_directories()

    def _persist_line(self, line: str) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        except OSError as exc:  # noqa: BLE001 - persist best-effort
            logger.warning(
                "Failed to append task %s log entry to %s: %s",
                self.task_id,
                self.log_path,
                exc,
            )
            return
        with self._lock:
            self.log_flush_count += 1
