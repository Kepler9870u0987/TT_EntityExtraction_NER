"""
Output schema for the Entity Extraction pipeline.

Produces a structured JSON envelope with ``entities``, ``meta``, and
``errors`` sections. The envelope is **always valid JSON** even on hard
failure (``entities`` is empty, ``meta.status`` is ``"failed"``).

Reference: entity-extraction-layer.md §Contratto di output
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional


class ExtractionOutput:
    """
    Mutable output object built incrementally by the pipeline orchestrator.

    Serialised via :meth:`to_dict` / :meth:`to_json` once processing is complete.
    """

    def __init__(
        self,
        id_conversazione: str,
        id_messaggio: str,
        layer_version: str,
        feature_flags: Optional[Dict[str, bool]] = None,
    ) -> None:
        self._id_conversazione = id_conversazione
        self._id_messaggio = id_messaggio
        self._layer_version = layer_version
        self._feature_flags: Dict[str, bool] = feature_flags or {}

        self._entities: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, str]] = []
        self._fallbacks: List[str] = []
        self._status: str = "ok"

        # Component-level timings (ms)
        self._timings: Dict[str, float] = {}
        self._start_ts: float = time.perf_counter()

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def set_entities(self, entities: List[Dict[str, Any]]) -> None:
        """Set the final list of serialised entity dicts."""
        self._entities = entities

    def add_error(self, component: str, message: str) -> None:
        """
        Record a **non-blocking** error.

        Non-blocking means the pipeline continues and returns partial results.
        """
        self._errors.append({"component": component, "message": message})

    def add_fallback(self, description: str) -> None:
        """Register a fallback activation (e.g. NER model not available)."""
        self._fallbacks.append(description)

    def set_failed(self, reason: str) -> None:
        """Mark the extraction as hard-failed. ``entities`` will be empty."""
        self._status = "failed"
        self._entities = []
        self._errors.append({"component": "pipeline", "message": reason})

    def record_timing(self, component: str, elapsed_ms: float) -> None:
        """Record elapsed milliseconds for a named pipeline component."""
        self._timings[component] = round(elapsed_ms, 3)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict representing the full output contract."""
        total_ms = round((time.perf_counter() - self._start_ts) * 1000, 3)
        return {
            "entities": self._entities,
            "meta": {
                "id_conversazione": self._id_conversazione,
                "id_messaggio": self._id_messaggio,
                "status": self._status,
                "layer_version": self._layer_version,
                "processing_time_ms": total_ms,
                "component_timings_ms": self._timings,
                "feature_flags": self._feature_flags,
                "fallbacks": self._fallbacks,
                "entity_count": len(self._entities),
            },
            "errors": self._errors,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        """Serialise to a JSON string. Always succeeds (safe fallback on error)."""
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
        except Exception as exc:  # noqa: BLE001
            # Last-resort safe envelope
            return json.dumps({
                "entities": [],
                "meta": {
                    "id_conversazione": self._id_conversazione,
                    "id_messaggio": self._id_messaggio,
                    "status": "failed",
                    "layer_version": self._layer_version,
                    "processing_time_ms": 0.0,
                    "component_timings_ms": {},
                    "feature_flags": {},
                    "fallbacks": [],
                    "entity_count": 0,
                },
                "errors": [{"component": "serialiser", "message": str(exc)}],
            }, ensure_ascii=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ExtractionOutput(status={self._status!r},"
            f" entities={len(self._entities)},"
            f" errors={len(self._errors)})"
        )
