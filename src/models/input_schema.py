"""
Input schema for the Entity Extraction pipeline.

Validates the normalised mail payload received from the upstream layer.

Reference: entity-extraction-layer.md §Contratto di input
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MAX_TEXT_LENGTH = 100_000


class ExtractionInput(BaseModel):
    """
    Validated input for the entity extraction layer.

    Mandatory fields are enforced at instantiation; ``language`` may be
    ``None`` without causing the layer to fail (per spec).
    """

    model_config = {"frozen": True, "extra": "ignore"}

    # ------------------------------------------------------------------
    # Mandatory fields
    # ------------------------------------------------------------------
    id_conversazione: str = Field(..., min_length=1, description="Unique conversation identifier")
    id_messaggio: str = Field(..., min_length=1, description="Unique message identifier")
    testo_normalizzato: str = Field(..., description="Clean email body text (no raw HTML)")
    lingua: Optional[str] = Field(default=None, description="BCP-47 language code or null")
    timestamp: str = Field(..., min_length=1, description="ISO-8601 message timestamp")
    mittente: str = Field(..., min_length=1, description="Sender address or identifier")
    destinatario: str = Field(..., min_length=1, description="Recipient address or identifier")

    # ------------------------------------------------------------------
    # Optional upstream fields
    # ------------------------------------------------------------------
    pre_annotazioni: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Pre-annotations from upstream layer (optional)",
    )
    regole_routing: Optional[List[str]] = Field(
        default=None,
        description="Routing rules already applied upstream (optional)",
    )
    tag_upstream: Optional[List[str]] = Field(
        default=None,
        description="Arbitrary tags attached by upstream layers (optional)",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("testo_normalizzato")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("testo_normalizzato must not be empty or whitespace-only")
        if len(v) > _MAX_TEXT_LENGTH:
            raise ValueError(
                f"testo_normalizzato exceeds maximum allowed length of {_MAX_TEXT_LENGTH} chars "
                f"(got {len(v)})"
            )
        if _HTML_TAG_RE.search(v):
            raise ValueError(
                "testo_normalizzato must not contain raw HTML tags; "
                "strip HTML before passing to this layer"
            )
        return v

    @field_validator("lingua")
    @classmethod
    def _validate_lingua(cls, v: Optional[str]) -> Optional[str]:
        # null is explicitly allowed per spec; non-null must be non-empty string
        if v is not None and not v.strip():
            raise ValueError("lingua must be a non-empty string or null")
        return v.lower() if v else v
