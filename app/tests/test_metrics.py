"""Regression tests for the Prometheus metric helpers."""

from __future__ import annotations

import unittest

from prometheus_client import Counter, REGISTRY

from app.app import metrics


class MetricsHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        metrics.reset_metrics_registry()

    def tearDown(self) -> None:
        metrics.reset_metrics_registry()

    def test_get_or_create_metric_returns_singleton(self) -> None:
        first = metrics._get_or_create_metric(  # type: ignore[attr-defined]
            Counter,
            "codex_test_cache_metric_total",
            "Test counter for singleton reuse verification.",
        )
        second = metrics._get_or_create_metric(  # type: ignore[attr-defined]
            Counter,
            "codex_test_cache_metric_total",
            "Test counter for singleton reuse verification.",
        )

        self.assertIs(first, second)

    def test_get_or_create_metric_rejects_existing_registry_metric(self) -> None:
        external_counter = Counter(
            "codex_test_registry_metric_total",
            "Metric registered outside of the metrics helper module.",
        )
        self.addCleanup(lambda: REGISTRY.unregister(external_counter))

        with self.assertRaises(metrics.MetricRegistrationError):
            metrics._get_or_create_metric(  # type: ignore[attr-defined]
                Counter,
                "codex_test_registry_metric_total",
                "Metric registered outside of the metrics helper module.",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
