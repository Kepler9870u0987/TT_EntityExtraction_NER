"""
Unit tests for the internal text normalizer.

Reference: entity-extraction-layer.md §Flusso elaborazione step 2
"""
import pytest

from src.entity_extraction.normalizer import normalize_text, NormalizationLog


class TestNormalizeText:

    def test_strips_leading_trailing_whitespace(self):
        text = "   Ciao mondo.   "
        result, log = normalize_text(text)
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_collapses_repeated_spaces(self):
        text = "Ciao    mondo."
        result, _ = normalize_text(text)
        assert "    " not in result
        assert "Ciao mondo." in result

    def test_collapses_repeated_newlines(self):
        text = "Prima riga.\n\n\n\nSeconda riga."
        result, _ = normalize_text(text)
        assert "\n\n\n" not in result
        assert "\n\n" in result

    def test_unicode_nfkc_applied(self):
        # Full-width Latin letter A (U+FF21) should become regular 'A'
        text = "\uff21cme Corporation"
        result, _ = normalize_text(text)
        assert result.startswith("A")

    def test_returns_normalization_log(self):
        _, log = normalize_text("  test  ")
        assert isinstance(log, NormalizationLog)
        assert len(log.steps) > 0

    def test_log_has_required_fields(self):
        _, log = normalize_text("  test  ")
        for step in log.steps:
            assert hasattr(step, "name")
            assert hasattr(step, "description")
            assert hasattr(step, "chars_before")
            assert hasattr(step, "chars_after")

    def test_log_to_dict(self):
        _, log = normalize_text("  hello   world  ")
        d = log.to_dict()
        assert isinstance(d, list)
        for step in d:
            assert "name" in step
            assert "chars_before" in step
            assert "chars_after" in step

    def test_idempotent_on_clean_text(self):
        text = "Testo già pulito."
        result1, _ = normalize_text(text)
        result2, _ = normalize_text(result1)
        assert result1 == result2

    def test_empty_string_returns_empty(self):
        result, _ = normalize_text("")
        assert result == ""

    def test_tab_collapsed_to_space(self):
        text = "col1\t\tcol2"
        result, _ = normalize_text(text)
        assert "\t" not in result
        assert "col1 col2" in result
