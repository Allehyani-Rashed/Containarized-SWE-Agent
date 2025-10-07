"""Worker scheduling primitives extracted from the monolithic queue manager."""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Callable, Deque, Dict, Iterable, Optional

from .metrics import WorkerMetricsPublisher, worker_metrics

SCHEDULER_IDLE_WAIT_SECONDS = 0.25
DEFERRED_RETRY_BACKOFF_SECONDS = 0.1


class TaskScheduleMetadata:
    """Scheduling metadata describing the owning project and concurrency limit."""

    __slots__ = ("project_id", "project_limit")

    def __init__(self, project_id: int, project_limit: int) -> None:
        self.project_id = project_id
        self.project_limit = project_limit


SchedulerFailureHandler = Callable[[int, Exception, str], None]
SchedulerExecutor = Callable[[int], None]
SchedulerMetadataResolver = Callable[[int], Optional[TaskScheduleMetadata]]
SchedulerProjectRecorder = Callable[[int, int], None]
SchedulerErrorHandler = Callable[[int, Exception], None]
SchedulerCompletionCallback = Callable[[int], None]


class WorkerScheduler:
    """Isolated queue orchestrator responsible for concurrency enforcement."""

    def __init__(
        self,
        *,
        max_workers: int,
        metrics: WorkerMetricsPublisher | None = None,
        task_executor: SchedulerExecutor,
        metadata_resolver: SchedulerMetadataResolver,
        project_recorder: SchedulerProjectRecorder,
        failure_handler: SchedulerFailureHandler,
        completion_callback: SchedulerCompletionCallback,
        unexpected_error_handler: SchedulerErrorHandler | None = None,
        idle_wait_seconds: float = SCHEDULER_IDLE_WAIT_SECONDS,
        retry_backoff_seconds: float = DEFERRED_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self._max_workers = max(1, max_workers)
        self._metrics = metrics or worker_metrics()
        self._task_executor = task_executor
        self._metadata_resolver = metadata_resolver
        self._project_recorder = project_recorder
        self._failure_handler = failure_handler
        self._completion_callback = completion_callback
        self._unexpected_error_handler = unexpected_error_handler
        self._idle_wait_seconds = idle_wait_seconds
        self._retry_backoff_seconds = retry_backoff_seconds

        self._tasks: "Queue[int]" = Queue()
        self._deferred_tasks: Deque[int] = deque()
        self._active_tasks: set[int] = set()
        self._project_active_counts: Dict[int, int] = {}
        self._throttled_task_ids: set[int] = set()
        self._task_metadata: Dict[int, TaskScheduleMetadata] = {}

        self._stop_event = Event()
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="task-worker",
        )
        self._thread = Thread(target=self._run_loop, name="task-dispatcher", daemon=True)

    # Lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._tasks.put(-1)
        self._thread.join(timeout=2)
        self._executor.shutdown(wait=True, cancel_futures=False)

    # State accessors ----------------------------------------------------

    def enqueue(self, task_id: int) -> None:
        self._tasks.put(task_id)
        self._update_metrics()

    def get_active_task_ids(self) -> list[int]:
        with self._lock:
            return list(self._active_tasks)

    def get_queue_depth(self) -> int:
        return self._tasks.qsize()

    def get_throttled_task_ids(self) -> list[int]:
        with self._lock:
            return list(self._throttled_task_ids)

    def clear_cached_metadata(self) -> None:
        with self._lock:
            self._task_metadata.clear()

    # Internal orchestration ---------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            task_id, source = self._next_task()
            if task_id is None:
                self._update_metrics()
                time.sleep(self._idle_wait_seconds)
                continue

            if source == "queue":
                self._tasks.task_done()

            if task_id < 0:
                if self._stop_event.is_set():
                    break
                continue

            try:
                scheduled = self._schedule_task(task_id)
            except Exception as exc:  # noqa: BLE001 - keep dispatcher alive on failure
                self._failure_handler(task_id, exc, stage="schedule")
                continue

            if scheduled:
                continue

            try:
                self._defer_task(task_id)
            except Exception as exc:  # noqa: BLE001 - keep dispatcher alive on failure
                self._failure_handler(task_id, exc, stage="defer")
                continue

            time.sleep(self._retry_backoff_seconds)

        self._update_metrics()

    def _next_task(self) -> tuple[Optional[int], Optional[str]]:
        deferred_task = self._pop_runnable_deferred()
        if deferred_task is not None:
            return deferred_task, "deferred"

        try:
            task_id = self._tasks.get(timeout=self._idle_wait_seconds)
        except Empty:
            deferred_task = self._pop_runnable_deferred()
            if deferred_task is not None:
                return deferred_task, "deferred"
            return None, None
        return task_id, "queue"

    def _pop_runnable_deferred(self) -> Optional[int]:
        if not self._deferred_tasks:
            return None

        for _ in range(len(self._deferred_tasks)):
            task_id = self._deferred_tasks[0]
            metadata = self._resolve_metadata(task_id)
            if metadata is None:
                self._deferred_tasks.popleft()
                self._throttled_task_ids.discard(task_id)
                self._task_metadata.pop(task_id, None)
                continue
            if self._can_schedule(metadata):
                self._deferred_tasks.popleft()
                return task_id
            self._deferred_tasks.rotate(-1)
        return None

    def _resolve_metadata(self, task_id: int) -> Optional[TaskScheduleMetadata]:
        with self._lock:
            cached = self._task_metadata.get(task_id)
        if cached is not None:
            return cached
        metadata = self._metadata_resolver(task_id)
        if metadata is not None:
            with self._lock:
                self._task_metadata[task_id] = metadata
        return metadata

    def _can_schedule(self, metadata: TaskScheduleMetadata) -> bool:
        with self._lock:
            if len(self._active_tasks) >= self._max_workers:
                return False
            project_active = self._project_active_counts.get(metadata.project_id, 0)
            if metadata.project_limit and project_active >= metadata.project_limit:
                return False
        return True

    def _schedule_task(self, task_id: int) -> bool:
        metadata = self._resolve_metadata(task_id)
        if metadata is None:
            return True

        with self._lock:
            if len(self._active_tasks) >= self._max_workers:
                return False
            project_active = self._project_active_counts.get(metadata.project_id, 0)
            if metadata.project_limit and project_active >= metadata.project_limit:
                return False
            self._active_tasks.add(task_id)
            self._project_active_counts[metadata.project_id] = project_active + 1
            self._throttled_task_ids.discard(task_id)

        self._project_recorder(metadata.project_id, project_active + 1)

        future = self._executor.submit(self._task_executor, task_id)

        def _finalize(fut) -> None:  # noqa: ANN001 - signature defined by executor
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001 - surface unexpected crashes without killing worker
                if self._unexpected_error_handler is not None:
                    self._unexpected_error_handler(task_id, exc)
            finally:
                self._handle_completion(task_id, metadata)

        future.add_done_callback(_finalize)
        self._update_metrics()
        return True

    def _handle_completion(self, task_id: int, metadata: TaskScheduleMetadata) -> None:
        with self._lock:
            self._active_tasks.discard(task_id)
            previous = self._project_active_counts.get(metadata.project_id, 0)
            remaining = previous - 1
            if remaining <= 0:
                self._project_active_counts.pop(metadata.project_id, None)
                remaining = 0
            else:
                self._project_active_counts[metadata.project_id] = remaining
            self._task_metadata.pop(task_id, None)
            self._throttled_task_ids.discard(task_id)
            try:
                self._deferred_tasks.remove(task_id)
            except ValueError:
                pass

        self._project_recorder(metadata.project_id, remaining)
        self._completion_callback(task_id)
        self._update_metrics()

    def _defer_task(self, task_id: int) -> None:
        metadata = self._resolve_metadata(task_id)
        if metadata is None:
            return
        self._deferred_tasks.append(task_id)
        with self._lock:
            self._throttled_task_ids.add(task_id)
        self._update_metrics()

    def _update_metrics(self) -> None:
        queue_depth = self._tasks.qsize() + len(self._deferred_tasks)
        with self._lock:
            active = len(self._active_tasks)
            throttled = len(self._throttled_task_ids)
        self._metrics.publish(
            active_tasks=active,
            queue_depth=max(queue_depth, 0),
            throttled_tasks=throttled,
        )

    # Debug helpers ------------------------------------------------------

    def debug_snapshot(self) -> dict[str, Iterable[int]]:
        """Return a snapshot of scheduling state for test assertions."""

        with self._lock:
            return {
                "active": tuple(self._active_tasks),
                "deferred": tuple(self._deferred_tasks),
                "throttled": tuple(self._throttled_task_ids),
            }
