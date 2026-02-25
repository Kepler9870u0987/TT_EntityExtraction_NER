"""
Esempio concreto: come alimentare il layer Entity Extraction
partendo dall'output dei layer precedenti contenuti in layer_io/.

Struttura della catena:
    [Email Parser]  →  crea MessageEnvelope (testo + header completi)
          ↓
    [Candidate Generator]  →  CandidateGenerateorDeterministicOutput.json
          ↓
    [LLM Triage Layer]     →  LLM_LayerOutput.json
          ↓
    [Post-processing]      →  postprocessing_result.json + arricchisce MessageEnvelope
          ↓
    [Entity Extraction NER]  ←  legge env.to_ner_input(), scrive env.ner_entities

I campi email (testo_normalizzato, mittente, destinatario, timestamp) fanno
parte del MessageEnvelope creato dall'email parser e propagato in tutta la catena.
Usare MessageEnvelope.from_postprocessing_result() nel periodo di transizione
quando l'email parser non emette ancora il MessageEnvelope completo.
"""

import json
import sys
from pathlib import Path

# Aggiungi la root del progetto al path (se eseguito direttamente)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.entity_extraction.pipeline import run_pipeline
from src.models.message_envelope import MessageEnvelope

# ---------------------------------------------------------------------------
# 1. Carica l'output del layer di post-processing precedente
# ---------------------------------------------------------------------------
LAYER_IO = Path(__file__).parent

with open(LAYER_IO / "postprocessing_result.json", encoding="utf-8") as f:
    postprocessing = json.load(f)

# ---------------------------------------------------------------------------
# 2. Costruisci il MessageEnvelope
#
#    In PRODUZIONE: l'email parser emette già un MessageEnvelope completo
#    serializzato su Kafka/Redis con tutti i campi inclusi.
#    Ogni layer successivo lo carica con MessageEnvelope.from_dict(d).
#
#    Nel PERIODO DI TRANSIZIONE (email parser non ancora aggiornato):
#    usa from_postprocessing_result() passando i campi email esplicitamente.
#    Questi valori si recuperano dal message store indicizzato per message_id.
# ---------------------------------------------------------------------------

# --- TRANSIZIONE: email parser non ancora aggiornato -----------------------
# I valori sotto vengono dal tuo message store / DB / cache
# (indicizzati per message_id = postprocessing["message_id"])
env = MessageEnvelope.from_postprocessing_result(
    postprocessing,
    testo_normalizzato=(
        "Gentile team, Volevo confermare che i dati sono corretti: "
        "Codice Fiscale: RSSMRA80A01H501U, come discusso. "
        "Ho verificato tutti i dettagli e sono d'accordo con i termini proposti: "
        "durata 24 mesi, rata mensile di \u20ac 450,00. "
        "Potete inviarmi il contratto definitivo in formato PDF editabile "
        "per apporre la firma digitale? "
        "Potete fornirmi un preventivo aggiornato con le nuove tariffe 2024? "
        "In allegato trovate il documento firmato e i dati aggiuntivi richiesti "
        "(IBAN per domiciliazione, delega amministrativa). "
        "Contatto: mario.rossi@example.it, tel. +39 02 98765432. "
        "Cordiali saluti, Mario Rossi"
    ),
    mittente     = "mario.rossi@example.it",
    destinatario = "supporto@banca.it",
    timestamp    = "2026-02-24T12:02:09Z",
    lingua       = "it",
)

# --- PRODUZIONE: email parser già aggiornato --------------------------------
# env = MessageEnvelope.from_dict(json.loads(redis_client.get(message_id)))

# ---------------------------------------------------------------------------
# 3. Costruisci l'input per run_pipeline() dall'envelope (zero boilerplate)
# ---------------------------------------------------------------------------
raw_input = env.to_ner_input()

topic_labels     = raw_input["tag_upstream"]
upstream_entities = raw_input["pre_annotazioni"]

print("=" * 60)
print("INPUT → topic labels upstream:", topic_labels)
print("INPUT → pre_annotazioni upstream:", [e["label"] for e in upstream_entities])
print("=" * 60)

result = run_pipeline(raw_input)

# ---------------------------------------------------------------------------
# 4. Arricchisci l'envelope con l'output NER e stampa
# ---------------------------------------------------------------------------
output = json.loads(result.to_json())

# Scrivi il risultato NER nell'envelope → il layer successivo troverà tutto
env.ner_entities = output

print(f"\nStatus: {output['meta']['status']}")
print(f"Layer version: {output['meta']['layer_version']}")
print(f"Processing time: {output['meta']['processing_time_ms']:.1f} ms")
print(f"Entità estratte: {output['meta']['entity_count']}\n")

for ent in output["entities"]:
    print(
        f"  [{ent['type']:16s}] {ent['value']:<35s} "
        f"conf={ent['confidence']:.2f}  src={ent['source']}"
    )

if output["errors"]:
    print("\nErrori:", output["errors"])

# ---------------------------------------------------------------------------
# 5. Persisti il MessageEnvelope completo
#    In produzione: json.dumps(env.to_dict()) → Redis / Kafka / DB
#    (il layer successivo fa MessageEnvelope.from_dict(json.loads(...)))
# ---------------------------------------------------------------------------
out_path = LAYER_IO / "ner_layer_output.json"
with open(out_path, "w", encoding="utf-8") as f:
    # Salva solo la sezione NER (come prima)
    json.dump(output, f, ensure_ascii=False, indent=2)

envelope_path = LAYER_IO / "message_envelope.json"
with open(envelope_path, "w", encoding="utf-8") as f:
    # Salva l'envelope completo — pronto per essere consumato dal layer successivo
    json.dump(env.to_dict(), f, ensure_ascii=False, indent=2)

print(f"\nNER output:        {out_path}")
print(f"MessageEnvelope:   {envelope_path}  ← passa questo al layer successivo")
