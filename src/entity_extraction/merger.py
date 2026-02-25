"""
Deterministic Entity Merger.

Merges overlapping entities with fixed priority rules:
1. Source priority: regex > lexicon > ner  (overridable via PipelineConfig)
2. Same source → longest span wins
3. Same length  → higher confidence wins

★FIX #8a★ — Source priorities now read from PipelineConfig, not a hardcoded constant.
★FIX #8b★ — Exact duplicates (same type + value + span) are deduped first.
★FIX #8c★ — Stable ordering: position → label → source (★FIX #3★ in spec).
★FIX #2★  — Entities with empty/whitespace text are discarded before merge.

Reference: entity-extraction-layer.md §Fusione entità
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from src.models.entity import Entity

if TYPE_CHECKING:
    from src.config import PipelineConfig

_DEFAULT_SOURCE_PRIORITY = {"regex": 0, "lexicon": 1, "ner": 2}


def merge_entities_deterministic(
    entities: List[Entity],
    config: Optional["PipelineConfig"] = None,
) -> List[Entity]:
    """
    Merge overlapping entities using deterministic rules.

    Steps:
      1. Drop empty/whitespace entities (★FIX #2★)
      2. Deduplicate exact matches (same label + text + start + end)
      3. Resolve overlapping spans using priority / span-length / confidence
      4. Sort result stably by (start, label, source)

    Priority resolution (for overlapping spans):
        1. Source priority: regex > lexicon > ner  (configurable via PipelineConfig)
        2. Same source → longest span wins
        3. Same length  → higher confidence wins

    Args:
        entities: All extracted entities (may overlap).
        config:   Optional :class:`~src.config.PipelineConfig`.  Falls back
                  to built-in defaults when ``None``.

    Returns:
        Deduplicated, non-overlapping list of :class:`~src.models.entity.Entity`
        objects sorted by position (then label, then source for stability).
    """
    _source_priority = (
        config.source_priority if config else _DEFAULT_SOURCE_PRIORITY
    )

    # ★FIX #2★ — Drop empty/whitespace-only entities
    entities = [e for e in entities if e.is_valid()]

    if not entities:
        return []

    # ★FIX #8b★ — Deduplicate truly identical entities
    # Key includes source + confidence so entities with same span but different
    # source/confidence are NOT discarded here but handled by priority resolution.
    seen: set = set()
    deduped: List[Entity] = []
    for e in entities:
        key = (e.label, e.text, e.start, e.end, e.source, e.confidence)
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    entities = deduped

    # Sort by start position, then longest span first, then source priority,
    # then highest confidence — so the "winner" appears first in the iteration
    entities_sorted = sorted(
        entities,
        key=lambda e: (
            e.start,
            -e.end,                                          # longest span first
            _source_priority.get(e.source, 99),             # highest priority source
            -e.confidence,                                   # highest confidence
        ),
    )

    merged: List[Entity] = []

    for entity in entities_sorted:
        overlap_found = False

        for i, existing in enumerate(merged):
            if entity.overlaps(existing):
                overlap_found = True

                e_prio = _source_priority.get(entity.source, 99)
                ex_prio = _source_priority.get(existing.source, 99)

                # Rule 1 — higher source priority (lower number) wins
                if e_prio < ex_prio:
                    merged[i] = entity
                elif e_prio == ex_prio:
                    # Rule 2 — longest span wins
                    if entity.span_length() > existing.span_length():
                        merged[i] = entity
                    elif (
                        entity.span_length() == existing.span_length()
                        and entity.confidence > existing.confidence
                    ):
                        # Rule 3 — higher confidence wins
                        merged[i] = entity

                break  # each new entity can only conflict with one existing

        if not overlap_found:
            merged.append(entity)

    # ★FIX #8c★ — Stable final sort: position → label → source
    merged.sort(key=lambda e: (e.start, e.label, _source_priority.get(e.source, 99)))
    return merged
