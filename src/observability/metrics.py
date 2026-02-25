"""
Prometheus metrics for the Entity Extraction layer.

All metrics are **optional**: if ``prometheus_client`` is not installed the
module configures itself with no-op stubs so the rest of the codebase never
needs to conditional-import.

Exported metrics
----------------
``ner_entities_per_mail``        histogram — entity count per mail, labelled by entity type
``ner_extraction_latency``       histogram — latency per pipeline component (seconds)
``ner_errors_total``             counter   — errors by type (soft/hard) and component
``ner_ner_skip_total``           counter   — NER engine skips by reason
``ner_pipeline_runs_total``      counter   — pipeline runs by outcome (ok/failed)

Reference: entity-extraction-layer.md §Metriche osservabili
"""
from __future__ import annotations

import logging
from typing import Any, Callable, ContextManager, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import prometheus-client; fall back to no-op stubs if missing
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Histogram  # type: ignore[import-untyped]

    _PROMETHEUS_AVAILABLE = True
    logger.debug("prometheus_client found; metrics enabled")
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus_client not installed; metrics are no-ops")

    class _NoOpLabels:  # type: ignore[no-redef]
        """No-op labels object returned by no-op metric stubs."""

        def inc(self, amount: float = 1) -> None:  # noqa: D401
            pass

        def observe(self, amount: float) -> None:
            pass

    class _NoOpMetric:  # type: ignore[no-redef]
        """No-op metric stub (Counter / Histogram)."""

        def labels(self, **_kwargs: Any) -> "_NoOpLabels":
            return _NoOpLabels()

        def inc(self, amount: float = 1) -> None:
            pass

        def observe(self, amount: float) -> None:
            pass

    def Counter(name: str, documentation: str, labelnames: list = []) -> "_NoOpMetric":  # type: ignore[no-redef]
        return _NoOpMetric()

    def Histogram(  # type: ignore[no-redef]
        name: str,
        documentation: str,
        labelnames: list = [],
        buckets: Any = None,
    ) -> "_NoOpMetric":
        return _NoOpMetric()


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

#: Number of entities extracted per mail, labelled by entity type.
ENTITIES_PER_MAIL: Any = Histogram(
    "ner_entities_per_mail",
    "Number of entities extracted per mail (histogram), by type",
    labelnames=["entity_type"],
    buckets=[0, 1, 2, 5, 10, 20, 50],
)

#: Latency (seconds) per named pipeline component.
EXTRACTION_LATENCY: Any = Histogram(
    "ner_extraction_latency_seconds",
    "Per-component extraction latency in seconds",
    labelnames=["component"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

#: Count of errors, labelled by type (soft/hard) and component.
ERRORS_TOTAL: Any = Counter(
    "ner_errors_total",
    "Total extraction errors by type (soft/hard) and component",
    labelnames=["error_type", "component"],
)

#: Count of NER engine skips, labelled by reason.
NER_SKIP_TOTAL: Any = Counter(
    "ner_ner_skip_total",
    "Count of times the NER engine was skipped, by reason",
    labelnames=["reason"],
)

#: Count of pipeline runs, labelled by outcome.
PIPELINE_RUNS: Any = Counter(
    "ner_pipeline_runs_total",
    "Total pipeline runs by outcome (ok/failed)",
    labelnames=["outcome"],
)


# ---------------------------------------------------------------------------
# Helper: context manager for timing a block
# ---------------------------------------------------------------------------


class _Timer:
    """Simple context manager that records elapsed time and emits Prometheus metric."""

    def __init__(self, component: str) -> None:
        self._component = component
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "_Timer":
        import time
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        import time
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        EXTRACTION_LATENCY.labels(component=self._component).observe(
            self.elapsed_ms / 1000
        )


def timer(component: str) -> _Timer:
    """Return a context manager that times a pipeline component and records latency."""
    return _Timer(component)


def record_entity_counts(entities: list, by_type: bool = True) -> None:
    """Record entity count metrics, optionally broken down by entity type."""
    if by_type:
        from collections import Counter as PyCounter
        counts = PyCounter(e.get("type", "UNKNOWN") if isinstance(e, dict) else e.label for e in entities)
        for entity_type, count in counts.items():
            ENTITIES_PER_MAIL.labels(entity_type=entity_type).observe(count)
    else:
        ENTITIES_PER_MAIL.labels(entity_type="ALL").observe(len(entities))
