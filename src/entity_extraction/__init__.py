"""Entity extraction sub-package — public API."""
from src.entity_extraction.pipeline import extract_all_entities, run_pipeline
from src.entity_extraction.regex_matcher import DEFAULT_REGEX_LEXICON

__all__ = ["run_pipeline", "extract_all_entities", "DEFAULT_REGEX_LEXICON"]
