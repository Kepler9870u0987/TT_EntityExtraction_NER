"""
Entity model for extracted entities (RegEx / NER / Lexicon).

★FIX #3★ — Document-level, no labelid dependency.
★FIX #2★ — Guards against empty/whitespace-only values via is_valid().
★FIX #4★ — Immutable (frozen=True) to prevent accidental mutation in merger/pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    """A single extracted entity with full provenance."""

    text: str
    """Surface form exactly as it appears in the source text."""

    label: str
    """Entity type (e.g. EMAIL, CODICEFISCALE, AZIENDA, DATA, IMPORTO)."""

    start: int
    """Inclusive start offset (char index) in the normalised text."""

    end: int
    """Exclusive end offset (char index) in the normalised text."""

    source: str
    """Extraction origin: 'regex' | 'ner' | 'lexicon'."""

    confidence: float = 1.0
    """Confidence score in [0.0, 1.0]."""

    version: str = ""
    """Version of the rule/model that produced this entity
    (e.g. 'regex-v1.0', 'it_core_news_lg-3.7.1')."""

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def is_valid(self) -> bool:
        """Return True if the entity has a non-empty, non-whitespace value."""
        return bool(self.text and self.text.strip())

    # ------------------------------------------------------------------
    # Span helpers
    # ------------------------------------------------------------------

    def overlaps(self, other: "Entity") -> bool:
        """Return True if this entity's span overlaps with *other*'s span."""
        return not (self.end <= other.start or other.end <= self.start)

    def span_length(self) -> int:
        """Return the length of the entity span in characters."""
        return self.end - self.start

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain dict compatible with the output JSON contract."""
        return {
            "type": self.label,
            "value": self.text,
            "span": {"start": self.start, "end": self.end},
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        """Deserialise from a plain dict (inverse of *to_dict*)."""
        span = data.get("span", {})
        return cls(
            text=data["value"],
            label=data["type"],
            start=span.get("start", data.get("start", 0)),
            end=span.get("end", data.get("end", 0)),
            source=data["source"],
            confidence=float(data.get("confidence", 1.0)),
            version=data.get("version", ""),
        )

    def __repr__(self) -> str:
        return (
            f"Entity('{self.text}', {self.label}, [{self.start},{self.end}],"
            f" src={self.source}, conf={self.confidence:.2f}, v={self.version!r})"
        )
