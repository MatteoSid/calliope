# Calliope — Roadmap di refactor

> Roadmap operativa derivata da [ANALISI_REFACTOR.md](ANALISI_REFACTOR.md).
> Gli ID tra parentesi (C1, A2, S3, D1…) rimandano alle problematiche censite nell'analisi.

## Stato di avanzamento

Legenda: ✅ completato · 🚧 in corso · ⬜ da fare

| Step | Stato | Note |
|------|-------|------|
| 0.1 Smoke test | ✅ | `docs/smoke-test.md` |
| 0.2 Pulizia repo | ✅ | notebook in `notebooks/`, `CLAUDE.md` committato |
| 1.1 Lockfile | ✅ | migrato a **uv**: `uv.lock` committato |
| 1.2 Struttura package | ✅ | handlers/transcription/media/storage; entry point `calliope` |
| 1.3 Tooling ruff/mypy | ⬜ | |
| 1.4 Config pydantic-settings | ✅ | `calliope/settings.py` |
| 1.5 Bootstrap esplicito | ⬜ | |
| 2.1 Storage riscritto | ⬜ | |
| 2.2 `/lang` end-to-end | ✅ | |
| 2.3 Device detection | ⬜ | parziale (usa ctranslate2) |
| 2.4 Media processing | ⬜ | |
| 2.5 Flood control retry | ✅ | |
| 2.6 `/stats` su Mongo | ✅ | |
| 2.7 Silence detection | ✅ | reaction 🔇 |
| 3.1 Inferenza off-loop | ⬜ | |
| 3.2 Streaming redesign | ⬜ | |
| 3.3 Limiti d'uso | ⬜ | |
| 3.4 Modulo admin | ✅ | |
| 3.5 Graceful shutdown | ⬜ | |
| 4.1 Hardening Docker | ⬜ | parziale (base uv/cuDNN9) |
| 4.2 Logging privacy | ⬜ | |
| 4.3 Dipendenze | ✅ | aggiornate + potate via uv |
| 4.4 Test automatici | ⬜ | |
| 4.5 CI | ⬜ | |
| 4.6 Documentazione | ⬜ | |

## Come usare questo documento

- Ogni fase produce un progetto **funzionante e rilasciabile**: non si passa alla fase successiva con il bot rotto.
- Ogni step ha: obiettivo, problemi risolti, attività (checklist), criteri di accettazione.
- Ordine consigliato: gli step dentro una fase sono ordinati per dipendenza; step senza dipendenze reciproche sono segnalati come parallelizzabili.
- Convenzione branch: un branch per step (`refactor/1.2-package-layout`), merge su `main` solo a criteri di accettazione soddisfatti.
- A fine fase: tag `v0.2.0`, `v0.3.0`, `v0.4.0`, `v1.0.0`.

### Regola d'oro

**Prima di toccare qualsiasi cosa** (Fase 0), congelare il comportamento attuale: il refactor deve preservare le funzionalità elencate in ANALISI_REFACTOR.md § "Funzionalità da preservare".

---

## Fase 0 — Baseline e rete di sicurezza

*Obiettivo: poter verificare a ogni step che il bot funzioni ancora. Durata indicativa: mezza giornata.*

### Step 0.1 — Smoke test manuale documentato

**Obiettivo:** una checklist di verifica manuale ripetibile, visto che non esistono test automatici e l'architettura attuale non permette di scriverne.

**Attività:**
- [x] Creare `docs/smoke-test.md` con la sequenza: avvio via `docker compose up`, `/start`, `/help`, invio vocale breve (<1 min), invio vocale lungo (>4096 caratteri di trascrizione, per lo split), invio video note, invio video (→ file .txt con timestamp), `/lang es` + verifica risposta, verifica documenti su Mongo (`users_db`, `groups_db`), test in un gruppo.
- [x] Eseguirla sullo stato attuale e annotare il comportamento osservato. La parte automatizzabile (avvio compose, log, connessione Mongo, caricamento modello) è verificata a ogni build; le interazioni Telegram (invio vocali/comandi) restano da eseguire manualmente dall'owner.

**Criteri di accettazione:** la checklist esiste, è stata eseguita una volta, e distingue "comportamento da preservare" da "bug noto da fixare in Fase 2". ✅

> **Nota:** i bug 2.2/2.6/2.7 citati nella versione originale (statistiche video note, `/lang` senza effetto, `/stats` rotto) sono già stati **risolti** nelle sessioni precedenti; la checklist riflette lo stato corrente.

### Step 0.2 — Pulizia working directory

**Obiettivo:** repository pulito prima di iniziare.

**Attività:**
- [x] Rimuovere `temp_audio.wav`, svuotare `logs/` (contengono dati utente — S1), spostare i notebook (`yt_download.ipynb`, `diarization.ipynb`, `calliope_segmentation.ipynb`) in una cartella `notebooks/`.
- [x] Aggiungere `logs/` al `.gitignore` (oggi è coperto solo da `*.log`).
- [x] Decidere il destino di `CLAUDE.md`: **committato** (guida di progetto).

**Criteri di accettazione:** `git status` pulito, nessun file con dati utente nella working tree. ✅

---

## Fase 1 — Fondamenta

*Obiettivo: packaging sano, configurazione unica e validata, bootstrap esplicito, tooling che impedisce la regressione della qualità. Nessun cambio di comportamento visibile all'utente. Durata indicativa: 2-3 giornate.*

### Step 1.1 — Lockfile e igiene repository (D1)

**Attività:**
- [ ] Rimuovere `poetry.lock` dal `.gitignore` e committare il lockfile.
- [ ] Rigenerarlo (`poetry lock`) per verificare che sia consistente con `pyproject.toml`.
- [ ] Verificare che la build Docker funzioni da un clone fresco (`git clone` in una dir temporanea + `docker build`).

**Criteri di accettazione:** `docker build` va a buon fine su un clone fresco. Build riproducibile.

### Step 1.2 — Ristrutturazione del package (A5, D4)

**Obiettivo:** layout standard, package installabile, addio hack `PYTHONPATH=.`.

**Struttura target:**

```
calliope/
├── __init__.py
├── __main__.py            # solo: from calliope.main import main; main()
├── main.py                # bootstrap: settings → logging → db → modello → application
├── settings.py            # (step 1.4)
├── handlers/              # ex commands/: start.py, help.py, language.py, transcribe.py, timestamp.py
│   └── __init__.py
├── transcription/         # ex models/: whisper.py (motore), formatting.py (timestamp, split)
│   └── __init__.py
├── media/                 # (step 2.5) download + estrazione audio
│   └── __init__.py
└── storage/               # ex utils/MongoClient.py: mongo.py, models.py
    └── __init__.py
```

**Attività:**
- [x] Aggiungere `__init__.py` ovunque; eliminare il livello `calliope/src/`.
- [x] Rinominare `MongoClient.py` → `storage/mongo.py`; smembrare `utils.py` (lo split messaggi + `format_timedelta` in `transcription/formatting.py`, `detect_silence` in `media/silence.py`, `message_type` inlinato in `handlers/transcribe.py`, `title`/figlet eliminati). Il notifier admin → `calliope/notifier.py`, il logger → `calliope/logging_setup.py`.
- [x] Definire l'entry point in `pyproject.toml`: **`[project.scripts] calliope = "calliope.main:main"`** (formato uv/PEP 621; il progetto è ora installabile con build-backend hatchling).
- [x] Aggiornare `makefile` (`uv run calliope`), `docker-compose.yml` (usa il `CMD`) e Dockerfile (`uv sync` a due fasi che installa il progetto → `CMD ["calliope"]`, figlet rimosso).
- [x] `configs.yaml` già assente (rimosso in precedenza).

**Criteri di accettazione:** il bot parte con `calliope` (console script) senza `PYTHONPATH`; smoke test 0.1 verde (build + avvio validati). ✅

**Nota:** questo step è quasi solo `git mv` + fix import. Non cambiare logica qui: le funzioni si spostano identiche, si rifattorizzano nelle fasi successive.

### Step 1.3 — Tooling: ruff, mypy, pre-commit (§6, codice morto §5b)

*Parallelizzabile con 1.1; da fare dopo 1.2 per non lintare file che spariranno.*

**Attività:**
- [ ] Aggiungere a `pyproject.toml`: `ruff` (lint + format, regole: `E`, `F`, `I`, `B`, `UP`, `N`), `mypy` (inizialmente permissivo: `ignore_missing_imports`, poi stretto sui moduli nuovi), gruppo dev.
- [ ] Configurare `pre-commit` con ruff + ruff-format + mypy.
- [ ] Prima passata di pulizia guidata dal linter:
  - [ ] rimuovere `from venv import logger` (C3, parte import),
  - [ ] rimuovere import inutilizzati e i `except:` nudi,
  - [ ] eliminare **solo il codice realmente morto** censito in §5b dell'analisi: `ConfigsNotFoundError`, blocco commentato `change_language` del modello, chiavi morte di `configs.yaml`, `title()`/figlet (togliere anche `figlet` dal Dockerfile),
  - [ ] **parcheggiare le feature incompiute** (§5a dell'analisi) — `stats.py`, `admin_feature.py`, `detect_silence`, `format_timedelta` **non si eliminano**: si applicano i fix minimi per far passare linter e mypy (import mancanti, annotazioni di tipo) e si marcano con un commento che rimanda allo step dedicato (`/stats` → 2.6, silence detection → 2.7, modulo admin → 3.4).
- [ ] Uniformare la lingua di codice/commenti/docstring (raccomandato: inglese).

**Criteri di accettazione:** `ruff check .` e `mypy calliope` passano; pre-commit installato; zero codice morto residuo; le feature incompiute compilano e sono rintracciabili dai commenti-segnaposto.

### Step 1.4 — Configurazione unificata con pydantic-settings (A6, A7, C9)

**Obiettivo:** un solo oggetto `Settings`, validato all'avvio, un solo posto dove si legge l'ambiente.

**Attività:**
- [ ] Aggiungere `pydantic-settings`; creare `calliope/settings.py`:
  ```python
  class Settings(BaseSettings):
      telegram_token: SecretStr
      mongo_uri: str = "mongodb://localhost:27017"
      mongo_db_name: str = "calliope"
      admin_chat_id: int | None = None
      whisper_model: str = "deepdml/faster-whisper-large-v3-turbo-ct2"
      device: Literal["auto", "cuda", "cpu"] = "auto"
      default_language: str | None = None      # None = auto-detect
      max_media_duration_s: int = 1800          # usato in 3.3
      silence_threshold: int = 70               # usata in 2.7
      log_level: str = "INFO"
      model_config = SettingsConfigDict(env_file=".env")
  ```
- [ ] Eliminare `configs_manager.py`, `configs.yaml`, `arg_parser.py` (il flag `-v` diventa `LOG_LEVEL=DEBUG`).
- [ ] Errore chiaro e immediato all'avvio se `TELEGRAM_TOKEN` manca.
- [ ] Aggiornare `.env.example` con **tutte** le variabili (incluso `ADMIN_CHAT_ID`, oggi assente) e `docker-compose.yml` di conseguenza.

**Criteri di accettazione:** avvio senza token → messaggio d'errore esplicito; `.env` caricato anche in locale senza docker; nessun `os.environ`/`os.getenv` fuori da `settings.py`.

### Step 1.5 — Bootstrap esplicito, addio side effects a import time (A2, A3)

**Obiettivo:** importare un modulo di Calliope non deve fare nulla; tutto succede in `main()`.

**Attività:**
- [ ] `main.py` con sequenza esplicita: `settings = Settings()` → `setup_logging(settings)` → `storage = MongoStorage(settings)` → `transcriber = WhisperTranscriber(settings)` → costruzione `Application`.
- [ ] Iniettare le dipendenze negli handler via `application.bot_data["storage"] = storage` ecc. (o partial/closure); rimuovere `calliope_db_init()` + `lru_cache`, il `__new__` singleton di `WhisperInferenceModel` e tutte le istanziazioni a livello di modulo in `handlers/*`.
- [ ] `setup_logging`: sink stdout sempre (siamo in Docker), file opzionale con `rotation`/`retention` (vedi 4.2); rimuovere il fragile `logger.remove(0)` a favore di `logger.remove()`.
- [ ] Il caricamento del modello Whisper avviene una sola volta in `main()`, con log del device scelto.

**Criteri di accettazione:** `python -c "import calliope.handlers.transcribe"` non carica il modello, non tocca Mongo, non parsea argv, non stampa banner; smoke test 0.1 verde.

---

## Fase 2 — Correttezza e completamento feature

*Obiettivo: fixare tutti i bug noti mantenendo l'architettura, e portare a compimento le feature incompiute lato utente (`/stats`, silence detection). Durata indicativa: 4-5 giornate.*

### Step 2.1 — Storage MongoDB riscritto (C2, C6, C7, A8)

**Obiettivo:** operazioni atomiche, dati tipizzati, fallimenti onesti.

**Attività:**
- [ ] Riscrivere `storage/mongo.py`:
  - [ ] upsert atomici: `update_one(filter, {"$set": ..., "$inc": ..., "$setOnInsert": ...}, upsert=True)` al posto di `find_one` + `insert`/`update` (elimina le race e i doppi round-trip);
  - [ ] indici unici su `user_id` e `group_id` creati all'avvio;
  - [ ] date come `datetime` UTC (`datetime.now(timezone.utc)`), non stringhe;
  - [ ] durata presa dal **media effettivo** (voice/video_note/video), non da `message.voice` — fixa C2; passarla come parametro esplicito (`record_usage(update, duration_s)`) invece di ri-estrarla dentro lo storage;
  - [ ] `get_language` robusto: ritorna `None` se utente/gruppo assente o chat type non gestito, niente `KeyError`/`TypeError` — pronto per 2.2;
  - [ ] via il bare `except:` dell'`__init__`: se Mongo è irraggiungibile all'avvio, log `warning` esplicito e oggetto in modalità degradata **dichiarata** (flag `available`, metodi no-op che loggano a `debug`), oppure fail-fast configurabile: scegliere e documentare;
  - [ ] eliminare `mongo_uri` calcolato a livello di modulo (usa `settings.mongo_uri`), il parametro fantasma `time_used`, il doppio `str(str(...))`.
- [ ] Deduplicare `update_single_user`/`update_group`: un metodo comune per il documento utente, il gruppo compone.
- [ ] **Migrazione dati**: script one-shot `scripts/migrate_dates.py` che converte le date-stringa esistenti in `datetime` (o decisione esplicita di azzerare il DB, essendo un progetto personale).

**Criteri di accettazione:** vocale e video note aggiornano entrambi le statistiche (verifica su Mongo); due messaggi ravvicinati dello stesso utente nuovo non creano documenti duplicati; con Mongo spento il bot trascrive comunque e logga il degrado una sola volta.

### Step 2.2 — `/lang` funzionante end-to-end (C1, C7, C10-parte)

**Obiettivo:** la lingua scelta viene davvero usata dalla trascrizione.

**Attività:**
- [ ] `WhisperTranscriber.transcribe(audio, language: str | None)`: passa `language` a `model.transcribe()` (None = auto-detect); rimuovere `self.language = "it"` morto.
- [ ] Nel handler di trascrizione: `language = storage.get_language(update) or settings.default_language` prima di trascrivere.
- [ ] `handlers/language.py`: validare l'input contro i codici lingua supportati da faster-whisper (lista disponibile nel package); rispondere con errore chiaro se il codice non è valido; **separare** i due casi oggi confusi dall'`except` unico (argomento mancante → messaggio di uso; errore DB → messaggio di errore + log).
- [ ] Aggiungere `/lang` senza argomenti → mostra lingua corrente.

**Criteri di accettazione:** `/lang en` + vocale in inglese → trascrizione forzata in inglese; `/lang xx` → messaggio "lingua non supportata"; `/lang` da solo → lingua corrente; il tutto anche nei gruppi.

### Step 2.3 — Device detection reale (C3)

**Attività:**
- [ ] `device = settings.device`; se `"auto"`: prova CUDA con fallback dichiarato a CPU. Rimuovere la dipendenza da `torch` per la detection (usare `ctranslate2.get_cuda_device_count()`, così `torch` diventa eliminabile in 4.4).
- [ ] Log esplicito all'avvio: modello, device, compute type.

**Criteri di accettazione:** il bot parte e trascrive sia su macchina con GPU sia senza (CPU), senza modifiche al codice.

### Step 2.4 — Media processing unificato e chiusura risorse (A4, C8, C10)

**Obiettivo:** un solo modulo per download → estrazione audio → array numpy, usato da entrambi gli handler.

**Attività:**
- [ ] Creare `media/extract.py` con un'unica funzione `async download_audio(bot, message) -> AudioData` che gestisce i tre tipi (voice, video_note, video) e ritorna array + sample rate + durata.
- [ ] Sostituire moviepy con **ffmpeg diretto** (`ffmpeg -i in.mp4 -vn -ac 1 -ar 16000 out.wav` via `asyncio.create_subprocess_exec`): elimina la dipendenza (D3), i leak di `VideoFileClip` (C10) e il doppio passaggio ogg→librosa. In alternativa minimale: tenere moviepy ma con `with closing(...)`.
- [ ] Eliminare `message_type()` a favore di un match esplicito sul tipo di attachment con ramo `else` che solleva un errore parlante (fixa C8).
- [ ] `timestamp.py`: scrivere il file di trascrizione con context manager, o meglio inviare il contenuto da memoria con `io.BytesIO` (niente secondo `TemporaryDirectory`).

**Criteri di accettazione:** vocale, video note e video funzionano; `lsof`/`ps` non mostrano processi ffmpeg o file handle residui dopo N trascrizioni; nessun import di moviepy residuo.

### Step 2.5 — Invio messaggi: retry corretto sul flood control (C5)

*Il ridisegno completo dello streaming è in 3.2; qui si fixa solo la perdita di testo.*

**Attività:**
- [ ] Estrarre l'invio/edit in una funzione `send_or_edit_with_retry(...)` che su `RetryAfter` attende con `await asyncio.sleep(e.retry_after)` e **riprova la stessa parte** (max N tentativi, poi errore).
- [ ] Sostituire `time.sleep` (blocca l'event loop).

**Criteri di accettazione:** con un audio molto lungo che scatena flood control, la trascrizione finale in chat è completa (confronto con l'output del modello nei log di debug).

### Step 2.6 — Riscrittura `/stats` su Mongo (C4)

*Dipende da 2.1: i dati su Mongo devono essere coerenti (durate corrette anche per i video note, date `datetime`).*

**Obiettivo:** utenti e gruppi possono vedere quanto usano Calliope.

**Attività:**
- [ ] Riscrivere `handlers/stats.py` leggendo da Mongo (oggi legge da un file `stast.json` che non esiste più):
  - [ ] in chat privata: statistiche personali (numero trascrizioni, tempo di parlato totale, primo/ultimo uso);
  - [ ] nei gruppi: statistiche del gruppo + classifica dei membri per tempo di parlato (`members_stats` ordinato — **senza pandas**, basta un `sorted()`);
  - [ ] caso "nessun dato ancora": messaggio chiaro, non "Stats not found" con `logger.error`.
- [ ] Reimplementare `format_timedelta` pulita (oggi commentata in `utils.py`) in `transcription/formatting.py`, con test.
- [ ] Registrare l'handler `/stats` in `main.py` (oggi commentato) e aggiungerlo alla lista comandi di BotFather / `set_my_commands`.
- [ ] Aggiornare `/help` menzionando `/stats`.

**Criteri di accettazione:** `/stats` in privato mostra i propri dati reali dal DB; in un gruppo mostra la classifica dei membri; i numeri sono coerenti con i documenti Mongo; nessun uso di pandas.

### Step 2.7 — Silence detection integrata (§5a)

*Dipende da 2.4 (il modulo media espone l'audio caricato) e 2.1 (statistiche).*

**Obiettivo:** non sprecare inferenza su audio in cui nessuno parla; l'utente riceve una reaction 🔇 al posto della trascrizione.

**Attività:**
- [ ] Fixare e spostare `detect_silence` (oggi in `utils.py`, mai integrata) in `media/silence.py`:
  - [ ] semantica corretta: rilevare il silenzio sull'**intero audio**, non solo in coda (oggi conta i blocchi finali e si ferma al primo blocco non muto);
  - [ ] allineare finestra e docstring (oggi il passo è di 1 s ma la docstring parla di mezzi secondi);
  - [ ] annotazione di ritorno corretta (oggi `-> int` ma ritorna una tupla);
  - [ ] soglia configurabile: `silence_threshold` in `Settings` (step 1.4), non hardcoded a 70.
- [ ] Eseguire il check **prima** dell'inferenza in entrambi gli handler (trascrizione e timestamp).
- [ ] Valutare in aggiunta il `vad_filter=True` di faster-whisper come conferma sui casi borderline (il check energetico è il pre-filtro economico, il VAD la rete di sicurezza).
- [ ] Audio muto → reaction 🔇 via `set_message_reaction`, **nessun messaggio** e nessuna trascrizione; non incrementare `total_speech_time` nelle statistiche.

**Criteri di accettazione:** un vocale muto riceve la reaction 🔇 e dai log risulta zero inferenza; un vocale parlato segue il flusso normale; la soglia è modificabile da `.env` senza toccare il codice.

---

## Fase 3 — Architettura e robustezza

*Obiettivo: il bot serve più utenti contemporaneamente, resta reattivo durante le trascrizioni e l'owner ha il suo toolkit di gestione. Durata indicativa: 3-4 giornate.*

### Step 3.1 — Inferenza fuori dall'event loop + concorrenza (A1)

**Il cambiamento architetturale più importante del refactor.**

**Attività:**
- [ ] Incapsulare l'inferenza in un executor dedicato: `ThreadPoolExecutor(max_workers=1)` per il modello (una GPU = una trascrizione alla volta, le richieste si accodano) e chiamate via `await loop.run_in_executor(...)` / `asyncio.to_thread`.
  - Nota: `WhisperModel.transcribe` di faster-whisper ritorna un generatore lazy — **consumarlo interamente dentro l'executor**, non nell'event loop.
- [ ] Stesso trattamento per `librosa.load` e per qualunque chiamata CPU-bound residua.
- [ ] Abilitare `Application.builder().concurrent_updates(True)` così i comandi (`/start`, `/help`, `/lang`) rispondono anche durante una trascrizione.
- [ ] Feedback all'utente quando la richiesta è in coda: reaction o messaggio "🎧 in coda…" + `chat_action` "typing" durante l'elaborazione.

**Criteri di accettazione:** mentre gira una trascrizione lunga, `/start` da un secondo account risponde immediatamente; due vocali inviati insieme vengono processati in sequenza senza errori né mescolamenti di risposta.

### Step 3.2 — Ridisegno dello streaming dei messaggi (A9)

**Obiettivo: da O(n²) chiamate API a un numero costante e prevedibile.**

**Attività:**
- [ ] Accumulare i segmenti man mano che il generatore li produce e aggiornare il messaggio Telegram **a intervalli** (es. edit al massimo ogni 3-5 secondi, o ogni +500 caratteri), non a ogni segmento.
- [ ] Isolare la logica di split/edit/send in `transcription/streaming.py` con stato proprio (ultimo messaggio, testo già inviato) — oggi il handler mescola download, trascrizione, split e invio.
- [ ] Riusare `send_or_edit_with_retry` (2.5).
- [ ] Edit finale a fine trascrizione per garantire il testo completo.

**Criteri di accettazione:** un audio da 10 minuti genera un numero di chiamate API lineare e limitato (verificabile dai log); niente flood control nei casi d'uso normali; il testo finale in chat è identico all'output del modello.

### Step 3.3 — Limiti d'uso e messaggi d'errore (S2, S5)

**Attività:**
- [ ] Controllo `duration > settings.max_media_duration_s` **prima** di scaricare il file → risposta cortese con il limite.
- [ ] Opzionale: `allowed_chat_ids` in Settings (vuoto = bot pubblico) per chi self-hosta con GPU propria.
- [ ] Handler di errore globale (`application.add_error_handler`): all'utente un messaggio generico ("Qualcosa è andato storto, riprova"), nei log l'eccezione completa; eliminare tutti i `reply_text(str(e))`. L'aggancio alle notifiche admin arriva nello step 3.4.

**Criteri di accettazione:** un video oltre il limite viene rifiutato senza download; un'eccezione forzata produce messaggio generico all'utente + stack trace nei log.

### Step 3.4 — Modulo admin per l'owner (S4)

*Dipende da 3.3 (error handler globale) e 2.1 (storage coerente). Completa la feature abbozzata in `admin_feature.py`, che qui viene sostituito definitivamente.*

**Obiettivo:** l'owner del servizio ha notifiche e strumenti di gestione direttamente in chat, implementati con il bot PTB già istanziato (niente URL costruiti a mano, niente `requests` sincrono).

**Attività:**
- [ ] Creare `handlers/admin.py` + un piccolo servizio di notifica (`admin/notifier.py` o funzione in `handlers/admin.py`) che usa `bot.send_message(settings.admin_chat_id, ...)`.
- [ ] **Notifiche errori**: l'error handler globale di 3.3 inoltra all'admin un riassunto dell'eccezione (tipo, handler coinvolto, chat anonimizzata) se `settings.admin_chat_id` è impostato.
- [ ] **Eventi d'uso**: notifica quando un nuovo utente o gruppo usa il bot per la prima volta (hook nel punto in cui lo storage fa l'upsert con `$setOnInsert`, step 2.1).
- [ ] **Comandi `/admin`** riservati all'owner (protetti con `filters.User(user_id=settings.admin_chat_id)` — i non autorizzati vengono ignorati, senza risposta):
  - [ ] `/admin stats`: statistiche globali dal DB — utenti totali, gruppi totali, trascrizioni effettuate, minuti di parlato processati;
  - [ ] `/admin status`: uptime, device/modello in uso, dimensione coda di trascrizione.
- [ ] **Broadcast**: `/admin broadcast <messaggio>` invia a tutti gli utenti e gruppi registrati, con:
  - [ ] conferma esplicita prima dell'invio (mostra anteprima + numero destinatari);
  - [ ] throttling per rispettare i limiti dell'API Bot (~30 msg/s complessivi): invio sequenziale con pausa;
  - [ ] gestione dei destinatari che hanno bloccato il bot (`Forbidden` → log, si continua) e report finale (inviati/falliti).
- [ ] Rimuovere `admin_feature.py` (il segnaposto lasciato in 1.3), incluse `TOKEN_PATH`/`TOKEN_CHAT_ID_PATH`; togliere `requests` dalle dipendenze se non serve altrove.

**Criteri di accettazione:** un'eccezione forzata arriva come notifica in chat all'owner; il primo uso da un nuovo account genera la notifica "nuovo utente"; `/admin stats` risponde solo all'owner (da un altro account viene ignorato); un broadcast di prova raggiunge i destinatari con report finale; `admin_feature.py` non esiste più.

### Step 3.5 — Graceful shutdown

**Attività:**
- [ ] Verificare il comportamento su SIGTERM (docker compose down): la trascrizione in corso deve completarsi o interrompersi in modo pulito (chiusura executor con `shutdown(wait=...)`, chiusura client Mongo).

**Criteri di accettazione:** `docker compose down` durante una trascrizione non lascia processi zombie né messaggi Telegram appesi su "[...]".

---

## Fase 4 — Sicurezza, immagine, developer experience

*Obiettivo: deploy sicuro e leggero, log rispettosi della privacy, test e CI. Durata indicativa: 2-3 giornate. Gli step 4.1-4.4 sono ampiamente parallelizzabili.*

### Step 4.1 — Hardening Docker (S3, S6, D5)

**Attività:**
- [ ] Base image: multi-stage build — stage builder su `nvidia/cuda:*-cudnn*-devel` solo se serve compilare, runtime su **`nvidia/cuda:*-runtime`** (o `base`); aspettarsi svariati GB risparmiati.
- [ ] Utente non-root (`USER calliope`), `WORKDIR` coerente.
- [ ] `.dockerignore`: `.env`, `logs/`, `notebooks/`, `.git`, `*.md`, screenshot.
- [ ] `CMD ["calliope"]` nel Dockerfile (l'entry point esiste da 1.2): l'immagine diventa avviabile anche senza compose.
- [ ] `poetry install --only main` (già da 1.2) + cache mount per pip/poetry; valutare in alternativa l'export a `requirements.txt` nello stage builder per non avere poetry nel runtime.
- [ ] docker-compose: rimuovere il port mapping di Mongo verso l'host **oppure** abilitare auth (`MONGO_INITDB_ROOT_USERNAME/PASSWORD` + URI con credenziali); pinnare `mongo` a una release stabile (via `8.0.0-rc6`); healthcheck su Mongo e `depends_on: condition: service_healthy`.
- [ ] Allineare il `makefile`: `make run` (locale), `make up`/`make down` (compose), rimuovere il `docker-run` rotto o dargli `--env-file`.

**Criteri di accettazione:** immagine sensibilmente più piccola (misurare prima/dopo); `docker inspect` mostra utente non-root; da fuori la macchina Mongo non è raggiungibile (o richiede credenziali); `docker run --env-file .env --gpus all calliope` parte da solo.

### Step 4.2 — Logging: privacy e rotation (S1, §6)

**Attività:**
- [ ] Rimuovere il log della trascrizione completa (`logger.success` in stt): loggare solo user id/username, durata media, tempo di elaborazione, esito, lingua rilevata.
- [ ] Audit di tutti i punti di log per contenuti utente residui.
- [ ] Sink file (se mantenuto oltre a stdout): `rotation="1 day"`, `retention="14 days"`, `compression="zip"`.
- [ ] Livelli coerenti: `info` per il flusso normale, `warning` per degradi, `error` solo per errori veri.

**Criteri di accettazione:** `grep` sui log dopo una sessione di test non trova alcun testo di trascrizione; i log ruotano.

### Step 4.3 — Potatura e aggiornamento dipendenze (D2, D3)

*Prerequisiti: 2.3 (via torch) e 2.4 (via moviepy) già fatti.*

**Attività:**
- [ ] Rimuovere da `pyproject.toml`: `torch`, `torchvision`, `torchaudio`, `moviepy`, `pandas` (il nuovo `/stats` dello step 2.6 non la usa), `rich`, `requests` (il modulo admin dello step 3.4 usa il bot PTB), `pydantic` esplicito (arriva con pydantic-settings), `python-dotenv` (gestito da pydantic-settings), `llvmlite` esplicito (se era solo un vincolo per librosa, verificare).
- [ ] Valutare la sostituzione di `librosa` (usata solo per caricare audio) con `soundfile`/ffmpeg diretto a 16 kHz mono: faster-whisper accetta anche file/percorsi direttamente — potrebbe sparire pure lei.
- [ ] Aggiornare: `python-telegram-bot` all'ultima major (changelog alla mano: API `Application` sostanzialmente stabile da v20), `faster-whisper`, `pymongo`; rivedere i pin-workaround di `av`/`ctranslate2` con le versioni correnti.
- [ ] `poetry lock` + smoke test completo + misura dimensione immagine prima/dopo.

**Criteri di accettazione:** nessuna dipendenza dichiarata e non importata (verificabile con `deptry` o grep); immagine e tempo di build ridotti; smoke test verde.

### Step 4.4 — Test automatici (§6)

*Reso possibile dalle fasi 1-2 (dipendenze iniettate, moduli puri).*

**Attività:**
- [ ] `pytest` + `pytest-asyncio` nel gruppo dev; struttura `tests/` speculare al package.
- [ ] Unit test sui moduli puri (nessun mock pesante necessario):
  - [ ] `split_message`: bordi esatti a 4096, testo senza spazi, testo vuoto, unicode;
  - [ ] formattazione timestamp (`transcribe_with_timestamps` → estrarre la parte pura di bucketing/formatting e testarla: parole a cavallo del minuto, audio < 1 min, trascrizione vuota);
  - [ ] `detect_silence` con audio sintetico (numpy): tutto muto, tutto parlato, silenzio solo in coda/testa, ai bordi della soglia;
  - [ ] `format_timedelta` e la formattazione di `/stats` (dati singolo utente e classifica gruppo);
  - [ ] validazione codici lingua di `/lang`;
  - [ ] `Settings`: default, override da env, errore senza token.
- [ ] Test dello storage con `mongomock` (o testcontainers se si preferisce fedeltà): upsert idempotente, incrementi corretti per voice/video note, `get_language` sui casi limite, aggregazioni di `/stats` e `/admin stats`.
- [ ] Test degli handler con `Update`/`Context` finti (PTB fornisce oggetti costruibili a mano): happy path `/start`, `/help`, `/lang`, `/stats`, media oltre il limite di durata; un comando `/admin` da un utente non autorizzato viene ignorato senza risposta.
- [ ] Coverage minima concordata (suggerito: 70% sui moduli non-handler).

**Criteri di accettazione:** `pytest` verde in locale e senza GPU/Mongo/rete; i bug fixati in Fase 2 hanno ciascuno un test di regressione (C1, C2, C5, C7, C9).

### Step 4.5 — CI (§6)

**Attività:**
- [ ] Pipeline (GitHub Actions, essendo il repo su GitHub): job `lint` (ruff + mypy), job `test` (pytest), job `build` (docker build senza push) su ogni push/PR.
- [ ] Badge di stato nel README.
- [ ] Opzionale: job di publish immagine su tag (`ghcr.io`).

**Criteri di accettazione:** la pipeline gira ed è rossa se lint/test falliscono; branch `main` protetto dalla pipeline (se si lavora via PR).

### Step 4.6 — Documentazione finale (§6)

**Attività:**
- [ ] Riscrivere il README: fix typo, path screenshot con `/`, sezione Requirements aggiornata (CPU ora supportata — da 2.3), tabella variabili d'ambiente, sezione sviluppo (setup poetry, pre-commit, test), sezione limiti configurabili.
- [ ] Badge licenza corretto (oggi punta a un repo altrui).
- [ ] Aggiornare/chiudere questo documento e ANALISI_REFACTOR.md (spuntare le problematiche risolte).
- [ ] Tag `v1.0.0`.

**Criteri di accettazione:** una persona esterna riesce a self-hostare il bot seguendo solo il README, da zero.

---

## Riepilogo dipendenze tra step

```
Fase 0 ──► 1.1 ──► 1.2 ──► 1.3 ──► 1.4 ──► 1.5
                                            │
              ┌─────────────┬───────────────┤
              ▼             ▼               ▼
             2.1 ──► 2.2   2.3   2.4 ──► 2.5
              │             │     │
              ├──► 2.6      │     ├──► 2.7
              │             │     │
              └──────┬──────┴─────┘
                     ▼
                    3.1 ──► 3.2 ──► 3.3 ──► 3.4 ──► 3.5
                     │
        ┌───────┬────┴────┬─────────┐
        ▼       ▼         ▼         ▼
       4.1     4.2       4.3       4.4 ──► 4.5 ──► 4.6
```

Durata complessiva indicativa: **~12-15 giornate**.

## Tracciamento problematiche → step

| ID analisi | Step che lo risolve |
|---|---|
| C1 `/lang` no-op | 2.2 |
| C2 statistiche video note | 2.1 |
| C3 device hardcoded | 1.3 (import) + 2.3 |
| C4 `stats.py` rotto | 2.6 (riscrittura su Mongo) |
| C5 flood control | 2.5 + 3.2 |
| C6 connessione Mongo | 2.1 |
| C7 `get_language` fragile | 2.1 + 2.2 |
| C8 variabili non definite | 2.4 |
| C9 `type=bool` | 1.4 |
| C10 risorse non rilasciate | 2.4 + 2.2 |
| A1 blocking async | 3.1 |
| A2 side effects import time | 1.5 |
| A3 singleton globali | 1.5 |
| A4 duplicazione | 2.1 + 2.4 |
| A5 struttura package | 1.2 |
| A6 config frammentata | 1.4 |
| A7 ConfigsLoader | 1.4 |
| A8 modello dati Mongo | 2.1 |
| A9 streaming O(n²) | 3.2 |
| S1 trascrizioni nei log | 0.2 + 4.2 |
| S2 leak errori all'utente | 3.3 |
| S3 Mongo esposto | 4.1 |
| S4 admin_feature | 3.4 (modulo admin completo) |
| S5 nessun limite d'uso | 3.3 |
| S6 container root/devel | 4.1 |
| D1 poetry.lock | 1.1 |
| D2 dipendenze inutili | 4.3 |
| D3 versioni vecchie | 4.3 |
| D4 package non installato | 1.2 |
| D5 Dockerfile/makefile | 4.1 |
| §5a feature incompiute | 2.6 (`/stats`) + 2.7 (silence detection) + 3.4 (admin) + 2.2 (`get_language`) |
| §5b codice morto | 1.3 |
| §6 test/lint/CI/docs | 1.3 + 4.4 + 4.5 + 4.6 |
