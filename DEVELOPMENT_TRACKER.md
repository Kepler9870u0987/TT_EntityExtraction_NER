# Entity Extraction + NER — Development Tracker
> **Layer**: Entity Extraction & NER · **Version**: 1.0.0 · **Ultima modifica**: 2026-02-25
>
> Legenda stato: ✅ Completato · 🔄 In corso · ⏳ Non iniziato · ❌ Bloccato

---

## Indice rapido

| Fase | Descrizione | Stato |
|------|-------------|-------|
| FASE 0 | Infrastruttura progetto | ✅ |
| FASE 1 | Modello Entity & contratti I/O | ✅ |
| FASE 2 | Configurazione & Feature Flags | ✅ |
| FASE 3 | Normalizzatore interno | ✅ |
| FASE 4 | Validazione input | ✅ |
| FASE 5 | Fix & miglioramento motori | ✅ |
| FASE 6 | Filtri post-estrazione | ✅ |
| FASE 7 | Refactoring pipeline orchestrator | ✅ |
| FASE 8 | Observability (logging + metrics) | ✅ |
| FASE 9 | Suite di test completa | ✅ |
| BACKLOG | Miglioramenti futuri | ⏳ |

---

## FASE 0 — Infrastruttura progetto

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 0.1 | Creare `pyproject.toml` con metadata, dipendenze, config pytest/mypy/ruff | `pyproject.toml` | ✅ | Dipendenze: pydantic>=2.0, spacy>=3.7; extras: observability, dev |
| 0.2 | Creare `requirements.txt` (runtime) | `requirements.txt` | ✅ | pydantic + spacy |
| 0.3 | Creare `requirements-dev.txt` (dev + observability) | `requirements-dev.txt` | ✅ | pytest, mypy, ruff, prometheus-client, structlog |
| 0.4 | Fix imports `from src.` (packaging via pythonpath in pyproject.toml) | `pyproject.toml` | ✅ | `pythonpath = ["."]` in pytest settings |
| 0.5 | Creare `tests/conftest.py` con fixture `mock_regex_lexicon`, `mock_ner_lexicon`, `sample_input_dict` | `tests/conftest.py` | ✅ | **★FIX CRITICO★** — senza questo tutti i test fallivano con `fixture not found` |
| 0.6 | Creare package `src/observability/` | `src/observability/__init__.py` | ✅ | |
| 0.7 | Creare package `tests/integration/` | `tests/integration/__init__.py` | ✅ | |
| 0.8 | Creare package `tests/robustness/` | `tests/robustness/__init__.py` | ✅ | |

---

## FASE 1 — Modello Entity & Contratti I/O

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 1.1 | Aggiungere campo `version: str = ""` a `Entity` | `src/models/entity.py` | ✅ | Richiesto da spec: entity-extraction-layer.md §Contratto output |
| 1.2 | Rendere `Entity` immutabile (`frozen=True`) | `src/models/entity.py` | ✅ | **★FIX #4★** — previene mutazione accidentale nel merger |
| 1.3 | Aggiungere metodo `is_valid()` a `Entity` | `src/models/entity.py` | ✅ | **★FIX #2★** — guard contro valori vuoti/whitespace |
| 1.4 | Aggiornare `to_dict()` al formato contratto output (`type`/`value`/`span`/…) | `src/models/entity.py` | ✅ | Allineato a spec (prima usava `text`/`label`/`start`/`end` flat) |
| 1.5 | Aggiungere metodo `from_dict()` per deserializzazione | `src/models/entity.py` | ✅ | Inverso di `to_dict()` |
| 1.6 | Creare `ExtractionInput` (Pydantic BaseModel) con validatori | `src/models/input_schema.py` | ✅ | Campi obbligatori + validazione testo (no HTML, max 100K, no whitespace-only) |
| 1.7 | Creare `ExtractionOutput` con envelope `entities`/`meta`/`errors` | `src/models/output_schema.py` | ✅ | Sempre serializzabile a JSON valido anche su hard failure |
| 1.8 | Aggiornare `src/models/__init__.py` con export pubblico | `src/models/__init__.py` | ✅ | |

---

## FASE 2 — Configurazione & Feature Flags

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 2.1 | Creare `PipelineConfig` dataclass con tutte le soglie configurabili | `src/config.py` | ✅ | `regex_confidence`, `ner_confidence`, `lexicon_confidence`, `min_text_length_for_ner`, `ner_timeout_seconds`, `max_text_length`, `supported_ner_languages`, `source_priority` |
| 2.2 | Feature flags per motori (`engine_regex_enabled`, `engine_ner_enabled`, `engine_lexicon_enabled`) | `src/config.py` | ✅ | Abilitazione/disabilitazione granulare per motore |
| 2.3 | Feature flags per tipo entità (`entity_types_enabled`) | `src/config.py` | ✅ | Per type key: `EMAIL`, `CODICEFISCALE`, `PARTITAIVA`, `IBAN`, `TELEFONO`, `DATA`, `IMPORTO`, `NUMERO_PRATICA` |
| 2.4 | Blacklist valori configurable | `src/config.py` | ✅ | `blacklist_values: List[str]` |
| 2.5 | Caricamento da env vars (`NER_*`) e file YAML/JSON (`NER_CONFIG_FILE`) | `src/config.py` | ✅ | `from_env()` classmethod |
| 2.6 | Costante `LAYER_VERSION` centralizzata | `src/config.py` | ✅ | `"1.0.0"` — inclusa in ogni `ExtractionOutput.meta` |
| 2.7 | Helper `is_entity_type_enabled()` e `is_language_ner_supported()` | `src/config.py` | ✅ | |

---

## FASE 3 — Normalizzatore Interno

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 3.1 | Creare `normalize_text(text) -> (str, NormalizationLog)` | `src/entity_extraction/normalizer.py` | ✅ | 4 step: Unicode NFKC → strip → dedup spaces/tab → dedup newlines |
| 3.2 | Creare `NormalizationLog` e `NormalizationStep` dataclasses | `src/entity_extraction/normalizer.py` | ✅ | Log deterministico e riproducibile (richiesto da spec §step 2) |
| 3.3 | Metodo `to_dict()` su `NormalizationLog` | `src/entity_extraction/normalizer.py` | ✅ | Per logging strutturato e audit trail |

---

## FASE 4 — Validazione Input

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 4.1 | Creare `validate_input(raw: dict) -> (ExtractionInput, warnings)` | `src/entity_extraction/input_validator.py` | ✅ | Wrappa Pydantic ValidationError in `InputValidationError` |
| 4.2 | `InputValidationError` con lista errori strutturata | `src/entity_extraction/input_validator.py` | ✅ | Ogni errore ha `field`, `message`, `type` |
| 4.3 | Warning non bloccante per `lingua=null` | `src/entity_extraction/input_validator.py` | ✅ | Pipeline continua, NER sarà saltato |

---

## FASE 5 — Fix & Miglioramento Motori

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 5.1 | `regex_matcher.py`: accettare `PipelineConfig` opzionale | `src/entity_extraction/regex_matcher.py` | ✅ | Legge `regex_confidence`, `entity_types_enabled`, `regex_rule_version` |
| 5.2 | `regex_matcher.py`: aggiungere campo `version` alle Entity prodotte | `src/entity_extraction/regex_matcher.py` | ✅ | Default `"regex-v1.0"` |
| 5.3 | `regex_matcher.py`: **★FIX #5a★** PARTITAIVA regex più precisa (richiede prefisso IT o contesto) | `src/entity_extraction/regex_matcher.py` | ✅ | Pattern `r"\bIT\s?\d{11}\b"` + anchor su label P.IVA |
| 5.4 | `regex_matcher.py`: **★FIX #5b★** TELEFONO regex più restrittiva (non matcha numeri arbitrari) | `src/entity_extraction/regex_matcher.py` | ✅ | Tre pattern: +39, prefisso 0xx, prefisso 3xx |
| 5.5 | `regex_matcher.py`: aggiungere pattern DATA, IMPORTO, NUMERO_PRATICA | `src/entity_extraction/regex_matcher.py` | ✅ | DATA: dd/mm/yyyy; IMPORTO: € prefisso/suffisso; NUMERO_PRATICA: PRAT/N. |
| 5.6 | `regex_matcher.py`: skip entità vuote/whitespace (★FIX #2★) | `src/entity_extraction/regex_matcher.py` | ✅ | Guard `if not matched_text or not matched_text.strip()` |
| 5.7 | `ner_extractor.py`: **★FIX #6a★** thread-safe model loading (elimina global `_nlp_model`) | `src/entity_extraction/ner_extractor.py` | ✅ | Cache per-name con `threading.Lock` |
| 5.8 | `ner_extractor.py`: **★FIX #6b★** esecuzione selettiva (lingua, lunghezza, feature flag) | `src/entity_extraction/ner_extractor.py` | ✅ | Restituisce `(entities, skip_reasons)` |
| 5.9 | `ner_extractor.py`: **★FIX #6c★** exception handling non-bloccante | `src/entity_extraction/ner_extractor.py` | ✅ | Tutte le eccezioni catturate → skip_reasons |
| 5.10 | `ner_extractor.py`: aggiungere `version` alle Entity prodotte | `src/entity_extraction/ner_extractor.py` | ✅ | Usa `config.ner_model_name` |
| 5.11 | `ner_extractor.py`: `clear_model_cache()` per test isolation | `src/entity_extraction/ner_extractor.py` | ✅ | |
| 5.12 | `lexicon_enhancer.py`: **★FIX #7★ CRITICO** — `label=entity_label` non `label=lemma` | `src/entity_extraction/lexicon_enhancer.py` | ✅ | Bug: prima assegnava `label="ACME"` invece di `label="AZIENDA"` |
| 5.13 | `lexicon_enhancer.py`: accettare `PipelineConfig` | `src/entity_extraction/lexicon_enhancer.py` | ✅ | Feature flag per tipo e per motore |
| 5.14 | `lexicon_enhancer.py`: aggiungere `version` alle Entity prodotte | `src/entity_extraction/lexicon_enhancer.py` | ✅ | Default `"lexicon-v1.0"` |
| 5.15 | `merger.py`: **★FIX #8a★** leggere `source_priority` da `PipelineConfig` | `src/entity_extraction/merger.py` | ✅ | Non più costante hardcoded |
| 5.16 | `merger.py`: **★FIX #8b★** deduplicazione exact duplicates (stesso type+value+span) | `src/entity_extraction/merger.py` | ✅ | Fase pre-merge con `seen: set` |
| 5.17 | `merger.py`: **★FIX #8c★** ordinamento stabile: posizione → label → source | `src/entity_extraction/merger.py` | ✅ | **★FIX #3★** dalla spec — output deterministico |
| 5.18 | `merger.py`: scartare entità vuote prima del merge (★FIX #2★) | `src/entity_extraction/merger.py` | ✅ | |

---

## FASE 6 — Filtri Post-Estrazione

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 6.1 | Creare `filter_empty_entities(entities)` | `src/entity_extraction/post_filters.py` | ✅ | **★FIX #2★** centralizzato |
| 6.2 | Creare `apply_blacklist(entities, blacklist)` | `src/entity_extraction/post_filters.py` | ✅ | Case-insensitive |
| 6.3 | Creare `apply_type_flags(entities, entity_types_enabled)` | `src/entity_extraction/post_filters.py` | ✅ | Tipi sconosciuti → abilitato di default |
| 6.4 | Creare `normalize_canonical_format(entities)` | `src/entity_extraction/post_filters.py` | ✅ | DATA → ISO 8601, IMPORTO → 1234.56, CODICEFISCALE/PARTITAIVA → uppercase |
| 6.5 | Creare `apply_all_filters()` convenience wrapper | `src/entity_extraction/post_filters.py` | ✅ | Ordine garantito: empty → blacklist → flags → canonical |

---

## FASE 7 — Refactoring Pipeline Orchestrator

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 7.1 | Creare funzione `run_pipeline(raw_input, …) -> ExtractionOutput` | `src/entity_extraction/pipeline.py` | ✅ | Pipeline a 7 step come da spec |
| 7.2 | Step 1: validazione input (`validate_input`) | `src/entity_extraction/pipeline.py` | ✅ | Hard failure → `status="failed"` JSON valido |
| 7.3 | Step 2: normalizzazione testo (`normalize_text`) | `src/entity_extraction/pipeline.py` | ✅ | |
| 7.4 | Step 3: regex engine con feature flag check | `src/entity_extraction/pipeline.py` | ✅ | |
| 7.5 | Step 4: NER **selettivo** (lingua, lunghezza, flag) | `src/entity_extraction/pipeline.py` | ✅ | Skip reasons → `ExtractionOutput.fallbacks` |
| 7.6 | Step 5: lexicon enhancement con feature flag | `src/entity_extraction/pipeline.py` | ✅ | |
| 7.7 | Step 6: merge deterministico | `src/entity_extraction/pipeline.py` | ✅ | |
| 7.8 | Step 7: filtri finali + serializzazione `ExtractionOutput` | `src/entity_extraction/pipeline.py` | ✅ | |
| 7.9 | Global try/except: qualsiasi eccezione → JSON valido con `status="failed"` | `src/entity_extraction/pipeline.py` | ✅ | Invariante fondamentale della spec |
| 7.10 | Mantener wrapper backwards-compatible `extract_all_entities(text, …) -> List[Entity]` | `src/entity_extraction/pipeline.py` | ✅ | Per compatibilità con codice esistente |
| 7.11 | Integrazione timing per componente → `ExtractionOutput.meta.component_timings_ms` | `src/entity_extraction/pipeline.py` | ✅ | Via `observability.metrics.timer()` |
| 7.12 | Aggiornare `src/entity_extraction/__init__.py` con export pubblico | `src/entity_extraction/__init__.py` | ✅ | |

---

## FASE 8 — Observability

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 8.1 | Creare `PipelineLogger` con binding context (id_conv, id_msg) | `src/observability/logging.py` | ✅ | JSON formatter consumabile da ELK/Datadog senza parsing |
| 8.2 | `_JSONFormatter` per output JSON strutturato | `src/observability/logging.py` | ✅ | Fallback stdlib-only (senza structlog) |
| 8.3 | `log_entity_summary()` — log sintetico entità per tipo/sorgente | `src/observability/logging.py` | ✅ | |
| 8.4 | `log_fallback()` — log attivazione fallback | `src/observability/logging.py` | ✅ | |
| 8.5 | Creare metriche Prometheus (`prometheus-client` opzionale) | `src/observability/metrics.py` | ✅ | No-op stubs se libreria non installata — zero hard dependency |
| 8.6 | `ENTITIES_PER_MAIL` histogram per tipo entità | `src/observability/metrics.py` | ✅ | |
| 8.7 | `EXTRACTION_LATENCY` histogram per componente | `src/observability/metrics.py` | ✅ | |
| 8.8 | `ERRORS_TOTAL` counter per tipo (soft/hard) e componente | `src/observability/metrics.py` | ✅ | |
| 8.9 | `NER_SKIP_TOTAL` counter per ragione skip | `src/observability/metrics.py` | ✅ | |
| 8.10 | `PIPELINE_RUNS` counter per outcome (ok/failed) | `src/observability/metrics.py` | ✅ | |
| 8.11 | `timer()` context manager per misura latenza componente | `src/observability/metrics.py` | ✅ | |

---

## FASE 9 — Suite di Test Completa

| ID | Task | File/i | Stato | Note |
|----|------|--------|-------|------|
| 9.1 | **★FIX CRITICO★** Creare `tests/conftest.py` con fixture mancanti | `tests/conftest.py` | ✅ | `mock_regex_lexicon`, `mock_ner_lexicon`, `sample_input_dict` |
| 9.2 | Aggiornare `test_entity_extraction.py` per nuove API | `tests/unit/test_entity_extraction.py` | ✅ | Nuovi test: `run_pipeline`, `Entity.version`, `★FIX #7★`, feature flags, output contract |
| 9.3 | Aggiungere `TestEntityModel` con test immutabilità, `to_dict`, `from_dict`, `is_valid` | `tests/unit/test_entity_extraction.py` | ✅ | |
| 9.4 | Creare `test_normalizer.py` | `tests/unit/test_normalizer.py` | ✅ | 11 test: strip, dedup, NFKC, idempotenza, tab, empty |
| 9.5 | Creare `test_input_validator.py` | `tests/unit/test_input_validator.py` | ✅ | 18 test: happy path, campi mancanti, vincoli, HTML, lunghezza |
| 9.6 | Creare `test_post_filters.py` | `tests/unit/test_post_filters.py` | ✅ | 24 test: empty, blacklist, type flags, canonical format, combinato |
| 9.7 | Creare `tests/integration/test_pipeline_e2e.py` | `tests/integration/test_pipeline_e2e.py` | ✅ | E2E con email realistica sanitizzata, output contract, feature flags, snapshot |
| 9.8 | Creare `tests/robustness/test_robustness.py` | `tests/robustness/test_robustness.py` | ✅ | Input patologici: empty, HTML, whitespace, troppo lungo, lingua null/non supportata, dedup stress |

---

## Bug Fix Consolidati

| ID | Bug | Componente | Stato | Riferimento |
|----|-----|------------|-------|-------------|
| FIX #2 | Entità vuote/null causano crash downstream | `merger`, `regex_matcher`, `ner_extractor`, `lexicon_enhancer`, `post_filters` | ✅ Fix in `is_valid()` + guard in ogni componente | spec §Bug fix |
| FIX #3 | Ordine non deterministico delle entità | `merger` | ✅ Sort stabile: posizione → label → source | spec §Bug fix |
| FIX #3 | Firma con `label_id` (document vs per-label) | `pipeline`, tutti i moduli | ✅ Document-level ovunque, nessun `label_id` | spec §Bug fix |
| FIX #4 | Entity mutabile → bug sottili nel merger | `entity.py` | ✅ `frozen=True` su dataclass | codice |
| FIX #5a | PARTITAIVA regex matchava numeri arbitrari | `regex_matcher` | ✅ Pattern più stretto con `IT` prefix o anchor | codice |
| FIX #5b | TELEFONO regex troppo ampia | `regex_matcher` | ✅ 3 pattern specifici (+39, 0xx, 3xx) | codice |
| FIX #6a | Global `_nlp_model` non thread-safe | `ner_extractor` | ✅ Cache per-name con `threading.Lock` | codice |
| FIX #7 | `lexicon_enhancer` assegnava `label=lemma` invece di `label=entity_label` | `lexicon_enhancer` | ✅ Ora `label=entity_label` (es. "AZIENDA" non "ACME") | codice |
| FIX #8b | Entità duplicate esatte non deduplicate | `merger` | ✅ Dedup per `(label, text, start, end)` prima del merge | spec §Fusione |
| FIX CONF | Fixture `mock_regex_lexicon`, `mock_ner_lexicon` mancanti → tutti i test fallivano | `tests/conftest.py` | ✅ Creati con dati realistici | codice |

---

## Backlog — Miglioramenti Futuri

| ID | Descrizione | Priorità | Note |
|----|-------------|----------|------|
| BL-01 | Deduplicazione entità cross-messaggio (stesso thread/conversazione) | Media | Richiede contesto storico |
| BL-02 | Feedback loop — correzioni manuali annotate per aggiornare regole/modelli | Media | Collegato a DB layer |
| BL-03 | Affinamento tassonomia entità per layer routing/risposta automatica | Alta | Compatibilità retroattiva obbligatoria |
| BL-04 | LLM-NER dinamico (v3) — tool calling o1-preview/Qwen3 per OOV | Bassa | Merge 3-tier: RegEx > LLM-NER > spaCy |
| BL-05 | Fine-tuning modello NER su corpus email italiano dominio bancario | Bassa | Migliora recall su entità specifiche di dominio |
| BL-06 | Drift detection (chi-squared test su distribuzione entity types) | Media | Monitoraggio qualità long-term |
| BL-07 | Timeout hard per NER via `concurrent.futures` (non signal-based) | Media | Thread-safe su tutti gli OS |
| BL-08 | Endpoint FastAPI + Dockerfile per deploy containerizzato | Alta | Stack raccomandato da doc/Brainstorming-Thread v2 |
| BL-09 | Validazione checksum IBAN/CODICEFISCALE/PARTITAIVA | Media | Riduce falsi positivi |
| BL-10 | Evaluation framework (precision/recall per entity type su holdout set) | Alta | Necessario per A/B testing e rollback |

---

## Struttura finale del progetto

```
TT_EntityExtraction_NER/
├── pyproject.toml                          ✅ packaging + pytest + mypy + ruff config
├── requirements.txt                        ✅ runtime deps
├── requirements-dev.txt                    ✅ dev + observability deps
├── DEVELOPMENT_TRACKER.md                  ✅ questo file
├── doc/
│   ├── entity-extraction-layer.md          # specifica production-ready
│   ├── Brainstorming-Thread-...v2.md       # brainstorming pipeline completa
│   └── Brainstorming-Thread-...v3.md       # patch v3: tool calling + LLM-NER
├── src/
│   ├── __init__.py
│   ├── config.py                           ✅ PipelineConfig + LAYER_VERSION + env loading
│   ├── entity_extraction/
│   │   ├── __init__.py                     ✅ export pubblico
│   │   ├── input_validator.py              ✅ NUOVO — validazione input strutturata
│   │   ├── lexicon_enhancer.py             ✅ FIX #7 label bug + config-aware
│   │   ├── merger.py                       ✅ FIX #8a/b/c + config-driven
│   │   ├── ner_extractor.py                ✅ FIX #6a thread-safe + FIX #6b selettivo
│   │   ├── normalizer.py                   ✅ NUOVO — normalizzatore interno deterministico
│   │   ├── pipeline.py                     ✅ 7-step orchestrator + run_pipeline()
│   │   ├── post_filters.py                 ✅ NUOVO — blacklist, type flags, canonical
│   │   └── regex_matcher.py                ✅ FIX #5a/b + nuovi pattern + config-aware
│   ├── models/
│   │   ├── __init__.py                     ✅ export pubblico
│   │   ├── entity.py                       ✅ FIX #4 frozen + version field + is_valid
│   │   ├── input_schema.py                 ✅ NUOVO — Pydantic ExtractionInput
│   │   └── output_schema.py                ✅ NUOVO — ExtractionOutput JSON envelope
│   └── observability/
│       ├── __init__.py                     ✅ NUOVO — package
│       ├── logging.py                      ✅ NUOVO — PipelineLogger JSON strutturato
│       └── metrics.py                      ✅ NUOVO — Prometheus metrics (optional dep)
└── tests/
    ├── conftest.py                         ✅ FIX CRITICO — fixture fixture fixture
    ├── __init__.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_entity_extraction.py       ✅ aggiornato + nuovi test classi
    │   ├── test_normalizer.py              ✅ NUOVO — 11 test
    │   ├── test_input_validator.py         ✅ NUOVO — 18 test
    │   └── test_post_filters.py            ✅ NUOVO — 24 test
    ├── integration/
    │   ├── __init__.py                     ✅ NUOVO
    │   └── test_pipeline_e2e.py            ✅ NUOVO — E2E + snapshot non-regression
    └── robustness/
        ├── __init__.py                     ✅ NUOVO
        └── test_robustness.py              ✅ NUOVO — input patologici
```
