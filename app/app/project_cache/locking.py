"""Cross-platform advisory locking for cache operations."""

from __future__ import annotations

import errno
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .errors import ProjectCacheError

try:  # pragma: no cover - platform-specific import
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore

try:  # pragma: no cover - platform-specific import
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = float(os.environ.get("PROJECT_CACHE_LOCK_TIMEOUT_SECONDS", "180"))
LOCK_POLL_INTERVAL = 0.25
LOCK_SUPPORTED = fcntl is not None or msvcrt is not None
LOCK_BUSY_ERRNOS = {errno.EACCES, errno.EAGAIN, getattr(errno, "EWOULDBLOCK", errno.EAGAIN)}


@contextmanager
def cache_operation_lock(
    repo_path: Path,
    *,
    identifier: str,
    log_fn: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Synchronise operations touching the same cache clone."""

    if not LOCK_SUPPORTED:
        yield
        return

    parent = repo_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    lock_path = parent / ".lock"
    start = time.perf_counter()
    message_emitted = False
    locked = False

    handle = lock_path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()

        while not locked:
            try:
                _acquire_file_lock(handle)
                locked = True
            except BlockingIOError:
                pass
            except OSError as exc:  # pragma: no branch - narrow error path
                if getattr(exc, "errno", None) not in LOCK_BUSY_ERRNOS:
                    raise ProjectCacheError(
                        f"Failed to lock cache for {identifier}: {exc}",
                        reason="cache-lock-error",
                    ) from exc
            if locked:
                break
            elapsed = time.perf_counter() - start
            if log_fn and not message_emitted and elapsed > 1:
                log_fn(f"Waiting for cache lock at {repo_path}; {elapsed:.1f}s elapsed")
                message_emitted = True
            if elapsed >= LOCK_TIMEOUT_SECONDS:
                raise ProjectCacheError(
                    f"Timed out waiting for cache lock at {repo_path}",
                    reason="cache-lock-timeout",
                )
            time.sleep(LOCK_POLL_INTERVAL)

        yield
    finally:
        try:
            _release_file_lock(handle)
        finally:
            handle.close()


def _acquire_file_lock(handle) -> None:
    if fcntl is not None:  # pragma: no branch - depends on platform
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif msvcrt is not None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)


def _release_file_lock(handle) -> None:
    if fcntl is not None:  # pragma: no branch - depends on platform
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            logger.info("Failed to release Windows file lock for %s", handle)


__all__ = ["LOCK_POLL_INTERVAL", "LOCK_TIMEOUT_SECONDS", "cache_operation_lock"]

