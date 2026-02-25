"""
Integration / E2E tests for the Entity Extraction pipeline.

These tests execute the full 7-step pipeline against realistic (sanitised)
Italian email payloads and assert on the complete output contract
(entities + meta + errors).

Reference: entity-extraction-layer.md §Testing — Test di integrazione
"""
import json

import pytest

from src.entity_extraction.pipeline import run_pipeline
from src.config import PipelineConfig, LAYER_VERSION

# ---------------------------------------------------------------------------
# Fixture: realistic sanitised Italian email payload
# ---------------------------------------------------------------------------

SAMPLE_EMAIL = {
    "id_conversazione": "CONV-E2E-001",
    "id_messaggio": "MSG-E2E-001",
    "testo_normalizzato": (
        "Gentile supporto,\n\n"
        "sono Mario Rossi (codice fiscale: RSSMRA85M01H501Z). "
        "Vi scrivo riguardo alla pratica PRAT2025001234 relativa al mutuo.\n\n"
        "Potete rispondermi a mario.rossi@example.it oppure chiamatemi al +39 333 123 4567.\n\n"
        "Ho effettuato un bonifico il 10/03/2025 di € 1.500,00 "
        "sul conto IT60 X054 2811 1010 0000 0123 456.\n\n"
        "L'azienda ACME S.p.A. ha ricevuto conferma.\n\n"
        "Cordiali saluti,\nMario Rossi"
    ),
    "lingua": "it",
    "timestamp": "2025-03-10T09:00:00Z",
    "mittente": "mario.rossi@example.it",
    "destinatario": "supporto@banca.it",
}

SAMPLE_LEXICON = {
    "AZIENDA": [
        {"lemma": "ACME", "surface_forms": ["ACME", "ACME S.p.A."]},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(payload=None, ner_lexicon=None, config=None):
    return run_pipeline(
        payload or SAMPLE_EMAIL,
        ner_lexicon=ner_lexicon or SAMPLE_LEXICON,
        nlp_model=None,
        config=config,
    )


def _entities(output):
    return output.to_dict()["entities"]


def _meta(output):
    return output.to_dict()["meta"]


# ---------------------------------------------------------------------------
# Output contract tests
# ---------------------------------------------------------------------------


class TestOutputContract:

    def test_output_always_json_serialisable(self):
        output = _run()
        raw = output.to_json()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_output_has_three_top_level_keys(self):
        output = _run()
        d = output.to_dict()
        assert set(d.keys()) >= {"entities", "meta", "errors"}

    def test_entities_is_list(self):
        output = _run()
        assert isinstance(_entities(output), list)

    def test_meta_status_ok(self):
        output = _run()
        assert _meta(output)["status"] == "ok"

    def test_meta_layer_version_present(self):
        output = _run()
        assert _meta(output)["layer_version"] == LAYER_VERSION

    def test_meta_processing_time_positive(self):
        output = _run()
        assert _meta(output)["processing_time_ms"] > 0

    def test_meta_entity_count_matches_entities(self):
        output = _run()
        d = output.to_dict()
        assert d["meta"]["entity_count"] == len(d["entities"])

    def test_errors_is_list(self):
        output = _run()
        assert isinstance(output.to_dict()["errors"], list)


# ---------------------------------------------------------------------------
# Entity field structure tests
# ---------------------------------------------------------------------------


class TestEntityFields:

    def test_every_entity_has_required_fields(self):
        output = _run()
        required = {"type", "value", "span", "confidence", "source", "version"}
        for ent in _entities(output):
            assert required <= set(ent.keys()), f"Missing fields in: {ent}"

    def test_span_has_start_end(self):
        output = _run()
        for ent in _entities(output):
            assert "start" in ent["span"]
            assert "end" in ent["span"]
            assert ent["span"]["end"] > ent["span"]["start"]

    def test_confidence_in_range(self):
        output = _run()
        for ent in _entities(output):
            assert 0.0 <= ent["confidence"] <= 1.0, f"Out-of-range confidence: {ent}"

    def test_source_valid_values(self):
        valid_sources = {"regex", "ner", "lexicon"}
        output = _run()
        for ent in _entities(output):
            assert ent["source"] in valid_sources, f"Unknown source: {ent['source']}"

    def test_no_empty_values(self):
        output = _run()
        for ent in _entities(output):
            assert ent["value"] and ent["value"].strip(), f"Empty value in: {ent}"


# ---------------------------------------------------------------------------
# Specific entity extraction correctness
# ---------------------------------------------------------------------------


class TestExtractionCorrectness:

    def test_email_extracted(self):
        output = _run()
        emails = [e for e in _entities(output) if e["type"] == "EMAIL"]
        assert len(emails) >= 1
        assert any("mario.rossi" in e["value"] for e in emails)

    def test_codice_fiscale_extracted(self):
        output = _run()
        cfs = [e for e in _entities(output) if e["type"] == "CODICEFISCALE"]
        assert len(cfs) >= 1
        assert cfs[0]["value"] == "RSSMRA85M01H501Z"

    def test_data_extracted_and_normalised(self):
        output = _run()
        dates = [e for e in _entities(output) if e["type"] == "DATA"]
        assert len(dates) >= 1
        # Should be ISO 8601 after canonical normalisation
        assert any(e["value"] == "2025-03-10" for e in dates)

    def test_importo_extracted(self):
        output = _run()
        importi = [e for e in _entities(output) if e["type"] == "IMPORTO"]
        assert len(importi) >= 1

    def test_azienda_extracted_via_lexicon(self):
        output = _run()
        aziende = [e for e in _entities(output) if e["type"] == "AZIENDA"]
        assert len(aziende) >= 1
        assert any("ACME" in e["value"] for e in aziende)

    def test_lexicon_entity_label_is_category(self):
        """★FIX #7★ — Lexicon entity label must be 'AZIENDA', not 'ACME'."""
        output = _run()
        for ent in _entities(output):
            if "ACME" in ent["value"] and ent["source"] == "lexicon":
                assert ent["type"] == "AZIENDA", (
                    f"Expected 'AZIENDA' got '{ent['type']}' for {ent['value']}"
                )


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


class TestFeatureFlags:

    def test_regex_disabled_no_regex_entities(self):
        config = PipelineConfig(engine_regex_enabled=False)
        output = _run(config=config)
        for ent in _entities(output):
            assert ent["source"] != "regex"

    def test_lexicon_disabled_no_lexicon_entities(self):
        config = PipelineConfig(engine_lexicon_enabled=False)
        output = _run(config=config)
        for ent in _entities(output):
            assert ent["source"] != "lexicon"

    def test_email_type_disabled(self):
        config = PipelineConfig(
            entity_types_enabled={"EMAIL": False}
        )
        output = _run(config=config)
        assert all(e["type"] != "EMAIL" for e in _entities(output))

    def test_blacklisted_value_absent_from_output(self):
        config = PipelineConfig(blacklist_values=["mario.rossi@example.it"])
        output = _run(config=config)
        assert all(
            e["value"].lower() != "mario.rossi@example.it"
            for e in _entities(output)
        )


# ---------------------------------------------------------------------------
# Non-regression snapshot test
# ---------------------------------------------------------------------------


class TestSnapshotNonRegression:
    """
    Lightweight non-regression test: the set of entity types extracted from
    the reference email must remain stable across releases.

    If this test fails it means a code change inadvertently altered extraction
    behaviour — update the snapshot only after deliberate review.
    """

    EXPECTED_TYPES = {"EMAIL", "CODICEFISCALE", "DATA", "IMPORTO", "AZIENDA"}

    def test_expected_entity_types_present(self):
        output = _run()
        found_types = {e["type"] for e in _entities(output)}
        missing = self.EXPECTED_TYPES - found_types
        assert not missing, f"Regression: these entity types are no longer extracted: {missing}"
