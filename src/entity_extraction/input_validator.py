"""
Input validator for the Entity Extraction pipeline.

Wraps Pydantic validation (ExtractionInput) and converts validation errors
into a standardised, non-blocking error list so the pipeline can always
return a valid JSON envelope.

Reference: entity-extraction-layer.md §Flusso elaborazione step 1
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from pydantic import ValidationError

from src.models.input_schema import ExtractionInput


class InputValidationError(ValueError):
    """Raised when mandatory input validation fails (hard error)."""

    def __init__(self, errors: List[Dict[str, str]]) -> None:
        self.validation_errors = errors
        messages = "; ".join(f"{e['field']}: {e['message']}" for e in errors)
        super().__init__(f"Input validation failed: {messages}")


def validate_input(raw: dict) -> Tuple[ExtractionInput, List[Dict[str, str]]]:
    """
    Validate a raw input dict against :class:`ExtractionInput`.

    Returns:
        A tuple ``(parsed_input, warnings)`` where ``warnings`` is a list of
        non-blocking warning dicts (e.g. unknown optional fields).

    Raises:
        :class:`InputValidationError` if any mandatory field is missing or
        invalid.
    """
    warnings: List[Dict[str, str]] = []

    try:
        parsed = ExtractionInput.model_validate(raw)
    except ValidationError as exc:
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        raise InputValidationError(errors) from exc

    # Non-blocking: warn if lingua is null (NER will be skipped)
    if parsed.lingua is None:
        warnings.append(
            {
                "field": "lingua",
                "message": "lingua is null; NER engine will be skipped for this message",
                "type": "null_language",
            }
        )

    return parsed, warnings
