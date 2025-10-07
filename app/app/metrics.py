"""Observability helpers for emitting Prometheus metrics."""

from __future__ import annotations

from typing import Callable, Dict, TypeVar

from prometheus_client import REGISTRY, Counter, Gauge, Histogram


MetricT = TypeVar("MetricT", Counter, Gauge, Histogram)

_METRICS: Dict[str, MetricT] = {}


class MetricRegistrationError(RuntimeError):
    """Raised when a Prometheus metric has already been registered."""


def _get_or_create_metric(
    factory: Callable[..., MetricT],
    name: str,
    documentation: str,
    **kwargs,
) -> MetricT:
    """Return a process-wide metric instance, creating it when absent."""

    metric = _METRICS.get(name)
    if metric is not None:
        return metric
    try:
        metric = factory(name, documentation, **kwargs)
    except ValueError as error:
        message = str(error)
        if "Duplicated timeseries" in message or "Duplicated metric" in message:
            raise MetricRegistrationError(
                f"Prometheus metric '{name}' is already registered; call reset_metrics_registry() in tests "
                "or ensure metrics are defined only once at module import time."
            ) from error
        raise
    _METRICS[name] = metric
    return metric


_CACHE_OPERATION_DURATION: Histogram | None = None
_CACHE_OPERATION_FAILURES: Counter | None = None
_CACHE_SIZE_BYTES: Gauge | None = None
_CACHE_SNAPSHOT_COUNT: Gauge | None = None


def _cache_operation_duration() -> Histogram:
    global _CACHE_OPERATION_DURATION
    if _CACHE_OPERATION_DURATION is None:
        _CACHE_OPERATION_DURATION = _get_or_create_metric(
            Histogram,
            "gitlab_project_cache_operation_duration_seconds",
            "Time spent bootstrapping or refreshing GitLab project caches.",
            labelnames=("operation", "project", "dry_run"),
        )
    return _CACHE_OPERATION_DURATION


def _cache_operation_failures() -> Counter:
    global _CACHE_OPERATION_FAILURES
    if _CACHE_OPERATION_FAILURES is None:
        _CACHE_OPERATION_FAILURES = _get_or_create_metric(
            Counter,
            "gitlab_project_cache_operation_failures_total",
            "Count of project cache failures grouped by operation and reason.",
            labelnames=("operation", "project", "reason"),
        )
    return _CACHE_OPERATION_FAILURES


def _cache_size_bytes() -> Gauge:
    global _CACHE_SIZE_BYTES
    if _CACHE_SIZE_BYTES is None:
        _CACHE_SIZE_BYTES = _get_or_create_metric(
            Gauge,
            "gitlab_project_cache_size_bytes",
            "Size on disk of the cached repository following the latest operation.",
            labelnames=("project",),
        )
    return _CACHE_SIZE_BYTES


def _cache_snapshot_count() -> Gauge:
    global _CACHE_SNAPSHOT_COUNT
    if _CACHE_SNAPSHOT_COUNT is None:
        _CACHE_SNAPSHOT_COUNT = _get_or_create_metric(
            Gauge,
            "gitlab_project_cache_snapshot_count",
            "Number of retained cache snapshots per project.",
            labelnames=("project",),
        )
    return _CACHE_SNAPSHOT_COUNT


class WorkerMetricsPublisher:
    """Lightweight adapter for publishing worker scheduling metrics."""

    def __init__(self) -> None:
        self._active = _get_or_create_metric(
            Gauge,
            "codex_worker_active_tasks",
            "Number of tasks currently being processed by the orchestrator worker pool.",
        )
        self._queue_depth = _get_or_create_metric(
            Gauge,
            "codex_worker_queue_depth",
            "Count of pending tasks waiting for a worker slot, including deferred items.",
        )
        self._throttled = _get_or_create_metric(
            Gauge,
            "codex_worker_throttled_tasks",
            "Number of tasks temporarily deferred due to concurrency limits.",
        )

    def publish(
        self,
        *,
        active_tasks: int,
        queue_depth: int,
        throttled_tasks: int,
    ) -> None:
        self._active.set(max(active_tasks, 0))
        self._queue_depth.set(max(queue_depth, 0))
        self._throttled.set(max(throttled_tasks, 0))


_WORKER_METRICS_SINGLETON: WorkerMetricsPublisher | None = None


def worker_metrics() -> WorkerMetricsPublisher:
    """Return the process-wide worker metrics publisher singleton."""

    global _WORKER_METRICS_SINGLETON
    if _WORKER_METRICS_SINGLETON is None:
        _WORKER_METRICS_SINGLETON = WorkerMetricsPublisher()
    return _WORKER_METRICS_SINGLETON


def observe_operation_duration(operation: str, project: str, *, dry_run: bool, seconds: float) -> None:
    """Record how long a cache operation took."""

    _cache_operation_duration().labels(
        operation=operation,
        project=project,
        dry_run="true" if dry_run else "false",
    ).observe(max(seconds, 0.0))


def increment_operation_failure(operation: str, project: str, *, reason: str) -> None:
    """Increment the failure counter for the supplied reason."""

    _cache_operation_failures().labels(
        operation=operation,
        project=project,
        reason=reason or "unknown",
    ).inc()


def set_cache_size(project: str, size_bytes: int) -> None:
    """Update the cache size gauge for a project."""

    _cache_size_bytes().labels(project=project).set(max(size_bytes, 0))


def set_snapshot_count(project: str, count: int) -> None:
    """Record how many cache snapshots are retained for a project."""

    _cache_snapshot_count().labels(project=project).set(max(count, 0))


def reset_metrics_registry() -> None:
    """Clear cached metric singletons and unregister them from the default registry."""

    global _CACHE_OPERATION_DURATION
    global _CACHE_OPERATION_FAILURES
    global _CACHE_SIZE_BYTES
    global _CACHE_SNAPSHOT_COUNT
    global _WORKER_METRICS_SINGLETON
    for metric in list(_METRICS.values()):
        try:
            REGISTRY.unregister(metric)
        except KeyError:
            # Collector already removed by the registry.
            pass
    _METRICS.clear()
    _CACHE_OPERATION_DURATION = None
    _CACHE_OPERATION_FAILURES = None
    _CACHE_SIZE_BYTES = None
    _CACHE_SNAPSHOT_COUNT = None
    _WORKER_METRICS_SINGLETON = None
