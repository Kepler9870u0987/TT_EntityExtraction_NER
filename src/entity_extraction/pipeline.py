"""
Entity Extraction Pipeline — full 7-step orchestration.

Implements the complete processing flow defined in
entity-extraction-layer.md §Flusso di elaborazione:

  Step 1. Input validation (mandatory fields, data types, size limits)
  Step 2. Soft text normalisation (trim, dedup-spaces, NFKC, …)
  Step 3. Rule-based engine (regex) — always runs if feature flag active
  Step 4. Selective NER engine (spaCy) — only if language/length/flag OK
  Step 5. Lexicon enhancement (gazetteer) — if feature flag active
  Step 6. Deterministic entity merge + dedup
  Step 7. Post-filters (empty-value, blacklist, type-flags, canonical format)
          → serialise to ExtractionOutput JSON envelope

The pipeline is **side-effect free** (no DB writes, no external calls in the
critical path) except for structured logging and Prometheus metrics increments.

A global try/except guarantees that the function **always** returns a valid
:class:`~src.models.output_schema.ExtractionOutput`, even on hard failure
(``meta.status`` will be ``"failed"`` and ``entities`` will be empty).

Reference: entity-extraction-layer.md §Flusso di elaborazione
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union

from src.config import LAYER_VERSION, PipelineConfig
from src.entity_extraction.input_validator import InputValidationError, validate_input
from src.entity_extraction.lexicon_enhancer import enhance_ner_with_lexicon
from src.entity_extraction.merger import merge_entities_deterministic
from src.entity_extraction.ner_extractor import extract_entities_ner
from src.entity_extraction.normalizer import normalize_text
from src.entity_extraction.post_filters import apply_all_filters
from src.entity_extraction.regex_matcher import DEFAULT_REGEX_LEXICON, extract_entities_regex
from src.models.entity import Entity
from src.models.input_schema import ExtractionInput
from src.models.output_schema import ExtractionOutput
from src.observability.logging import PipelineLogger
from src.observability.metrics import (
    ERRORS_TOTAL,
    NER_SKIP_TOTAL,
    PIPELINE_RUNS,
    record_entity_counts,
    timer,
)

logger = logging.getLogger(__name__)


def run_pipeline(
    raw_input: Union[dict, ExtractionInput],
    regex_lexicon: Optional[Dict[str, List[dict]]] = None,
    ner_lexicon: Optional[Dict[str, List[dict]]] = None,
    nlp_model=None,
    config: Optional[PipelineConfig] = None,
) -> ExtractionOutput:
    """
    Execute the full 7-step Entity Extraction pipeline.

    Args:
        raw_input:     Either a raw ``dict`` (validated internally) or a
                       pre-validated :class:`~src.models.input_schema.ExtractionInput`.
        regex_lexicon: Regex pattern lexicon. Defaults to :data:`DEFAULT_REGEX_LEXICON`.
        ner_lexicon:   Gazetteer lexicon. Defaults to empty (no gazetteer matching).
        nlp_model:     Pre-loaded spaCy model.  ``None`` → lazy-loaded per config.
        config:        Runtime configuration.  ``None`` → :meth:`PipelineConfig.default`.

    Returns:
        An :class:`~src.models.output_schema.ExtractionOutput` that is always
        serialisable to valid JSON.  On hard failure ``meta.status == "failed"``.
    """
    if config is None:
        config = PipelineConfig.default()

    # Determine IDs early for logging/output envelope (may be unknown on hard failure)
    _id_conv = "UNKNOWN"
    _id_msg = "UNKNOWN"

    try:
        # ------------------------------------------------------------------
        # Step 1 — Input validation
        # ------------------------------------------------------------------
        with timer("step1_validation") as t1:
            if isinstance(raw_input, ExtractionInput):
                parsed = raw_input
                input_warnings: List[Dict] = []
            else:
                parsed, input_warnings = validate_input(raw_input)

        _id_conv = parsed.id_conversazione
        _id_msg = parsed.id_messaggio

        output = ExtractionOutput(
            id_conversazione=_id_conv,
            id_messaggio=_id_msg,
            layer_version=LAYER_VERSION,
            feature_flags={
                "engine_regex": config.engine_regex_enabled,
                "engine_ner": config.engine_ner_enabled,
                "engine_lexicon": config.engine_lexicon_enabled,
            },
        )
        output.record_timing("step1_validation", t1.elapsed_ms)

        pipe_log = PipelineLogger(
            id_messaggio=_id_msg,
            id_conversazione=_id_conv,
        )

        # Propagate non-blocking input warnings
        for w in input_warnings:
            output.add_error("input_validator", w["message"])
            ERRORS_TOTAL.labels(error_type="soft", component="input_validator").inc()

        # ------------------------------------------------------------------
        # Step 2 — Soft text normalisation
        # ------------------------------------------------------------------
        with timer("step2_normalisation") as t2:
            normalised_text, norm_log = normalize_text(parsed.testo_normalizzato)
        output.record_timing("step2_normalisation", t2.elapsed_ms)
        pipe_log.debug("text_normalised", norm_steps=len(norm_log.steps))

        # ------------------------------------------------------------------
        # Step 3 — Rule-based (regex) engine
        # ------------------------------------------------------------------
        regex_entities: List[Entity] = []
        if config.engine_regex_enabled:
            _lexicon = regex_lexicon if regex_lexicon is not None else DEFAULT_REGEX_LEXICON
            with timer("step3_regex") as t3:
                regex_entities = extract_entities_regex(
                    normalised_text, _lexicon, config=config
                )
            output.record_timing("step3_regex", t3.elapsed_ms)
            pipe_log.debug("regex_done", count=len(regex_entities))
        else:
            output.add_fallback("Regex engine skipped (feature flag off)")
            pipe_log.log_fallback("regex", "feature flag disabled")

        # ------------------------------------------------------------------
        # Step 4 — Selective NER engine
        # ------------------------------------------------------------------
        ner_entities: List[Entity] = []
        if config.engine_ner_enabled:
            with timer("step4_ner") as t4:
                ner_entities, skip_reasons = extract_entities_ner(
                    normalised_text,
                    nlp_model=nlp_model,
                    config=config,
                    language=parsed.lingua,
                )
            output.record_timing("step4_ner", t4.elapsed_ms)

            for reason in skip_reasons:
                output.add_fallback(f"NER skipped: {reason}")
                pipe_log.log_fallback("ner", reason)
                NER_SKIP_TOTAL.labels(reason=_normalise_skip_reason(reason)).inc()

            pipe_log.debug("ner_done", count=len(ner_entities), skipped=bool(skip_reasons))
        else:
            output.add_fallback("NER engine skipped (feature flag off)")
            pipe_log.log_fallback("ner", "feature flag disabled")
            NER_SKIP_TOTAL.labels(reason="feature_flag_disabled").inc()

        # ------------------------------------------------------------------
        # Step 5 — Lexicon / gazetteer enhancement
        # ------------------------------------------------------------------
        _ner_lexicon = ner_lexicon if ner_lexicon is not None else {}
        with timer("step5_lexicon") as t5:
            enhanced_entities = enhance_ner_with_lexicon(
                ner_entities, _ner_lexicon, normalised_text, config=config
            )
        output.record_timing("step5_lexicon", t5.elapsed_ms)
        lexicon_new = len(enhanced_entities) - len(ner_entities)
        pipe_log.debug("lexicon_done", new_entities=lexicon_new)

        # ------------------------------------------------------------------
        # Step 6 — Deterministic merge
        # ------------------------------------------------------------------
        all_candidates = regex_entities + enhanced_entities
        with timer("step6_merge") as t6:
            merged = merge_entities_deterministic(all_candidates, config=config)
        output.record_timing("step6_merge", t6.elapsed_ms)
        pipe_log.debug("merge_done", count=len(merged))

        # ------------------------------------------------------------------
        # Step 7 — Post-filters + serialisation
        # ------------------------------------------------------------------
        with timer("step7_filters") as t7:
            filtered = apply_all_filters(
                merged,
                blacklist=config.blacklist_values,
                entity_types_enabled=config.entity_types_enabled,
            )
        output.record_timing("step7_filters", t7.elapsed_ms)

        entity_dicts = [e.to_dict() for e in filtered]
        output.set_entities(entity_dicts)

        # ------------------------------------------------------------------
        # Observability
        # ------------------------------------------------------------------
        record_entity_counts(entity_dicts, by_type=True)
        pipe_log.log_entity_summary(entity_dicts)
        PIPELINE_RUNS.labels(outcome="ok").inc()

    except InputValidationError as exc:
        # Hard failure: mandatory input fields are missing/invalid
        _output = _make_failed_output(_id_conv, _id_msg, f"Input validation failed: {exc}")
        ERRORS_TOTAL.labels(error_type="hard", component="input_validator").inc()
        PIPELINE_RUNS.labels(outcome="failed").inc()
        logger.error("Pipeline hard failure (input validation): %s", exc)
        return _output

    except Exception as exc:  # noqa: BLE001
        # Unexpected hard failure — always return valid JSON
        _output = _make_failed_output(_id_conv, _id_msg, f"Unexpected error: {exc}")
        ERRORS_TOTAL.labels(error_type="hard", component="pipeline").inc()
        PIPELINE_RUNS.labels(outcome="failed").inc()
        logger.exception("Pipeline unexpected hard failure: %s", exc)
        return _output

    return output


# ---------------------------------------------------------------------------
# Backwards-compatible thin wrapper (document-level, keeps old signature)
# ---------------------------------------------------------------------------


def extract_all_entities(
    text: str,
    regex_lexicon: Optional[Dict[str, List[dict]]] = None,
    ner_lexicon: Optional[Dict[str, List[dict]]] = None,
    nlp_model=None,
    config: Optional[PipelineConfig] = None,
) -> List[Entity]:
    """
    Backwards-compatible document-level extraction returning ``List[Entity]``.

    ★FIX #3★ — No labelid parameter (document-level).

    This is a thin wrapper around :func:`run_pipeline` that accepts a plain
    text string (without the full input envelope) and returns a flat list of
    :class:`~src.models.entity.Entity` objects instead of an
    :class:`~src.models.output_schema.ExtractionOutput`.

    For production use, prefer :func:`run_pipeline` which returns the full
    JSON contract with meta/errors.

    Args:
        text:          Plain email body text.
        regex_lexicon: Regex pattern lexicon (defaults to built-in).
        ner_lexicon:   Gazetteer lexicon (defaults to empty).
        nlp_model:     Pre-loaded spaCy model (``None`` → lazy-loaded).
        config:        Runtime configuration.

    Returns:
        Merged, deduplicated list of :class:`~src.models.entity.Entity` objects.
    """
    if config is None:
        config = PipelineConfig.default()

    if regex_lexicon is None:
        regex_lexicon = DEFAULT_REGEX_LEXICON
    if ner_lexicon is None:
        ner_lexicon = {}

    # Step 3 — Regex
    regex_entities: List[Entity] = []
    if config.engine_regex_enabled:
        regex_entities = extract_entities_regex(text, regex_lexicon, config=config)

    # Step 4 — NER (selective)
    ner_entities: List[Entity] = []
    if config.engine_ner_enabled:
        ner_entities, _ = extract_entities_ner(
            text, nlp_model=nlp_model, config=config, language=None
        )

    # Step 5 — Lexicon enhancement
    enhanced_entities = enhance_ner_with_lexicon(
        ner_entities, ner_lexicon, text, config=config
    )

    # Step 6 — Merge
    all_candidates = regex_entities + enhanced_entities
    merged = merge_entities_deterministic(all_candidates, config=config)

    # Step 7 — Post-filters
    filtered = apply_all_filters(
        merged,
        blacklist=config.blacklist_values,
        entity_types_enabled=config.entity_types_enabled,
    )

    return filtered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_failed_output(
    id_conv: str, id_msg: str, reason: str
) -> ExtractionOutput:
    """Build a hard-failure output envelope."""
    out = ExtractionOutput(
        id_conversazione=id_conv,
        id_messaggio=id_msg,
        layer_version=LAYER_VERSION,
    )
    out.set_failed(reason)
    return out


def _normalise_skip_reason(reason: str) -> str:
    """Normalise a skip reason string to a Prometheus-label-safe key."""
    if "feature flag" in reason.lower():
        return "feature_flag_disabled"
    if "language" in reason.lower():
        return "unsupported_language"
    if "length" in reason.lower():
        return "text_too_short"
    if "not installed" in reason.lower() or "not available" in reason.lower():
        return "model_not_installed"
    if "error" in reason.lower():
        return "model_error"
    return "other"
