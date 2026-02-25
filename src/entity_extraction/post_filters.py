"""
Post-extraction filters applied after entity merging.

Filters (applied in order):
  1. ``filter_empty_entities``    — drop entities with empty/whitespace value (★FIX #2★)
  2. ``apply_blacklist``          — drop entities whose value is in the blacklist
  3. ``apply_type_flags``         — drop entities whose type is disabled in config
  4. ``normalize_canonical_format`` — normalise dates → ISO 8601, importi → 1234.56

Reference: entity-extraction-layer.md §Flusso elaborazione step 6
"""
from __future__ import annotations

import re
from typing import List

from src.models.entity import Entity


# ---------------------------------------------------------------------------
# Filter 1 — drop empty/whitespace-only entities (★FIX #2★)
# ---------------------------------------------------------------------------


def filter_empty_entities(entities: List[Entity]) -> List[Entity]:
    """
    Remove entities with an empty or whitespace-only ``text`` value.

    ★FIX #2★ — Guards against downstream crashes.
    """
    return [e for e in entities if e.is_valid()]


# ---------------------------------------------------------------------------
# Filter 2 — blacklist
# ---------------------------------------------------------------------------


def apply_blacklist(entities: List[Entity], blacklist: List[str]) -> List[Entity]:
    """
    Remove entities whose value appears (case-insensitively) in *blacklist*.

    Args:
        entities: Merged entity list.
        blacklist: List of value strings to suppress (case-insensitive).
    """
    if not blacklist:
        return entities

    lower_blacklist = {v.lower() for v in blacklist}
    return [e for e in entities if e.text.lower() not in lower_blacklist]


# ---------------------------------------------------------------------------
# Filter 3 — entity type flags
# ---------------------------------------------------------------------------


def apply_type_flags(
    entities: List[Entity],
    entity_types_enabled: dict,
) -> List[Entity]:
    """
    Remove entities whose type is disabled in the feature-flag map.

    Unknown entity types default to **enabled**.
    """
    return [
        e for e in entities
        if entity_types_enabled.get(e.label, True)
    ]


# ---------------------------------------------------------------------------
# Filter 4 — canonical format normalisation
# ---------------------------------------------------------------------------

# Italian date patterns → ISO 8601
_DATE_IT_RE = re.compile(
    r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$"
)

# Amount with Italian formatting (e.g. "1.500,00" or "€ 1500,00" or "1500.00")
_IMPORTO_EURO_RE = re.compile(
    r"^€?\s*(?P<intpart>[\d.]+)(?:,(?P<dec>\d{1,2}))?$"
)


def _normalise_date(value: str) -> str:
    """Convert Italian date (dd/mm/yyyy) to ISO 8601 (yyyy-mm-dd)."""
    m = _DATE_IT_RE.match(value.strip())
    if not m:
        return value  # unknown format, leave unchanged
    day, month, year = m.group(1), m.group(2), m.group(3)
    # Expand 2-digit year: 00-49 → 2000s, 50-99 → 1900s
    if len(year) == 2:
        y = int(year)
        year = str(2000 + y) if y < 50 else str(1900 + y)
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _normalise_importo(value: str) -> str:
    """Normalise Italian currency format to plain decimal (e.g. '1.500,00' → '1500.00')."""
    # Strip € and spaces
    cleaned = value.replace("€", "").strip()
    m = _IMPORTO_EURO_RE.match(cleaned)
    if not m:
        return value
    int_part = m.group("intpart").replace(".", "")  # remove thousand separators
    dec_part = m.group("dec") or "00"
    return f"{int_part}.{dec_part}"


def normalize_canonical_format(entities: List[Entity]) -> List[Entity]:
    """
    Normalise entity values to canonical formats:

    - ``DATA``:    Italian ``dd/mm/yyyy`` → ISO 8601 ``yyyy-mm-dd``
    - ``IMPORTO``: Italian currency (``1.500,00`` / ``€ 1500,00``) → ``1500.00``
    - ``CODICEFISCALE``: uppercase
    - ``PARTITAIVA``: uppercase, strip leading spaces

    All other types are returned unchanged.  The original span/position
    data is preserved; only ``text`` is updated.
    """
    result: List[Entity] = []
    for e in entities:
        normalised_text = e.text

        if e.label == "DATA":
            normalised_text = _normalise_date(e.text)
        elif e.label == "IMPORTO":
            normalised_text = _normalise_importo(e.text)
        elif e.label in ("CODICEFISCALE", "PARTITAIVA"):
            normalised_text = e.text.upper().strip()

        if normalised_text != e.text:
            # Create a new frozen Entity with the updated text
            e = Entity(
                text=normalised_text,
                label=e.label,
                start=e.start,
                end=e.end,
                source=e.source,
                confidence=e.confidence,
                version=e.version,
            )
        result.append(e)
    return result


# ---------------------------------------------------------------------------
# Convenience: apply all filters in order
# ---------------------------------------------------------------------------


def apply_all_filters(
    entities: List[Entity],
    blacklist: List[str],
    entity_types_enabled: dict,
) -> List[Entity]:
    """Apply all post-extraction filters in the canonical order."""
    entities = filter_empty_entities(entities)
    entities = apply_blacklist(entities, blacklist)
    entities = apply_type_flags(entities, entity_types_enabled)
    entities = normalize_canonical_format(entities)
    return entities
