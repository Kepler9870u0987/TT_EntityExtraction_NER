"""
Pytest fixtures shared across all test modules.
"""
import pytest

from src.models.entity import Entity


# ---------------------------------------------------------------------------
# Regex lexicon fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_regex_lexicon():
    """Minimal regex lexicon covering EMAIL and CODICEFISCALE for unit tests."""
    return {
        "EMAIL": [
            {
                "regex_pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "label": "EMAIL",
            },
        ],
        "CODICEFISCALE": [
            {
                "regex_pattern": r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b",
                "label": "CODICEFISCALE",
            },
        ],
        "IBAN": [
            {
                "regex_pattern": r"\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{3}\b",
                "label": "IBAN",
            },
        ],
        "IMPORTO": [
            {
                "regex_pattern": r"€\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s?€",
                "label": "IMPORTO",
            },
        ],
        "DATA": [
            {
                "regex_pattern": r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b",
                "label": "DATA",
            },
        ],
    }


# ---------------------------------------------------------------------------
# NER lexicon fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ner_lexicon():
    """Minimal NER/gazetteer lexicon with sample Italian companies."""
    return {
        "AZIENDA": [
            {
                "lemma": "ACME",
                "surface_forms": ["ACME", "ACME S.p.A.", "ACME srl"],
            },
            {
                "lemma": "FIAT",
                "surface_forms": ["FIAT", "Fiat Group"],
            },
        ],
        "PRODOTTO": [
            {
                "lemma": "MUTUO",
                "surface_forms": ["mutuo", "Mutuo", "mutuo ipotecario"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Sample valid input dict fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_input_dict():
    """A valid ExtractionInput payload for integration tests."""
    return {
        "id_conversazione": "CONV-001",
        "id_messaggio": "MSG-001",
        "testo_normalizzato": (
            "Gentile supporto, sono Mario Rossi (RSSMRA85M01H501Z). "
            "Vi contatto per la pratica del mutuo. "
            "Potete rispondermi a mario.rossi@example.it? "
            "L'azienda ACME ha già versato € 1.500,00 il 10/03/2025. "
            "IBAN: IT60X0542811101000000123456. Grazie."
        ),
        "lingua": "it",
        "timestamp": "2025-03-10T09:00:00Z",
        "mittente": "mario.rossi@example.it",
        "destinatario": "supporto@banca.it",
    }
