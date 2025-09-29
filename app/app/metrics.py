"""Observability helpers for emitting Prometheus metrics."""

from __future__ import annotations

from typing import Callable, TypeVar

from prometheus_client import Counter, Gauge, Histogram, REGISTRY


MetricT = TypeVar("MetricT", Counter, Gauge, Histogram)


def _get_or_create_metric(factory: Callable[..., MetricT], name: str, documentation: str, **kwargs) -> MetricT:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return factory(name, documentation, **kwargs)


_CACHE_OPERATION_DURATION = _get_or_create_metric(
    Histogram,
    "gitlab_project_cache_operation_duration_seconds",
    "Time spent bootstrapping or refreshing GitLab project caches.",
    labelnames=("operation", "project", "dry_run"),
)

_CACHE_OPERATION_FAILURES = _get_or_create_metric(
    Counter,
    "gitlab_project_cache_operation_failures_total",
    "Count of project cache failures grouped by operation and reason.",
    labelnames=("operation", "project", "reason"),
)

_CACHE_SIZE_BYTES = _get_or_create_metric(
    Gauge,
    "gitlab_project_cache_size_bytes",
    "Size on disk of the cached repository following the latest operation.",
    labelnames=("project",),
)

_CACHE_SNAPSHOT_COUNT = _get_or_create_metric(
    Gauge,
    "gitlab_project_cache_snapshot_count",
    "Number of retained cache snapshots per project.",
    labelnames=("project",),
)


def observe_operation_duration(operation: str, project: str, *, dry_run: bool, seconds: float) -> None:
    """Record how long a cache operation took."""

    _CACHE_OPERATION_DURATION.labels(
        operation=operation,
        project=project,
        dry_run="true" if dry_run else "false",
    ).observe(max(seconds, 0.0))


def increment_operation_failure(operation: str, project: str, *, reason: str) -> None:
    """Increment the failure counter for the supplied reason."""

    _CACHE_OPERATION_FAILURES.labels(operation=operation, project=project, reason=reason or "unknown").inc()


def set_cache_size(project: str, size_bytes: int) -> None:
    """Update the cache size gauge for a project."""

    _CACHE_SIZE_BYTES.labels(project=project).set(max(size_bytes, 0))


def set_snapshot_count(project: str, count: int) -> None:
    """Record how many cache snapshots are retained for a project."""

    _CACHE_SNAPSHOT_COUNT.labels(project=project).set(max(count, 0))
