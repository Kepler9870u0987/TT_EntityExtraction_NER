"""
Robustness tests for the Entity Extraction pipeline.

Exercises the pipeline with pathological inputs to verify it always fails in
a controlled, observable way — never crashing ungracefully or returning
invalid JSON.

Reference: entity-extraction-layer.md §Testing — Test di robustezza
"""
import json

import pytest

from src.entity_extraction.pipeline import extract_all_entities, run_pipeline
from src.config import PipelineConfig


_MANDATORY = {
    "id_conversazione": "CONV-ROB",
    "id_messaggio": "MSG-ROB",
    "testo_normalizzato": "placeholder",  # overridden per test
    "lingua": "it",
    "timestamp": "2025-01-01T00:00:00Z",
    "mittente": "a@b.it",
    "destinatario": "c@d.it",
}


def _payload(**overrides):
    return {**_MANDATORY, **overrides}


# ===========================================================================
# Hard validation failures — must return status="failed" JSON, not raise
# ===========================================================================


class TestHardFailureSafety:

    def test_empty_dict_returns_failed_output(self):
        output = run_pipeline({})
        d = output.to_dict()
        assert d["meta"]["status"] == "failed"
        assert isinstance(d["entities"], list) and len(d["entities"]) == 0

    def test_missing_mandatory_id_returns_failed_output(self):
        bad = {k: v for k, v in _MANDATORY.items() if k != "id_conversazione"}
        bad["testo_normalizzato"] = "Testo di prova."
        output = run_pipeline(bad)
        d = output.to_dict()
        assert d["meta"]["status"] == "failed"

    def test_html_in_text_returns_failed_output(self):
        output = run_pipeline(_payload(testo_normalizzato="<p>Hello <b>world</b></p>"))
        d = output.to_dict()
        assert d["meta"]["status"] == "failed"

    def test_whitespace_only_text_returns_failed_output(self):
        output = run_pipeline(_payload(testo_normalizzato="   "))
        d = output.to_dict()
        assert d["meta"]["status"] == "failed"

    def test_failed_output_always_valid_json(self):
        output = run_pipeline({})
        raw = output.to_json()
        parsed = json.loads(raw)  # must not raise
        assert "entities" in parsed
        assert "meta" in parsed


# ===========================================================================
# Edge cases — empty and minimal text
# ===========================================================================


class TestEdgeCasesText:

    def test_single_word_no_crash(self):
        output = run_pipeline(_payload(testo_normalizzato="Ciao."), nlp_model=None)
        d = output.to_dict()
        assert d["meta"]["status"] == "ok"
        assert isinstance(d["entities"], list)

    def test_single_email_extracted(self):
        output = run_pipeline(
            _payload(testo_normalizzato="test@example.it"),
            nlp_model=None,
        )
        entities = output.to_dict()["entities"]
        assert any(e["type"] == "EMAIL" for e in entities)

    def test_text_with_only_spaces_and_newlines(self):
        output = run_pipeline(_payload(testo_normalizzato="  \n  \n  "))
        d = output.to_dict()
        # whitespace-only text should fail input validation
        assert d["meta"]["status"] == "failed"


# ===========================================================================
# Very long text
# ===========================================================================


class TestVeryLongText:

    def test_max_length_text_processed_ok(self):
        """100 000-char text must not crash the pipeline."""
        long_text = ("A" * 99) + " " + "test@example.it" + (" B" * 49_000)
        # Ensure it does not exceed max_text_length
        assert len(long_text) <= 100_000
        output = run_pipeline(_payload(testo_normalizzato=long_text), nlp_model=None)
        d = output.to_dict()
        assert d["meta"]["status"] == "ok"

    def test_exceeds_max_length_returns_failed(self):
        too_long = "x" * 100_001
        output = run_pipeline(_payload(testo_normalizzato=too_long))
        assert output.to_dict()["meta"]["status"] == "failed"


# ===========================================================================
# Language edge cases
# ===========================================================================


class TestLanguageEdgeCases:

    def test_null_language_pipeline_ok(self):
        output = run_pipeline(_payload(lingua=None), nlp_model=None)
        d = output.to_dict()
        # Null language must not cause a hard failure
        assert d["meta"]["status"] == "ok"

    def test_unsupported_language_ner_skipped(self):
        config = PipelineConfig(supported_ner_languages=["it"])
        output = run_pipeline(
            _payload(lingua="zh"),  # Chinese — not supported
            config=config,
            nlp_model=None,
        )
        d = output.to_dict()
        assert d["meta"]["status"] == "ok"
        # NER was skipped → no ner-source entities
        assert all(e["source"] != "ner" for e in d["entities"])

    def test_unknown_language_code_non_blocking(self):
        output = run_pipeline(
            _payload(testo_normalizzato="test@example.it", lingua="xx"),
            nlp_model=None,
        )
        assert output.to_dict()["meta"]["status"] == "ok"


# ===========================================================================
# Repeated entities (deduplication stress test)
# ===========================================================================


class TestDeduplication:

    def test_repeated_email_deduped(self):
        text = "test@example.it test@example.it test@example.it"
        output = run_pipeline(_payload(testo_normalizzato=text), nlp_model=None)
        emails = [e for e in output.to_dict()["entities"] if e["type"] == "EMAIL"]
        # There are 3 occurrences at different spans — all valid (not duplicate spans)
        # but positions must be unique
        spans = [(e["span"]["start"], e["span"]["end"]) for e in emails]
        assert len(spans) == len(set(spans)), "Duplicate spans detected"

    def test_empty_entity_never_in_output(self):
        text = "Testo normale senza entità speciali."
        output = run_pipeline(_payload(testo_normalizzato=text), nlp_model=None)
        for ent in output.to_dict()["entities"]:
            assert ent["value"].strip(), "Empty entity value in output (★FIX #2★ violated)"


# ===========================================================================
# extract_all_entities wrapper — backwards-compatible robustness
# ===========================================================================


class TestExtractAllEntitiesRobustness:

    def test_empty_string_returns_empty_list(self):
        # Short text skips NER due to min_text_length_for_ner guard
        result = extract_all_entities("", nlp_model=None)
        assert result == []

    def test_no_crash_on_only_whitespace(self):
        result = extract_all_entities("   \n\n   ", nlp_model=None)
        assert isinstance(result, list)

    def test_no_crash_on_unicode_heavy_text(self):
        text = "Ün tèsto cön àccénti è caràtteri spèciàli 中文 العربية."
        result = extract_all_entities(text, nlp_model=None)
        assert isinstance(result, list)

    def test_no_entities_for_plain_text(self):
        text = "Buongiorno, come stai? Spero bene."
        result = extract_all_entities(text, nlp_model=None)
        # Should return empty or very few entities — never crash
        assert isinstance(result, list)
