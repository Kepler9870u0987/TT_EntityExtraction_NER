# Entity Extraction Layer – Specifica Production Ready

## Scopo del documento
Questo documento descrive la logica, la struttura e le regole operative dello strato di Entity Extraction della pipeline di triage mail, consolidando le versioni v2 e v3 e integrando i bug fix e le feature individuate nel riepilogo completo originale.[file:1]

## Obiettivi del layer
- Estrarre entità strutturate dalle mail (es. identificativi cliente, riferimenti a pratiche, prodotti, importi, date rilevanti) in modo deterministico e riproducibile.[file:1]
- Fornire un contratto di input/output stabile verso gli altri layer della pipeline, riducendo al minimo le rotture dovute a cambi di formato.[file:1]
- Esporre segnali di confidenza, provenance e spiegabilità per ogni entità, per facilitare il debugging e le decisioni a valle.[file:1]

## Contratto di input
- **Sorgente**: mail già normalizzata dallo strato precedente (body testuale pulito, header rilevanti, metadati della conversazione).[file:1]
- **Formato**: JSON con campi obbligatori (id_conversazione, id_messaggio, testo_normalizzato, lingua, timestamp, mittente, destinatario) e campi opzionali (pre-annotazioni, regole di routing applicate, tag upstream).[file:1]
- **Vincoli**:
  - Non deve contenere HTML grezzo, allegati binari o payload non testuali.[file:1]
  - La lingua, se non nota, deve essere valorizzata a `null` ma il layer non deve fallire per questo motivo.[file:1]

## Contratto di output
- **Formato**: JSON con struttura ad albero, contenente:
  - `entities`: lista di entità estratte, ciascuna con `type`, `value`, `span` (start, end nel testo normalizzato), `confidence`, `source` (rule, NER, pattern ibrido), `version` (versione del modello/regola che l’ha prodotta).[file:1]
  - `meta`: informazioni di servizio (tempo di elaborazione, feature flag attivi, versione del layer, eventuali fallback attivati).[file:1]
  - `errors`: lista vuota se il layer ha terminato correttamente; popolata solo con errori non bloccanti (es. tempi di timeout di servizi opzionali).[file:1]
- **Invarianti**:
  - Il layer deve sempre restituire un JSON valido, anche in caso di errore interno grave (in quel caso `entities` è vuoto e `meta.status` è `"failed"`).[file:1]

## Architettura logica
- **Normalizer interno**: applica una normalizzazione locale minimale (es. trim, lowercasing controllato, rimozione spazi duplicati) che non deve mai contraddire quella a monte ma solo completarla.[file:1]
- **Motore rule-based**: set di regole deterministiche (regex, pattern lessicali, lookup su dizionari) per entità ad alta precisione e bassa ambiguità.[file:1]
- **Motore NER/statistico**: modelli ML/LLM chiamati tramite API interne, usati per entità ambigue o con variabilità linguistica elevata.[file:1]
- **Layer di fusione (entity resolver)**: unifica, deduplica e risolve conflitti tra entità provenienti da motore rule-based e NER secondo politiche di priorità e soglie.[file:1]
- **Adapter di output**: serializza nel formato JSON di contratto, applica mapping delle tipologie di entità e aggiunge metadati di tracing.[file:1]

## Flusso di elaborazione
1. Validazione schema di input (controllo presenza campi obbligatori, tipi di dato coerenti, limiti sulle dimensioni del testo).[file:1]
2. Normalizzazione interna soft del testo, con log deterministici per poter riprodurre la stessa trasformazione offline.[file:1]
3. Esecuzione del motore rule-based su tutte le mail, con raccolta di entità candidate e motivazione della regola attivata.[file:1]
4. Esecuzione selettiva del motore NER/statistico solo se:
   - la lingua è supportata;
   - il corpo del messaggio supera una certa soglia di lunghezza;
   - sono attivi i relativi feature flag.[file:1]
5. Fusione delle entità: deduplicazione per stesso `type` + `value` + `span`, risoluzione conflitti tramite:
   - priorità delle sorgenti (di default: rule-based > NER, overridabile per tipo di entità);
   - confronto delle confidence con soglie configurabili per tipo.[file:1]
6. Applicazione di filtri finali (blacklist valori, normalizzazione canonica di formati, es. date, importi).[file:1]
7. Serializzazione dell’output e logging strutturato.[file:1]

## Bug fix consolidati
- **Duplicazione entità tra v2 e v3**: è stata unificata la logica di normalizzazione e matching per gli identificativi cliente, evitando che la stessa entità venga emessa due volte con piccole differenze di formattazione.[file:1]
- **Gestione entità vuote o nulle**: sono stati introdotti controlli centralizzati nel resolver per scartare entità con `value` vuoto, whitespace-only o non coerente con il pattern atteso, evitando crash downstream.[file:1]
- **Ordine non deterministico delle entità**: è stata definita una policy di ordinamento stabile (prima per posizione nel testo, poi per tipo, infine per sorgente) per rendere i test riproducibili e semplificare il diff tra versioni.[file:1]
- **Error handling del motore NER**: le eccezioni del modello sono ora intercettate a livello di adapter, convertite in errori non bloccanti e propagate solo nei metadati, senza interrompere l’estrazione rule-based.[file:1]

## Feature implementate per la produzione
- **Feature flag granulari** per abilitare/disabilitare singoli tipi di entità o singoli motori (rule-based vs NER) per cluster di traffico (es. canary, rollout progressivi).[file:1]
- **Versionamento esplicito** di regole e modelli, con inclusione del campo `version` per ogni entità, per semplificare analisi A/B e rollback mirati.[file:1]
- **Metriche osservabili**: esport di counter/gauge su
  - numero medio di entità per mail per tipo;
  - latenza per componente (rule-based, NER, resolver);
  - tasso di errori soft vs hard.
  Queste metriche sono state derivate dal design originale ma portate a un livello operativo più fine.[file:1]
- **Logging strutturato** con:
  - trace id di conversazione;
  - id del messaggio;
  - lista sintetica di entità emesse per tipo e sorgente;
  - eventuali fallback attivati.
  I log sono pensati per essere consumabili da sistemi di osservabilità (es. ELK, Datadog) senza parsing fragile.[file:1]

## Linee guida di implementazione
- Mantenere il core del layer side-effect free: niente scritture su DB o sistemi esterni dentro il percorso critico di estrazione, ad eccezione del logging.[file:1]
- Rendere tutte le soglie (confidence, lunghezza minima del testo, timeout NER, ecc.) configurabili a runtime tramite configuration service o environment, evitando costanti hardcoded.[file:1]
- Fornire librerie comuni di normalizzazione e validazione da condividere tra regole e modelli, così da ridurre drift logico tra componenti.[file:1]

## Testing e qualità
- **Unit test** sul motore rule-based, con casi specifici per ogni pattern di estrazione e casi limite tratti dai bug segnalati nel documento v2/v3.[file:1]
- **Test di integrazione** end-to-end sulla pipeline, con snapshot degli output di entità per mail reali (sanitizzate), per garantire la non regressione tra release.[file:1]
- **Test di robustezza**: campagne mirate con input patologici (testo vuoto, testo molto lungo, encoding non valido) per verificare che il layer fallisca in modo controllato e osservabile.[file:1]

## Backlog di miglioramenti futuri
- Miglioramento della risoluzione delle entità duplicate cross-messaggio (es. thread della stessa conversazione), utilizzando contesto storico dove disponibile.[file:1]
- Introduzione di un sistema di feedback loop (es. correzioni manuali annotate a valle) per aggiornare periodicamente regole e modelli secondo quanto discusso nel riepilogo originale.[file:1]
- Ulteriore affinamento della tassonomia di entità per allinearla alle esigenze dei layer di routing e risposta automatica, mantenendo compatibilità retroattiva con il formato corrente.[file:1]
