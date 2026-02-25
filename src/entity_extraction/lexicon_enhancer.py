"""
Lexicon Enhancement — gazetteer-based entity enrichment.

★FIX #3★ — Document-level: no labelid parameter.
★FIX #7★ — Critical label fix: entity label is set to the *category key*
            (e.g. "AZIENDA") not to the lemma string (e.g. "ACME").
            Previously ``label=lemma`` caused the merger to treat different
            category entries as distinct types, breaking conflict resolution.
★ADD★    — Accepts optional PipelineConfig for confidence / feature-flag control.
★ADD★    — Every produced Entity carries the lexicon version tag.

Reference: entity-extraction-layer.md §Motore rule-based / Fusione entità
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from src.models.entity import Entity

if TYPE_CHECKING:
    from src.config import PipelineConfig


def enhance_ner_with_lexicon(
    ner_entities: List[Entity],
    ner_lexicon: Dict[str, List[dict]],
    text: str,
    config: Optional["PipelineConfig"] = None,
) -> List[Entity]:
    """
    Enhance NER entities using a gazetteer lexicon.

    ★FIX #3★ — Document-level: no labelid parameter.
    ★FIX #7★ — Entity ``label`` is the category key (e.g. ``"AZIENDA"``),
               not the lemma value.

    Args:
        ner_entities: Entities already found by NER.
        ner_lexicon:  Global gazetteer structured as::

            {
                "AZIENDA": [
                    {"lemma": "ACME", "surface_forms": ["ACME", "ACME S.p.A."]},
                    ...
                ],
                ...
            }

        text:   Normalised email body text.
        config: Optional :class:`~src.config.PipelineConfig` for confidence
                and feature-flag control.

    Returns:
        Combined list: original NER entities + lexicon-matched entities.
        Lexicon-matched entities have ``source="lexicon"``.
    """
    if not _is_engine_enabled(config):
        return list(ner_entities)

    _confidence: float = config.lexicon_confidence if config else 0.85
    _version: str = config.lexicon_version if config else "lexicon-v1.0"
    _type_flags: dict = config.entity_types_enabled if config else {}

    enhanced = list(ner_entities)
    lower_text = text.lower()

    for entity_label, entries in ner_lexicon.items():
        # Feature-flag: skip disabled entity types
        if not _type_flags.get(entity_label, True):
            continue

        for entry in entries:
            surface_forms = entry.get("surface_forms", [entry.get("lemma", "")])
            entry_confidence = float(entry.get("confidence", _confidence))

            for sf in surface_forms:
                if not sf:
                    continue

                lower_sf = sf.lower()
                pos = 0

                while pos < len(lower_text):
                    idx = lower_text.find(lower_sf, pos)
                    if idx == -1:
                        break

                    # Word-boundary check
                    before_ok = idx == 0 or not lower_text[idx - 1].isalnum()
                    after_index = idx + len(lower_sf)
                    after_ok = (
                        after_index == len(lower_text)
                        or not lower_text[after_index].isalnum()
                    )

                    if before_ok and after_ok:
                        matched_text = text[idx: idx + len(sf)]
                        # ★FIX #2★ — skip empty/whitespace matches
                        if matched_text.strip():
                            enhanced.append(
                                Entity(
                                    text=matched_text,
                                    # ★FIX #7★ — label is the CATEGORY, not the lemma
                                    label=entity_label,
                                    start=idx,
                                    end=idx + len(sf),
                                    source="lexicon",
                                    confidence=entry_confidence,
                                    version=_version,
                                )
                            )

                    pos = idx + 1

    return enhanced


def _is_engine_enabled(config: Optional["PipelineConfig"]) -> bool:
    if config is None:
        return True
    return config.engine_lexicon_enabled
