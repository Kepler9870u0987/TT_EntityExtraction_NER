"""
Structured logging for the Entity Extraction layer.

Uses Python's standard ``logging`` module with a JSON-structured formatter
so logs are consumable by ELK / Datadog / any structured-log aggregator
without fragile text parsing.

If ``structlog`` is installed it is used instead for richer context binding.
Falls back to a plain ``logging.Formatter`` otherwise (zero hard dependency).

Reference: entity-extraction-layer.md §Logging strutturato
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# JSON formatter (stdlib-only fallback)
# ---------------------------------------------------------------------------


class _JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach any extra fields bound via LogRecord.__dict__
        for key, value in record.__dict__.items():
            if key.startswith("ctx_") or key in (
                "id_conversazione", "id_messaggio", "trace_id"
            ):
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return json.dumps({"message": str(payload)})


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------


def get_logger(name: str = "entity_extraction") -> logging.Logger:
    """
    Return a logger that emits JSON-structured output to stdout.

    Idempotent: repeated calls with the same *name* return the same logger.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Context-enriched log helper
# ---------------------------------------------------------------------------


class PipelineLogger:
    """
    Thin wrapper around :class:`logging.Logger` that prepends conversation /
    message context to every log record.

    Usage::

        log = PipelineLogger("MSG-001", "CONV-001")
        log.info("step_complete", step="regex", entities_found=3)
    """

    def __init__(
        self,
        id_messaggio: str,
        id_conversazione: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or get_logger()
        self._ctx: Dict[str, str] = {
            "id_messaggio": id_messaggio,
            "id_conversazione": id_conversazione,
        }

    def _log(self, level: int, event: str, **extra: Any) -> None:
        extra.update(self._ctx)
        self._logger.log(level, event, extra=extra)

    def debug(self, event: str, **kw: Any) -> None:
        self._log(logging.DEBUG, event, **kw)

    def info(self, event: str, **kw: Any) -> None:
        self._log(logging.INFO, event, **kw)

    def warning(self, event: str, **kw: Any) -> None:
        self._log(logging.WARNING, event, **kw)

    def error(self, event: str, **kw: Any) -> None:
        self._log(logging.ERROR, event, **kw)

    def log_entity_summary(self, entities: List[Dict[str, Any]]) -> None:
        """Log a compact summary of extracted entities grouped by type and source."""
        summary: Dict[str, Dict[str, int]] = {}
        for ent in entities:
            label = ent.get("type", "UNKNOWN")
            source = ent.get("source", "unknown")
            summary.setdefault(label, {}).setdefault(source, 0)
            summary[label][source] += 1

        self.info(
            "entity_extraction_complete",
            entity_summary=summary,
            total_entities=len(entities),
        )

    def log_fallback(self, component: str, reason: str) -> None:
        """Log a fallback activation in a structured way."""
        self.warning(
            "fallback_activated",
            component=component,
            reason=reason,
        )
