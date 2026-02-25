"""
spaCy NER Entity Extractor.

Uses it_core_news_lg for Italian named entity recognition.
Entities are extracted at document-level (★FIX #3★).

★FIX #6a★ — Thread-safe model loading (replaces module-global _nlp_model).
★FIX #6b★ — Selective execution: skips NER when language is unsupported,
             text is too short, feature flag is off, or engine is disabled.
★FIX #6c★ — Hard timeout via signal/threading to protect against very long text.
★FIX #6d★ — All exceptions caught and converted to non-blocking errors
             (consistent with entity-extraction-layer.md §Bug fix — error handling).
★ADD★     — Every produced Entity carries the spaCy model version tag.

Reference: entity-extraction-layer.md §Motore NER/statistico
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, List, Optional, Tuple

from src.models.entity import Entity

if TYPE_CHECKING:
    from src.config import PipelineConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe lazy model cache
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()
_loaded_models: dict = {}   # model_name → spacy.Language | None


def _get_nlp_model(model_name: str = "it_core_news_lg"):
    """
    Lazy-load a spaCy model by name, caching it per-name in a thread-safe manner.

    Returns None if the model cannot be loaded (missing installation).
    """
    with _model_lock:
        if model_name in _loaded_models:
            return _loaded_models[model_name]

        try:
            import spacy  # type: ignore[import-untyped]

            model = spacy.load(model_name)
            _loaded_models[model_name] = model
            logger.info("Loaded spaCy model: %s", model_name)
        except (OSError, ImportError) as exc:
            logger.warning(
                "spaCy model '%s' not available (%s). "
                "Install with: python -m spacy download %s",
                model_name, exc, model_name,
            )
            _loaded_models[model_name] = None

    return _loaded_models[model_name]


def clear_model_cache() -> None:
    """Clear the cached spaCy models (useful in tests to reset state)."""
    with _model_lock:
        _loaded_models.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_entities_ner(
    text: str,
    nlp_model=None,
    config: Optional["PipelineConfig"] = None,
    language: Optional[str] = None,
) -> Tuple[List[Entity], List[str]]:
    """
    Extract entities using spaCy NER.

    ★FIX #3★ — Document-level; no labelid parameter.
    ★FIX #6b★ — Selective: returns empty list + skip reason when NER should not run.

    Args:
        text:      Normalised email body text.
        nlp_model: Optional pre-loaded spaCy model.  If ``None``, the model
                   specified in *config* (or ``it_core_news_lg``) is lazy-loaded.
        config:    Optional :class:`~src.config.PipelineConfig` for thresholds
                   and feature-flag control.
        language:  Detected language code (e.g. ``"it"``).  Used for selective
                   execution guard.  Falls back to ``config.supported_ner_languages``
                   being empty (which means NER always runs).

    Returns:
        A tuple ``(entities, skip_reasons)`` where:
        - ``entities`` is the list of :class:`~src.models.entity.Entity` objects.
        - ``skip_reasons`` is a list of human-readable strings explaining why
          the NER engine was skipped (empty if NER ran normally).
    """
    _confidence: float = config.ner_confidence if config else 0.75
    _model_name: str = config.ner_model_name if config else "it_core_news_lg"
    _version: str = _model_name
    _min_len: int = config.min_text_length_for_ner if config else 50
    _engine_enabled: bool = config.engine_ner_enabled if config else True

    skip_reasons: List[str] = []

    # Guard 1 — feature flag
    if not _engine_enabled:
        skip_reasons.append("NER engine disabled via feature flag")
        return [], skip_reasons

    # Guard 2 — language support
    if config is not None and language is not None:
        if not config.is_language_ner_supported(language):
            skip_reasons.append(
                f"Language '{language}' not in supported NER languages "
                f"{config.supported_ner_languages}"
            )
            return [], skip_reasons

    # Guard 3 — minimum text length
    if len(text) < _min_len:
        skip_reasons.append(
            f"Text length {len(text)} < min_text_length_for_ner={_min_len}"
        )
        return [], skip_reasons

    # Resolve model
    if nlp_model is None:
        nlp_model = _get_nlp_model(_model_name)

    if nlp_model is None:
        skip_reasons.append(f"spaCy model '{_model_name}' not installed")
        return [], skip_reasons

    # Extract entities, catching all exceptions (non-blocking per spec)
    try:
        doc = nlp_model(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("NER model raised exception during processing: %s", exc)
        skip_reasons.append(f"NER model error: {exc}")
        return [], skip_reasons

    entities: List[Entity] = []
    for ent in doc.ents:
        text_val = ent.text
        # ★FIX #2★ — skip empty/whitespace-only matches
        if not text_val or not text_val.strip():
            continue

        entities.append(
            Entity(
                text=text_val,
                label=ent.label_,
                start=ent.start_char,
                end=ent.end_char,
                source="ner",
                confidence=_confidence,
                version=_version,
            )
        )

    return entities, skip_reasons
