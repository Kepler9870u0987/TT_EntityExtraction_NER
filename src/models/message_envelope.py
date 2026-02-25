"""
MessageEnvelope — oggetto portante condiviso da tutta la pipeline.

È il contratto di passaggio dati tra un layer e il successivo.
Viene creato dall'email parser e arricchito a cascata da ogni layer.

Struttura:
  ┌─────────────────────────────────┐
  │  email_context  (Email Parser)  │  testo + header email
  │  triage         (LLM Layer)     │  topic / sentiment / priority
  │  postprocessing (Post-proc)     │  confidence adjusted, observations
  │  ner_entities   (questo layer)  │  entità estratte
  └─────────────────────────────────┘

Il layer Entity Extraction legge da `email_context`, arricchisce `ner_entities`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EmailContext:
    """
    Campi prodotti dall'email parser — obbligatori per il layer NER.

    Tutti i layer a valle dipendono da questo oggetto.
    """
    message_id:          str
    id_conversazione:    str
    testo_normalizzato:  str
    mittente:            str
    destinatario:        str
    timestamp:           str                       # ISO-8601
    lingua:              Optional[str]  = "it"
    oggetto:             Optional[str]  = None
    allegati:            List[str]      = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EmailContext":
        return cls(
            message_id         = d["message_id"],
            id_conversazione   = d.get("id_conversazione", d["message_id"]),
            testo_normalizzato = d["testo_normalizzato"],
            mittente           = d["mittente"],
            destinatario       = d["destinatario"],
            timestamp          = d["timestamp"],
            lingua             = d.get("lingua", "it"),
            oggetto            = d.get("oggetto"),
            allegati           = d.get("allegati", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id":          self.message_id,
            "id_conversazione":    self.id_conversazione,
            "testo_normalizzato":  self.testo_normalizzato,
            "mittente":            self.mittente,
            "destinatario":        self.destinatario,
            "timestamp":           self.timestamp,
            "lingua":              self.lingua,
            "oggetto":             self.oggetto,
            "allegati":            self.allegati,
        }


@dataclass
class MessageEnvelope:
    """
    Oggetto portante completo della pipeline.

    Creato dal layer email-parser; ogni layer successivo aggiunge la sua
    sezione senza sovrascrivere quelle altrui.

    Utilizzo:
        # Layer email-parser
        env = MessageEnvelope(email_context=EmailContext(...))

        # Layer postprocessing
        env.postprocessing = postprocessing_result_dict

        # Layer NER (questo)
        result = run_pipeline(env.to_ner_input())
        env.ner_entities = result

    Serializzazione:
        json.dumps(env.to_dict())  # persiste l'intero stato tra layer
        MessageEnvelope.from_dict(d)  # ricostruisce da storage / message bus
    """
    email_context:   EmailContext
    triage:          Optional[Dict[str, Any]] = None   # LLM layer output
    postprocessing:  Optional[Dict[str, Any]] = None   # postprocessing result
    ner_entities:    Optional[Dict[str, Any]] = None   # output di questo layer

    # ---------------------------------------------------------------------------
    # Costruttore da dict (de-serializzazione da storage / Kafka / Redis)
    # ---------------------------------------------------------------------------

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MessageEnvelope":
        return cls(
            email_context  = EmailContext.from_dict(d["email_context"]),
            triage         = d.get("triage"),
            postprocessing = d.get("postprocessing"),
            ner_entities   = d.get("ner_entities"),
        )

    @classmethod
    def from_postprocessing_result(
        cls,
        postprocessing: Dict[str, Any],
        *,
        # Questi campi vengono dall'email parser; passali esplicitamente
        testo_normalizzato: str,
        mittente: str,
        destinatario: str,
        timestamp: Optional[str] = None,
        lingua: Optional[str] = "it",
        oggetto: Optional[str] = None,
    ) -> "MessageEnvelope":
        """
        Costruisce un MessageEnvelope a partire dal postprocessing_result JSON
        (output del layer precedente) + i campi email che solo il parser ha.

        Questo è il metodo da usare nel periodo di transizione, quando
        l'email parser non emette ancora un MessageEnvelope completo.
        """
        ts = timestamp or postprocessing.get("created_at") or "1970-01-01T00:00:00Z"

        ctx = EmailContext(
            message_id         = postprocessing["message_id"],
            id_conversazione   = postprocessing["message_id"],
            testo_normalizzato = testo_normalizzato,
            mittente           = mittente,
            destinatario       = destinatario,
            timestamp          = ts,
            lingua             = lingua,
            oggetto            = oggetto,
        )
        return cls(
            email_context  = ctx,
            postprocessing = postprocessing,
            triage         = postprocessing.get("triage"),
        )

    # ---------------------------------------------------------------------------
    # Costruisce l'input dict per run_pipeline()
    # ---------------------------------------------------------------------------

    def to_ner_input(self) -> Dict[str, Any]:
        """
        Produce il dict pronto per ``run_pipeline()``.
        Arricchisce automaticamente con pre_annotazioni e tag_upstream
        ricavati dai layer precedenti già presenti nell'envelope.
        """
        ctx = self.email_context

        # Entità già estratte dall'upstream (pre_annotazioni)
        pre_annotazioni: List[Dict[str, Any]] = []
        if self.postprocessing:
            pre_annotazioni = self.postprocessing.get("entities", [])

        # Topic label come tag_upstream
        tag_upstream: List[str] = []
        if self.triage:
            tag_upstream = [
                t["labelid"] for t in self.triage.get("topics", [])
            ]

        return {
            "id_messaggio":       ctx.message_id,
            "id_conversazione":   ctx.id_conversazione,
            "testo_normalizzato": ctx.testo_normalizzato,
            "lingua":             ctx.lingua,
            "timestamp":          ctx.timestamp,
            "mittente":           ctx.mittente,
            "destinatario":       ctx.destinatario,
            "pre_annotazioni":    pre_annotazioni,
            "tag_upstream":       tag_upstream,
        }

    # ---------------------------------------------------------------------------
    # Serializzazione
    # ---------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "email_context":  self.email_context.to_dict(),
            "triage":         self.triage,
            "postprocessing": self.postprocessing,
            "ner_entities":   self.ner_entities,
        }
