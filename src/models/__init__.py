"""Domain models — public API."""
from src.models.entity import Entity
from src.models.input_schema import ExtractionInput
from src.models.message_envelope import EmailContext, MessageEnvelope
from src.models.output_schema import ExtractionOutput

__all__ = ["Entity", "ExtractionInput", "ExtractionOutput", "MessageEnvelope", "EmailContext"]