"""
Unit tests for entity extraction (★FIX #3★ — document-level).
Tests: Entity model, regex_matcher, lexicon_enhancer, merger, pipeline.

All fixtures (mock_regex_lexicon, mock_ner_lexicon, sample_input_dict)
are defined in tests/conftest.py.
"""
import pytest

from src.entity_extraction.lexicon_enhancer import enhance_ner_with_lexicon
from src.entity_extraction.merger import merge_entities_deterministic
from src.entity_extraction.pipeline import extract_all_entities, run_pipeline
from src.entity_extraction.regex_matcher import extract_entities_regex
from src.models.entity import Entity


# ===========================================================================
# Entity model
# ===========================================================================


class TestEntityModel:
    """Tests for the Entity dataclass."""

    def test_to_dict_structure(self):
        e = Entity("test@example.it", "EMAIL", 0, 15, "regex", 0.95, "regex-v1.0")
        d = e.to_dict()
        assert d["type"] == "EMAIL"
        assert d["value"] == "test@example.it"
        assert d["span"] == {"start": 0, "end": 15}
        assert d["confidence"] == 0.95
        assert d["source"] == "regex"
        assert d["version"] == "regex-v1.0"

    def test_from_dict_roundtrip(self):
        e = Entity("RSSMRA85M01H501Z", "CODICEFISCALE", 5, 21, "regex", 0.95, "regex-v1.0")
        restored = Entity.from_dict(e.to_dict())
        assert restored.text == e.text
        assert restored.label == e.label
        assert restored.start == e.start
        assert restored.end == e.end
        assert restored.source == e.source
        assert restored.version == e.version

    def test_is_valid_non_empty(self):
        assert Entity("hello", "L", 0, 5, "regex").is_valid()

    def test_is_valid_empty_text(self):
        assert not Entity("", "L", 0, 0, "regex").is_valid()

    def test_is_valid_whitespace_only(self):
        assert not Entity("   ", "L", 0, 3, "regex").is_valid()

    def test_frozen_immutable(self):
        e = Entity("hello", "L", 0, 5, "regex")
        with pytest.raises((AttributeError, TypeError)):
            e.text = "mutated"  # type: ignore[misc]

    def test_version_default_empty(self):
        e = Entity("hello", "L", 0, 5, "regex")
        assert e.version == ""


# ===========================================================================
# Entity overlaps
# ===========================================================================


class TestEntityOverlaps:
    """Tests for Entity.overlaps() method."""

    def test_no_overlap(self):
        e1 = Entity("a", "L", 0, 5, "regex")
        e2 = Entity("b", "L", 10, 15, "regex")
        assert not e1.overlaps(e2)
        assert not e2.overlaps(e1)

    def test_overlap(self):
        e1 = Entity("a", "L", 0, 10, "regex")
        e2 = Entity("b", "L", 5, 15, "regex")
        assert e1.overlaps(e2)
        assert e2.overlaps(e1)

    def test_contained(self):
        e1 = Entity("a", "L", 0, 20, "regex")
        e2 = Entity("b", "L", 5, 10, "regex")
        assert e1.overlaps(e2)
        assert e2.overlaps(e1)

    def test_adjacent_no_overlap(self):
        e1 = Entity("a", "L", 0, 5, "regex")
        e2 = Entity("b", "L", 5, 10, "regex")
        assert not e1.overlaps(e2)


# ===========================================================================
# RegexMatcher
# ===========================================================================


class TestRegexMatcher:
    """Tests for extract_entities_regex."""

    def test_email_extraction(self, mock_regex_lexicon):
        text = "Contattami a mario.rossi@example.it per info."
        entities = extract_entities_regex(text, mock_regex_lexicon)

        emails = [e for e in entities if e.label == "EMAIL"]
        assert len(emails) == 1
        assert emails[0].text == "mario.rossi@example.it"
        assert emails[0].source == "regex"
        assert emails[0].confidence == 0.95

    def test_codice_fiscale_extraction(self, mock_regex_lexicon):
        text = "Il codice fiscale è RSSMRA85M01H501Z, grazie."
        entities = extract_entities_regex(text, mock_regex_lexicon)

        cfs = [e for e in entities if e.label == "CODICEFISCALE"]
        assert len(cfs) == 1
        assert cfs[0].text == "RSSMRA85M01H501Z"

    def test_no_match_returns_empty(self, mock_regex_lexicon):
        text = "Buongiorno, nessuna entità riconoscibile qui."
        entities = extract_entities_regex(text, mock_regex_lexicon)
        assert len(entities) == 0

    def test_invalid_regex_skipped(self):
        bad_lexicon = {
            "BAD": [{"regex_pattern": r"[invalid(", "label": "BAD"}],
        }
        text = "Some text"
        entities = extract_entities_regex(text, bad_lexicon)
        assert len(entities) == 0  # No crash, just skipped

    def test_entity_carries_version(self, mock_regex_lexicon):
        text = "mario.rossi@example.it"
        entities = extract_entities_regex(text, mock_regex_lexicon)
        assert all(isinstance(e.version, str) for e in entities)

    def test_empty_match_skipped(self):
        """Patterns that match empty strings must not produce entities (★FIX #2★)."""
        # A pattern that can match the empty string
        lexicon = {"TEST": [{"regex_pattern": r"x*", "label": "TEST"}]}
        text = "hello world"
        entities = extract_entities_regex(text, lexicon)
        # All produced entities must have non-empty text
        assert all(e.is_valid() for e in entities)

    def test_importo_extraction(self, mock_regex_lexicon):
        text = "L'importo è € 1.500,00."
        entities = extract_entities_regex(text, mock_regex_lexicon)
        importi = [e for e in entities if e.label == "IMPORTO"]
        assert len(importi) >= 1

    def test_data_extraction(self, mock_regex_lexicon):
        text = "Scadenza il 15/03/2025 prossimo."
        entities = extract_entities_regex(text, mock_regex_lexicon)
        dates = [e for e in entities if e.label == "DATA"]
        assert len(dates) >= 1
        assert "15" in dates[0].text


# ===========================================================================
# LexiconEnhancer
# ===========================================================================


class TestLexiconEnhancer:
    """Tests for enhance_ner_with_lexicon."""

    def test_lexicon_match(self, mock_ner_lexicon):
        text = "L'azienda ACME ha inviato la fattura."
        enhanced = enhance_ner_with_lexicon([], mock_ner_lexicon, text)

        acme_entities = [e for e in enhanced if "ACME" in e.text]
        assert len(acme_entities) >= 1
        assert acme_entities[0].source == "lexicon"
        assert acme_entities[0].confidence == 0.85

    def test_label_is_category_not_lemma(self, mock_ner_lexicon):
        """★FIX #7★ — label must be 'AZIENDA', not 'ACME'."""
        text = "L'azienda ACME ha confermato."
        enhanced = enhance_ner_with_lexicon([], mock_ner_lexicon, text)
        acme = [e for e in enhanced if "ACME" in e.text]
        assert acme, "Expected at least one ACME entity"
        # ★FIX #7★: label must be the CATEGORY key, not the lemma
        assert acme[0].label == "AZIENDA", (
            f"Expected label='AZIENDA', got label='{acme[0].label}'. "
            "This was a bug where label=lemma instead of label=entity_label."
        )

    def test_word_boundary_respected(self, mock_ner_lexicon):
        text = "La parola ACMEEXTRA non è ACME."
        enhanced = enhance_ner_with_lexicon([], mock_ner_lexicon, text)

        # Should match "ACME" at end but NOT inside "ACMEEXTRA"
        acme_exact = [e for e in enhanced if e.text == "ACME"]
        assert len(acme_exact) >= 1

        # The ACMEEXTRA substring should NOT be matched as ACME
        all_starts = [e.start for e in enhanced if "ACME" in e.text]
        assert all(text[s: s + 4] == "ACME" and (s == 0 or not text[s - 1].isalnum())
                   for s in all_starts)

    def test_preserves_existing_entities(self, mock_ner_lexicon):
        existing = [Entity("Roma", "LOC", 0, 4, "ner", 0.75)]
        text = "Roma è una città. ACME è un'azienda."

        enhanced = enhance_ner_with_lexicon(existing, mock_ner_lexicon, text)

        assert any(e.text == "Roma" for e in enhanced)
        assert any("ACME" in e.text for e in enhanced)

    def test_entity_carries_version(self, mock_ner_lexicon):
        text = "ACME ha risposto."
        enhanced = enhance_ner_with_lexicon([], mock_ner_lexicon, text)
        lex_entities = [e for e in enhanced if e.source == "lexicon"]
        assert all(isinstance(e.version, str) for e in lex_entities)


# ===========================================================================
# Merger
# ===========================================================================


class TestMerger:
    """Tests for merge_entities_deterministic."""

    def test_no_overlap_keeps_all(self):
        entities = [
            Entity("ACME", "ORG", 0, 4, "regex", 0.95),
            Entity("Roma", "LOC", 10, 14, "ner", 0.75),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 2

    def test_regex_wins_over_ner(self):
        entities = [
            Entity("ACME", "ORG", 0, 4, "ner", 0.75),
            Entity("ACME", "ORG", 0, 4, "regex", 0.95),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 1
        assert merged[0].source == "regex"

    def test_lexicon_wins_over_ner(self):
        entities = [
            Entity("ACME", "ORG", 0, 4, "ner", 0.90),
            Entity("ACME", "ORG", 0, 4, "lexicon", 0.85),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 1
        assert merged[0].source == "lexicon"

    def test_longest_span_wins_same_source(self):
        entities = [
            Entity("ACME", "ORG", 0, 4, "lexicon", 0.85),
            Entity("ACME S.p.A.", "ORG", 0, 11, "lexicon", 0.85),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 1
        assert merged[0].text == "ACME S.p.A."

    def test_higher_confidence_wins_same_span(self):
        entities = [
            Entity("ACME", "ORG", 0, 4, "ner", 0.75),
            Entity("ACME", "ORG", 0, 4, "ner", 0.90),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 1
        assert merged[0].confidence == 0.90

    def test_empty_input(self):
        assert merge_entities_deterministic([]) == []

    def test_sorted_by_position(self):
        entities = [
            Entity("B", "L", 10, 15, "regex", 0.95),
            Entity("A", "L", 0, 5, "regex", 0.95),
        ]
        merged = merge_entities_deterministic(entities)
        assert merged[0].start < merged[1].start

    def test_exact_duplicates_deduped(self):
        """★FIX #8b★ — Exact duplicates (same type+value+span) must be removed."""
        entities = [
            Entity("ACME", "ORG", 0, 4, "regex", 0.95),
            Entity("ACME", "ORG", 0, 4, "regex", 0.95),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 1

    def test_empty_entity_discarded(self):
        """★FIX #2★ — Entities with empty text are dropped before merge."""
        entities = [
            Entity("", "ORG", 0, 0, "regex", 0.95),
            Entity("Roma", "LOC", 5, 9, "ner", 0.75),
        ]
        merged = merge_entities_deterministic(entities)
        assert len(merged) == 1
        assert merged[0].text == "Roma"


# ===========================================================================
# extract_all_entities (backwards-compatible wrapper)
# ===========================================================================


class TestExtractAllEntities:
    """Tests for the backwards-compatible extract_all_entities wrapper (★FIX #3★)."""

    def test_document_level_no_labelid(self, mock_regex_lexicon, mock_ner_lexicon):
        """★FIX #3★ — Signature has NO labelid parameter."""
        text = "Contattami a mario.rossi@example.it. L'azienda ACME ringrazia."
        entities = extract_all_entities(
            text,
            regex_lexicon=mock_regex_lexicon,
            ner_lexicon=mock_ner_lexicon,
            nlp_model=None,
        )
        assert any(e.label == "EMAIL" for e in entities)
        assert any("ACME" in e.text for e in entities)

    def test_default_lexicon_used(self):
        text = "Inviare a test@example.com i documenti."
        entities = extract_all_entities(text, nlp_model=None)
        emails = [e for e in entities if e.label == "EMAIL"]
        assert len(emails) >= 1

    def test_returns_list_of_entity_objects(self, mock_regex_lexicon):
        text = "test@example.it"
        result = extract_all_entities(text, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        assert isinstance(result, list)
        assert all(isinstance(e, Entity) for e in result)


# ===========================================================================
# run_pipeline (full contract)
# ===========================================================================


class TestRunPipeline:
    """Tests for the full run_pipeline orchestrator."""

    def test_returns_extraction_output(self, sample_input_dict, mock_regex_lexicon):
        from src.models.output_schema import ExtractionOutput

        output = run_pipeline(sample_input_dict, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        assert isinstance(output, ExtractionOutput)

    def test_output_contains_entities_meta_errors(
        self, sample_input_dict, mock_regex_lexicon
    ):
        output = run_pipeline(sample_input_dict, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        d = output.to_dict()
        assert "entities" in d
        assert "meta" in d
        assert "errors" in d

    def test_meta_has_required_fields(self, sample_input_dict, mock_regex_lexicon):
        output = run_pipeline(sample_input_dict, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        meta = output.to_dict()["meta"]
        for field in ("id_conversazione", "id_messaggio", "status", "layer_version",
                      "processing_time_ms", "entity_count", "feature_flags", "fallbacks"):
            assert field in meta, f"Missing meta field: {field}"

    def test_email_found_in_output(self, sample_input_dict, mock_regex_lexicon):
        output = run_pipeline(sample_input_dict, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        entities = output.to_dict()["entities"]
        emails = [e for e in entities if e["type"] == "EMAIL"]
        assert len(emails) >= 1

    def test_entity_dict_has_version(self, sample_input_dict, mock_regex_lexicon):
        output = run_pipeline(sample_input_dict, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        entities = output.to_dict()["entities"]
        assert all("version" in e for e in entities)

    def test_invalid_input_returns_failed_output(self):
        """Hard input failure must return a valid output with status='failed'."""
        bad_input = {"id_conversazione": "X"}  # missing many mandatory fields
        output = run_pipeline(bad_input)
        d = output.to_dict()
        assert d["meta"]["status"] == "failed"
        assert d["entities"] == []
        assert len(d["errors"]) >= 1

    def test_always_valid_json(self, sample_input_dict, mock_regex_lexicon):
        import json
        output = run_pipeline(sample_input_dict, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        json_str = output.to_json()
        parsed = json.loads(json_str)
        assert "entities" in parsed
        assert "meta" in parsed
        assert "errors" in parsed

    def test_null_language_non_blocking(self, mock_regex_lexicon):
        """lingua=null must not crash the pipeline (spec requirement)."""
        payload = {
            "id_conversazione": "CONV-NULL-LANG",
            "id_messaggio": "MSG-001",
            "testo_normalizzato": "Testo di prova.",
            "lingua": None,
            "timestamp": "2025-01-01T00:00:00Z",
            "mittente": "a@b.it",
            "destinatario": "c@d.it",
        }
        output = run_pipeline(payload, regex_lexicon=mock_regex_lexicon, nlp_model=None)
        assert output.to_dict()["meta"]["status"] != "failed"

