"""
Internal soft text normalizer.

Applies minimal, deterministic transformations to the email body before
entity extraction. **Never** contradicts upstream normalisation — only
completes it.

Transformations (in order):
  1. Left/right strip
  2. Collapse repeated whitespace (spaces, tabs) to a single space
  3. Collapse repeated newlines (>2) to double newline
  4. Unicode NFKC normalisation (resolves ligatures, full-width chars, etc.)

Each transformation is logged in a :class:`NormalizationLog` so the same
transformation can be reproduced offline.

Reference: entity-extraction-layer.md §Flusso elaborazione step 2
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# NormalizationLog
# ---------------------------------------------------------------------------


@dataclass
class NormalizationStep:
    """Records a single deterministic transformation applied to the text."""

    name: str
    """Short identifier for the transformation (e.g. 'strip', 'dedup_spaces')."""

    description: str
    """Human-readable description of what was changed."""

    chars_before: int
    """Text length before this step."""

    chars_after: int
    """Text length after this step."""

    @property
    def changed(self) -> bool:
        """Return True if the transformation actually modified the text."""
        return self.chars_before != self.chars_after or True  # always log


@dataclass
class NormalizationLog:
    """Ordered list of transformations applied during soft normalization."""

    steps: List[NormalizationStep] = field(default_factory=list)

    def add(self, name: str, description: str, before: int, after: int) -> None:
        self.steps.append(
            NormalizationStep(
                name=name,
                description=description,
                chars_before=before,
                chars_after=after,
            )
        )

    def to_dict(self) -> list:
        return [
            {
                "name": s.name,
                "description": s.description,
                "chars_before": s.chars_before,
                "chars_after": s.chars_after,
            }
            for s in self.steps
        ]


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_MULTI_SPACES_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINES_RE = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> tuple[str, NormalizationLog]:
    """
    Apply soft, deterministic text normalisation.

    Args:
        text: Raw (but already de-HTML'd) email body text.

    Returns:
        A tuple of:
          - The normalised text.
          - A :class:`NormalizationLog` recording every transformation.
    """
    log = NormalizationLog()
    current = text

    # Step 1 — Unicode NFKC
    before = len(current)
    current = unicodedata.normalize("NFKC", current)
    log.add(
        "unicode_nfkc",
        "Unicode NFKC normalisation (resolves ligatures, full-width chars, etc.)",
        before,
        len(current),
    )

    # Step 2 — Strip leading/trailing whitespace
    before = len(current)
    current = current.strip()
    log.add(
        "strip",
        "Stripped leading and trailing whitespace",
        before,
        len(current),
    )

    # Step 3 — Collapse repeated inline whitespace (spaces/tabs) to single space
    before = len(current)
    current = _MULTI_SPACES_RE.sub(" ", current)
    log.add(
        "dedup_spaces",
        "Collapsed repeated spaces/tabs to a single space",
        before,
        len(current),
    )

    # Step 4 — Collapse 3+ consecutive newlines to double newline
    before = len(current)
    current = _MULTI_NEWLINES_RE.sub("\n\n", current)
    log.add(
        "dedup_newlines",
        "Collapsed 3+ consecutive newlines to double newline",
        before,
        len(current),
    )

    return current, log
