"""
Unit tests for input validation.

Reference: entity-extraction-layer.md §Flusso elaborazione step 1
"""
import pytest

from src.entity_extraction.input_validator import InputValidationError, validate_input
from src.models.input_schema import ExtractionInput


_VALID_BASE = {
    "id_conversazione": "CONV-001",
    "id_messaggio": "MSG-001",
    "testo_normalizzato": "Gentile supporto, vi contatto per informazioni.",
    "lingua": "it",
    "timestamp": "2025-01-01T00:00:00Z",
    "mittente": "mario@example.it",
    "destinatario": "supporto@banca.it",
}


class TestValidateInputHappyPath:

    def test_valid_input_returns_extraction_input(self):
        parsed, warnings = validate_input(_VALID_BASE)
        assert isinstance(parsed, ExtractionInput)

    def test_lingua_lowercased(self):
        raw = {**_VALID_BASE, "lingua": "IT"}
        parsed, _ = validate_input(raw)
        assert parsed.lingua == "it"

    def test_null_lingua_accepted(self):
        raw = {**_VALID_BASE, "lingua": None}
        parsed, warnings = validate_input(raw)
        assert parsed.lingua is None

    def test_null_lingua_produces_warning(self):
        raw = {**_VALID_BASE, "lingua": None}
        _, warnings = validate_input(raw)
        assert any(w["type"] == "null_language" for w in warnings)

    def test_optional_fields_accepted(self):
        raw = {
            **_VALID_BASE,
            "pre_annotazioni": [{"label": "X", "span": [0, 5]}],
            "tag_upstream": ["routing_a"],
        }
        parsed, _ = validate_input(raw)
        assert parsed.pre_annotazioni is not None

    def test_extra_fields_ignored(self):
        raw = {**_VALID_BASE, "unknown_field": "should_be_ignored"}
        parsed, _ = validate_input(raw)
        assert not hasattr(parsed, "unknown_field")


class TestValidateInputMissingFields:

    def test_missing_id_conversazione_raises(self):
        raw = {k: v for k, v in _VALID_BASE.items() if k != "id_conversazione"}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_missing_id_messaggio_raises(self):
        raw = {k: v for k, v in _VALID_BASE.items() if k != "id_messaggio"}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_missing_testo_raises(self):
        raw = {k: v for k, v in _VALID_BASE.items() if k != "testo_normalizzato"}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_missing_multiple_fields_raises(self):
        with pytest.raises(InputValidationError):
            validate_input({})

    def test_error_list_populated_on_failure(self):
        raw = {k: v for k, v in _VALID_BASE.items() if k != "id_conversazione"}
        try:
            validate_input(raw)
        except InputValidationError as exc:
            assert len(exc.validation_errors) >= 1


class TestValidateInputConstraints:

    def test_empty_text_raises(self):
        raw = {**_VALID_BASE, "testo_normalizzato": ""}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_whitespace_only_text_raises(self):
        raw = {**_VALID_BASE, "testo_normalizzato": "   "}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_text_with_html_raises(self):
        raw = {**_VALID_BASE, "testo_normalizzato": "<p>Ciao <b>mondo</b></p>"}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_text_too_long_raises(self):
        raw = {**_VALID_BASE, "testo_normalizzato": "x" * 100_001}
        with pytest.raises(InputValidationError):
            validate_input(raw)

    def test_text_at_max_length_accepted(self):
        raw = {**_VALID_BASE, "testo_normalizzato": "x" * 100_000}
        parsed, _ = validate_input(raw)
        assert len(parsed.testo_normalizzato) == 100_000

    def test_empty_lingua_string_raises(self):
        raw = {**_VALID_BASE, "lingua": ""}
        with pytest.raises(InputValidationError):
            validate_input(raw)
