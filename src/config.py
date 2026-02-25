"""
Pipeline configuration — all thresholds and feature flags configurable at runtime.

Load order:
  1. Built-in defaults.
  2. YAML / JSON config file (if ``CONFIG_FILE`` env var is set).
  3. Individual environment variable overrides (``NER_*`` prefix).

Reference: entity-extraction-layer.md §Linee guida di implementazione
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer version — bump on every significant rule/model change
# ---------------------------------------------------------------------------
LAYER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# PipelineConfig
# ---------------------------------------------------------------------------


@dataclass
class PipelineConfig:
    """All runtime-tunable parameters for the Entity Extraction pipeline."""

    # --- Confidence defaults per engine ---
    regex_confidence: float = 0.95
    ner_confidence: float = 0.75
    lexicon_confidence: float = 0.85

    # --- NER selective-execution guards ---
    min_text_length_for_ner: int = 50
    """Minimum text length (chars) before NER engine is invoked."""

    ner_timeout_seconds: float = 30.0
    """Hard timeout for the spaCy NER call (in seconds)."""

    max_text_length: int = 100_000
    """Hard cap on text length accepted by the pipeline."""

    supported_ner_languages: List[str] = field(
        default_factory=lambda: ["it", "en"]
    )
    """Languages for which the NER engine is considered valid."""

    # --- Source priority (lower = higher priority) ---
    source_priority: Dict[str, int] = field(
        default_factory=lambda: {"regex": 0, "lexicon": 1, "ner": 2}
    )

    # --- Feature flags — engines ---
    engine_regex_enabled: bool = True
    engine_ner_enabled: bool = True
    engine_lexicon_enabled: bool = True

    # --- Feature flags — entity types ---
    # True = enabled, False = suppressed from output
    entity_types_enabled: Dict[str, bool] = field(
        default_factory=lambda: {
            "EMAIL": True,
            "CODICEFISCALE": True,
            "PARTITAIVA": True,
            "IBAN": True,
            "TELEFONO": True,
            "DATA": True,
            "IMPORTO": True,
            "NUMERO_PRATICA": True,
        }
    )

    # --- Post-filter: blacklist ---
    blacklist_values: List[str] = field(default_factory=list)
    """Entity values (case-insensitive) that must always be discarded."""

    # --- Versioning ---
    regex_rule_version: str = "regex-v1.0"
    lexicon_version: str = "lexicon-v1.0"

    # --- NER model identifier (used as entity version tag) ---
    ner_model_name: str = "it_core_news_lg"

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Build config from environment variables, falling back to defaults."""
        cfg = cls()

        # Optional YAML / JSON config file
        config_file = os.environ.get("NER_CONFIG_FILE")
        if config_file:
            path = Path(config_file)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    cfg = cls(**{k: v for k, v in raw.items() if hasattr(cls, k)})
                    logger.info("Loaded pipeline config from %s", path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to load config file %s: %s", path, exc)

        # Individual env-var overrides
        _apply_env_overrides(cfg)
        return cfg

    @classmethod
    def default(cls) -> "PipelineConfig":
        """Return a fresh config with all defaults (convenience alias)."""
        return cls()

    def is_entity_type_enabled(self, label: str) -> bool:
        """Return True if the given entity type is enabled (defaults to True for unknown types)."""
        return self.entity_types_enabled.get(label, True)

    def is_language_ner_supported(self, language: Optional[str]) -> bool:
        """Return True if *language* is in the supported NER languages."""
        if language is None:
            return False
        return language.lower() in [lang.lower() for lang in self.supported_ner_languages]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_env_overrides(cfg: PipelineConfig) -> None:
    """Apply individual NER_* environment variable overrides to *cfg* in-place."""
    bool_map = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}

    def _getenv_float(key: str) -> Optional[float]:
        v = os.environ.get(key)
        return float(v) if v is not None else None

    def _getenv_int(key: str) -> Optional[int]:
        v = os.environ.get(key)
        return int(v) if v is not None else None

    def _getenv_bool(key: str) -> Optional[bool]:
        v = os.environ.get(key, "").lower()
        return bool_map.get(v)

    # Confidence overrides
    for attr, env_key in [
        ("regex_confidence", "NER_REGEX_CONFIDENCE"),
        ("ner_confidence", "NER_NER_CONFIDENCE"),
        ("lexicon_confidence", "NER_LEXICON_CONFIDENCE"),
        ("ner_timeout_seconds", "NER_TIMEOUT_SECONDS"),
    ]:
        val = _getenv_float(env_key)
        if val is not None:
            object.__setattr__(cfg, attr, val) if hasattr(cfg, "__dataclass_fields__") else setattr(cfg, attr, val)

    for attr, env_key in [
        ("min_text_length_for_ner", "NER_MIN_TEXT_LENGTH"),
        ("max_text_length", "NER_MAX_TEXT_LENGTH"),
    ]:
        val = _getenv_int(env_key)
        if val is not None:
            setattr(cfg, attr, val)

    for attr, env_key in [
        ("engine_regex_enabled", "NER_ENGINE_REGEX"),
        ("engine_ner_enabled", "NER_ENGINE_NER"),
        ("engine_lexicon_enabled", "NER_ENGINE_LEXICON"),
    ]:
        val = _getenv_bool(env_key)
        if val is not None:
            setattr(cfg, attr, val)
