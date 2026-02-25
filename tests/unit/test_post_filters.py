"""
Unit tests for post-extraction filters.

Reference: entity-extraction-layer.md §Flusso elaborazione step 6
"""
import pytest

from src.entity_extraction.post_filters import (
    apply_all_filters,
    apply_blacklist,
    apply_type_flags,
    filter_empty_entities,
    normalize_canonical_format,
)
from src.models.entity import Entity


def _make(text: str, label: str = "X", start: int = 0, source: str = "regex") -> Entity:
    return Entity(text=text, label=label, start=start, end=start + len(text), source=source)


# ===========================================================================
# filter_empty_entities
# ===========================================================================

class TestFilterEmptyEntities:

    def test_empty_text_removed(self):
        entities = [_make(""), _make("hello")]
        result = filter_empty_entities(entities)
        assert len(result) == 1
        assert result[0].text == "hello"

    def test_whitespace_only_removed(self):
        entities = [_make("   "), _make("world")]
        result = filter_empty_entities(entities)
        assert len(result) == 1

    def test_valid_entities_kept(self):
        entities = [_make("ACME"), _make("Roma")]
        result = filter_empty_entities(entities)
        assert len(result) == 2

    def test_empty_list(self):
        assert filter_empty_entities([]) == []


# ===========================================================================
# apply_blacklist
# ===========================================================================

class TestApplyBlacklist:

    def test_blacklisted_value_removed(self):
        entities = [_make("unknown"), _make("Roma")]
        result = apply_blacklist(entities, blacklist=["unknown"])
        assert all(e.text != "unknown" for e in result)

    def test_case_insensitive_match(self):
        entities = [_make("UNKNOWN"), _make("Roma")]
        result = apply_blacklist(entities, blacklist=["unknown"])
        assert all(e.text != "UNKNOWN" for e in result)

    def test_empty_blacklist_keeps_all(self):
        entities = [_make("ACME"), _make("Roma")]
        result = apply_blacklist(entities, blacklist=[])
        assert len(result) == 2

    def test_multiple_blacklist_values(self):
        entities = [_make("spam"), _make("test"), _make("valid")]
        result = apply_blacklist(entities, blacklist=["spam", "test"])
        assert len(result) == 1
        assert result[0].text == "valid"


# ===========================================================================
# apply_type_flags
# ===========================================================================

class TestApplyTypeFlags:

    def test_disabled_type_removed(self):
        entities = [
            Entity("test@x.it", "EMAIL", 0, 9, "regex"),
            Entity("RSSMRA85M01H501Z", "CODICEFISCALE", 10, 26, "regex"),
        ]
        flags = {"EMAIL": True, "CODICEFISCALE": False}
        result = apply_type_flags(entities, flags)
        assert all(e.label != "CODICEFISCALE" for e in result)

    def test_unknown_type_defaults_to_enabled(self):
        entities = [Entity("X", "UNKNOWN_TYPE", 0, 1, "regex")]
        result = apply_type_flags(entities, entity_types_enabled={})
        assert len(result) == 1

    def test_all_enabled_keeps_all(self):
        entities = [
            Entity("test@x.it", "EMAIL", 0, 9, "regex"),
            Entity("RSSMRA85M01H501Z", "CODICEFISCALE", 10, 26, "regex"),
        ]
        flags = {"EMAIL": True, "CODICEFISCALE": True}
        result = apply_type_flags(entities, flags)
        assert len(result) == 2


# ===========================================================================
# normalize_canonical_format
# ===========================================================================

class TestNormalizeCanonicalFormat:

    def test_italian_date_to_iso(self):
        e = Entity("10/03/2025", "DATA", 0, 10, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "2025-03-10"

    def test_dash_date_to_iso(self):
        e = Entity("05-12-2024", "DATA", 0, 10, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "2024-12-05"

    def test_two_digit_year_50_plus_is_1900s(self):
        e = Entity("01/01/85", "DATA", 0, 8, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "1985-01-01"

    def test_two_digit_year_under_50_is_2000s(self):
        e = Entity("01/01/25", "DATA", 0, 8, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "2025-01-01"

    def test_importo_normalised(self):
        e = Entity("€ 1.500,00", "IMPORTO", 0, 10, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "1500.00"

    def test_importo_no_decimals(self):
        e = Entity("€ 500", "IMPORTO", 0, 5, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "500.00"

    def test_codice_fiscale_uppercased(self):
        e = Entity("rssmra85m01h501z", "CODICEFISCALE", 0, 16, "regex")
        result = normalize_canonical_format([e])
        assert result[0].text == "RSSMRA85M01H501Z"

    def test_non_normalised_types_unchanged(self):
        e = Entity("ACME S.p.A.", "AZIENDA", 0, 11, "lexicon")
        result = normalize_canonical_format([e])
        assert result[0].text == "ACME S.p.A."

    def test_span_preserved_after_normalisation(self):
        e = Entity("10/03/2025", "DATA", 5, 15, "regex")
        result = normalize_canonical_format([e])
        # Span must not change (original position in text is preserved)
        assert result[0].start == 5
        assert result[0].end == 15


# ===========================================================================
# apply_all_filters (combined)
# ===========================================================================

class TestApplyAllFilters:

    def test_combined_filters_applied_in_order(self):
        entities = [
            Entity("", "EMAIL", 0, 0, "regex"),            # empty → removed
            Entity("spam@x.it", "EMAIL", 5, 14, "regex"),  # blacklisted → removed
            Entity("10/03/2025", "DATA", 20, 30, "regex"), # normalised → ISO 8601
            Entity("test@x.it", "TELEFONO", 35, 44, "regex"),  # disabled type → removed
        ]
        blacklist = ["spam@x.it"]
        type_flags = {"EMAIL": True, "DATA": True, "TELEFONO": False}

        result = apply_all_filters(entities, blacklist=blacklist, entity_types_enabled=type_flags)

        assert all(e.is_valid() for e in result)
        assert all(e.text.lower() not in blacklist for e in result)
        assert all(e.label != "TELEFONO" for e in result)
        dates = [e for e in result if e.label == "DATA"]
        assert dates[0].text == "2025-03-10"
