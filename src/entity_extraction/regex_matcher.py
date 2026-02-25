"""
RegEx Entity Matcher — high-precision entity extraction.

★FIX #3★ — Document-level: operates on entire document, not per-label.
★FIX #5a★ — PARTITAIVA regex tightened (requires IT prefix or contextual anchor).
★FIX #5b★ — TELEFONO regex tightened to avoid matching arbitrary numbers.
★ADD★ — Patterns for DATA, IMPORTO, NUMERO_PRATICA added.
★ADD★ — Accepts optional PipelineConfig for confidence / feature-flag control.
★ADD★ — Every produced Entity carries the regex rule version tag.

Reference: entity-extraction-layer.md §Motore rule-based
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from src.models.entity import Entity

if TYPE_CHECKING:
    from src.config import PipelineConfig

logger = logging.getLogger(__name__)


def extract_entities_regex(
    text: str,
    regex_lexicon: Dict[str, List[dict]],
    config: Optional["PipelineConfig"] = None,
) -> List[Entity]:
    """
    Extract entities using regex patterns from a global entity lexicon.

    ★FIX #3★ — Document-level: no labelid parameter.

    Args:
        text: Canonical (normalised) email body text.
        regex_lexicon: Mapping of entity label → list of pattern entries::

            {
                "EMAIL": [{"regex_pattern": r"...", "label": "EMAIL"}, ...],
                ...
            }

        config: Optional :class:`~src.config.PipelineConfig` for confidence
                and feature-flag overrides.  Falls back to built-in defaults
                when ``None``.

    Returns:
        List of :class:`~src.models.entity.Entity` objects found via regex
        (``source="regex"``).  Empty/whitespace matches are skipped (★FIX #2★).
    """
    _confidence = config.regex_confidence if config else 0.95
    _version = config.regex_rule_version if config else "regex-v1.0"
    _type_flags = (
        config.entity_types_enabled if config else {}
    )

    entities: List[Entity] = []

    for entity_label, entries in regex_lexicon.items():
        # Feature-flag: skip disabled entity types
        if not _type_flags.get(entity_label, True):
            continue

        for entry in entries:
            pattern = entry["regex_pattern"]
            label = entry.get("label", entity_label)
            entry_confidence = float(entry.get("confidence", _confidence))
            entry_version = entry.get("version", _version)

            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                logger.warning(
                    "Invalid regex pattern '%s' for label '%s': %s",
                    pattern, label, exc,
                )
                continue

            for match in compiled.finditer(text):
                matched_text = match.group(0)
                # ★FIX #2★ — skip empty/whitespace-only matches
                if not matched_text or not matched_text.strip():
                    continue

                entities.append(
                    Entity(
                        text=matched_text,
                        label=label,
                        start=match.start(),
                        end=match.end(),
                        source="regex",
                        confidence=entry_confidence,
                        version=entry_version,
                    )
                )

    return entities


# ==========================================================================
# Default regex lexicon for common Italian entities
# ==========================================================================

DEFAULT_REGEX_LEXICON: Dict[str, List[dict]] = {
    # ------------------------------------------------------------------
    # EMAIL
    # ------------------------------------------------------------------
    "EMAIL": [
        {
            "regex_pattern": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            "label": "EMAIL",
        },
    ],

    # ------------------------------------------------------------------
    # CODICE FISCALE (16-char Italian tax code)
    # Format: LLLLLL NN L NN L NNN L  (exactly)
    # ------------------------------------------------------------------
    "CODICEFISCALE": [
        {
            "regex_pattern": (
                r"\b[A-Z]{6}"        # 6 letters (surname + name)
                r"\d{2}"             # 2 digits (year)
                r"[A-Z]"             # 1 letter (month code)
                r"\d{2}"             # 2 digits (day + gender)
                r"[A-Z]"             # 1 letter (municipality code prefix)
                r"\d{3}"             # 3 digits (municipality code)
                r"[A-Z]\b"           # 1 control letter
            ),
            "label": "CODICEFISCALE",
        },
    ],

    # ------------------------------------------------------------------
    # PARTITA IVA (Italian VAT number — 11 digits, optionally IT prefix)
    # ★FIX #5a★ — Requires explicit "IT" prefix OR a VAT context keyword
    # anchor to avoid false positives on arbitrary 11-digit numbers.
    # ------------------------------------------------------------------
    "PARTITAIVA": [
        {
            # Explicit "IT" country code prefix (most common)
            "regex_pattern": r"\bIT\s?\d{11}\b",
            "label": "PARTITAIVA",
        },
        {
            # Without prefix, only match when preceded by an Italian VAT label
            "regex_pattern": (
                r"(?:P\.?\s?IVA|partita\s+iva|p\.iva)"
                r"[\s:]*"
                r"(\d{11})\b"
            ),
            "label": "PARTITAIVA",
        },
    ],

    # ------------------------------------------------------------------
    # IBAN (Italian: IT + 2 check + 23 alphanum chars)
    # ------------------------------------------------------------------
    "IBAN": [
        {
            "regex_pattern": (
                r"\b"
                r"[A-Z]{2}"                             # country code
                r"\d{2}"                                # check digits
                r"(?:[\s]?[A-Z0-9]{4}){1,7}"           # BBAN groups
                r"\b"
            ),
            "label": "IBAN",
        },
    ],

    # ------------------------------------------------------------------
    # TELEFONO (Italian landlines + mobiles)
    # ★FIX #5b★ — Tighter pattern; avoids matching arbitrary numbers.
    # Accepts:  +39 xxx, 0xx, 3xx (Italian mobile prefix range 3xx)
    # ------------------------------------------------------------------
    "TELEFONO": [
        {
            # International format: +39 followed by 6-10 digits
            "regex_pattern": r"\+39[\s.\-]?\d{2,4}[\s.\-]?\d{4,8}\b",
            "label": "TELEFONO",
        },
        {
            # Italian landline: 0 + 1-3 area code + 6-8 digits
            "regex_pattern": r"\b0\d{1,3}[\s.\-]?\d{6,8}\b",
            "label": "TELEFONO",
        },
        {
            # Italian mobile: 3xx prefix + 7 digits
            "regex_pattern": r"\b3\d{2}[\s.\-]?\d{3}[\s.\-]?\d{4}\b",
            "label": "TELEFONO",
        },
    ],

    # ------------------------------------------------------------------
    # DATA (Italian date formats: dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy)
    # ------------------------------------------------------------------
    "DATA": [
        {
            "regex_pattern": (
                r"\b"
                r"(?:0?[1-9]|[12]\d|3[01])"   # day
                r"[/\-.]"
                r"(?:0?[1-9]|1[0-2])"          # month
                r"[/\-.]"
                r"(?:\d{4}|\d{2})"             # year (4 or 2 digits)
                r"\b"
            ),
            "label": "DATA",
        },
    ],

    # ------------------------------------------------------------------
    # IMPORTO (Italian currency amounts)
    # Matches: € 1.500,00 | 1.500,00 € | € 1500 | 1500,50€
    # ------------------------------------------------------------------
    "IMPORTO": [
        {
            "regex_pattern": (
                r"€\s?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?"   # € prefix
                r"|"
                r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\s?€"   # € suffix
            ),
            "label": "IMPORTO",
        },
    ],

    # ------------------------------------------------------------------
    # NUMERO_PRATICA  (practice/case reference — highly domain-specific)
    # Matches patterns like: PRAT-2025-001234, PRT/001234, N. 001234
    # Adjust the pattern to match your org's actual reference format.
    # ------------------------------------------------------------------
    "NUMERO_PRATICA": [
        {
            "regex_pattern": (
                r"\b(?:PRAT|PRT|PRATICA|RIFER|REF)"
                r"[\s/\-.]?\d{4,10}\b"
            ),
            "label": "NUMERO_PRATICA",
        },
        {
            # Generic reference "N. 12345678" or "Nr. 12345678"
            "regex_pattern": r"\bN[r]?\.?\s*\d{6,10}\b",
            "label": "NUMERO_PRATICA",
        },
    ],
}
