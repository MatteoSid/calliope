# Calliope — Analisi dei punti deboli in ottica refactor

> Documento di analisi del progetto allo stato attuale (branch `main`, luglio 2026).
> Obiettivo: censire tutte le problematiche per pianificare un refactor che mantenga le funzionalità esistenti migliorando qualità, robustezza e manutenibilità del codice.

## Funzionalità da preservare

Prima di elencare i problemi, questo è il perimetro funzionale da non perdere nel refactor:

- `/start`, `/help` — messaggi informativi
- `/lang <codice>` — cambio lingua di trascrizione (⚠️ oggi è di fatto rotto, vedi C1)
- Messaggi vocali e video note → trascrizione in chat, con streaming progressivo e split oltre i 4096 caratteri
- Video → trascrizione con timestamp per minuto, inviata come file `.txt`
- Statistiche d'uso utenti/gruppi su MongoDB
- Deploy via Docker Compose con supporto GPU (CUDA) + MongoDB

E queste sono le **feature incompiute da completare** (codice già presente ma non funzionante o non integrato — da NON rimuovere durante il refactor):

- `/stats` — utenti e gruppi devono poter vedere le proprie statistiche d'uso (oggi `stats.py` è rotto e scollegato, vedi C4)
- **Toolkit admin** per l'owner del servizio (oggi `admin_feature.py`, vedi S4): notifiche errori, eventi d'uso (nuovi utenti/gruppi), comandi `/admin` riservati, broadcast agli utenti
- **Silence detection** (oggi `detect_silence`, mai integrata): non trascrivere audio in cui nessuno parla; su audio muto il bot mette una reaction 🔇 senza inviare messaggi

---

## 1. Bug e problemi di correttezza (Critici)

### C1 — La feature `/lang` è un no-op
`change_language` salva la lingua su MongoDB, ma **nessuno la legge mai**: `MongoWriter.get_language` non è chiamato da nessuna parte, e `WhisperInferenceModel.transcribe` (`inference_model.py:37`) invoca il modello senza parametro `language`. L'attributo `self.language = "it"` (`inference_model.py:35`) non è mai usato. Risultato: la lingua è sempre auto-rilevata da Whisper e il comando `/lang` mente all'utente confermando un'impostazione che non ha effetto.

### C2 — Statistiche rotte per i video note
`MongoWriter.update_single_user` e `update_group` incrementano `total_speech_time` con `update.message.voice.duration` (`MongoClient.py:73,123,162`). Per i video note `message.voice` è `None` → `AttributeError`, inghiottita dal `try/except` generico di `update()` che logga "Error updating user". Le statistiche non vengono mai aggiornate per i video note, silenziosamente.

### C3 — Device hardcoded a `"cuda"` nonostante la detection
`inference_model.py:10-15` rileva CUDA e sceglie `device = "cpu"` come fallback, ma poi `_initialize()` ignora tutto e hardcoda `self.device = "cuda"` (`inference_model.py:33`). Su una macchina senza GPU il bot crasha all'avvio malgrado la detection esista. In più a riga 2 c'è `from venv import logger`: un import errato (probabilmente auto-import dell'IDE) subito sovrascritto da loguru.

### C4 — `stats.py` non può funzionare
`calliope/src/commands/stats.py` usa `json`, `timedelta`, `pd` e `format_timedelta` senza importarli (`format_timedelta` è commentata in `utils.py:32`). L'handler è commentato in `calliope.py:40`, quindi se riattivato oggi esploderebbe con `NameError`. Legge inoltre da un file `stast.json` (typo incluso) invece che da MongoDB, dove le statistiche vengono realmente scritte. È una **feature incompiuta, non codice morto**: `/stats` deve permettere a utenti e gruppi di vedere quanto usano Calliope, quindi va riscritta da zero leggendo da Mongo.

### C5 — Flood control: testo perso e event loop bloccato
In `stt.py:89-96`, quando Telegram risponde `RetryAfter`:
- si usa `time.sleep(e.retry_after)` che **blocca l'intero event loop asyncio** (tutto il bot si ferma, per tutti gli utenti);
- dopo lo sleep la parte di messaggio fallita **non viene reinviata**: si passa alla successiva e quel pezzo di trascrizione va perso.

### C6 — Gestione connessione MongoDB fragile e incoerente
`MongoClient.py:21-41`:
- `except:` nudo (cattura anche `KeyboardInterrupt`/`SystemExit`);
- se la connessione fallisce, `self.client = None` ma `users_collection`/`groups_collection` non esistono → ogni metodo successivo solleva `AttributeError`, inghiottita dai vari `except` generici: il bot "funziona" ma non salva nulla, senza che ce ne si accorga;
- incoerenza: il modulo calcola `mongo_uri` con fallback su `settings` (riga 10-12) ma il client usa direttamente `os.environ.get("MONGO_URI")` (riga 23) senza fallback — il log "Connected to MongoDB at {mongo_uri}" può indicare un URI diverso da quello realmente usato.

### C7 — `get_language` esplode nei casi limite
`MongoClient.py:168-179`: se l'utente/gruppo non è nel DB, `find_one` ritorna `None` → `TypeError` su `None["language_code"]`; se il chat type non è tra quelli previsti (es. canale) → `UnboundLocalError`. (Oggi non si manifesta solo perché il metodo non è mai chiamato, vedi C1.)

### C8 — Variabili potenzialmente non definite in `stt`
In `stt.py:33-53`, se `message_type(update)` non è né `VideoNote` né `Voice`, le variabili `audio` e `duration` non vengono mai assegnate → `NameError` alla riga 59. Oggi i filtri in `calliope.py` lo impediscono, ma la funzione è fragile per costruzione (nessun ramo `else`, nessuna validazione).

### C9 — `argparse` con `type=bool` è un bug classico
`arg_parser.py:7`: `type=bool` fa sì che **qualunque stringa non vuota sia `True`**: `-v False` attiva il verbose. Il `docker-compose.yml` passa `-v True` e funziona per caso. Va usato `action="store_true"`.

### C10 — Risorse non rilasciate
- `VideoFileClip` mai chiuso (`stt.py:39`, `timestamp.py:29`) → leak di file handle e processi ffmpeg residui;
- `open(transcript_path, "rb")` passato a `reply_document` senza context manager (`timestamp.py:48`);
- in `change_language`, l'`except Exception` generico (`change_language.py:27`) tratta qualsiasi errore (incluso Mongo giù) come "l'utente non ha specificato la lingua".

---

## 2. Problemi architetturali

### A1 — Codice bloccante dentro handler async (il problema più impattante)
Gli handler sono `async`, ma dentro eseguono operazioni sincrone pesanti: `whisper.transcribe` (GPU/CPU-bound, anche minuti), `librosa.load`, l'estrazione audio con moviepy, `time.sleep`. Con python-telegram-bot v20 (che di default processa gli update in sequenza e senza `concurrent_updates`), **il bot è mono-utente di fatto**: mentre trascrive un audio non risponde nemmeno a `/start` di un altro utente. Il refactor deve spostare il lavoro pesante fuori dall'event loop (es. `asyncio.to_thread`/executor dedicato, coda di lavoro, o processo separato per l'inferenza).

### A2 — Side effects a import time ovunque
- `calliope.py:8` chiama `title()` (che fa `os.system("clear && figlet ...")`!) **in mezzo agli import**, forzando import fuori ordine (violazione E402) e richiedendo `figlet` installato;
- `arg_parser.py` esegue `parser.parse_args()` a import time → qualunque import del package legge `sys.argv` (rende impossibile testare o riusare i moduli);
- `MongoWriter` viene istanziato a import time in `stt.py`, `start.py`, `change_language.py` (mitigato dal `lru_cache`, ma resta un singleton implicito sparso);
- il modello Whisper viene caricato a import time in `stt.py:20` e `timestamp.py:13`.

Nessuna di queste inizializzazioni è iniettata o controllabile: il grafo degli import È il bootstrap dell'applicazione.

### A3 — Nessuna dependency injection, tutto singleton globale
`calliope_db_init()` con `lru_cache` e il singleton thread-safe di `WhisperInferenceModel` sono due pattern diversi per lo stesso problema. Gli handler dovrebbero ricevere le dipendenze (DB, modello, settings) — PTB offre `context.bot_data` proprio per questo. Lo stato attuale rende il codice non testabile senza un MongoDB e una GPU reali.

### A4 — Duplicazione di logica
- L'estrazione audio da video (download → `VideoFileClip` → `write_audiofile` → `librosa.load`) è duplicata tra `stt.py:33-45` e `timestamp.py:22-35`;
- `datetime.now().strftime("%Y-%m-%d %H:%M:%S")` ripetuto 8 volte in `MongoClient.py`;
- la logica di update utente/gruppo in `update_group` duplica in gran parte `update_single_user`;
- i due blocchi `if/elif` su `chat.type` sono ripetuti in 4 metodi diversi.

### A5 — Struttura del package incoerente
- `calliope/src/...`: una directory `src` **dentro** il package è un anti-pattern (o si usa `src-layout` con `src/calliope/`, o si tolgono livelli);
- **nessun `__init__.py`** in tutto il progetto (funziona solo come namespace package implicito, da cui l'hack `PYTHONPATH=.` nel compose e nel makefile);
- `MongoClient.py` in PascalCase (i moduli Python vanno in `snake_case`); il nome ombreggia concettualmente `pymongo.MongoClient`;
- `utils.py` è un cestino: contiene split dei messaggi, la silence detection mai integrata (§5a), type-detection dei messaggi e il banner figlet;
- `commands/` mescola veri comandi (`/start`, `/help`) e handler di messaggi (`stt`, `timestamp`).

### A6 — Configurazione frammentata su tre sistemi non integrati
1. `configs.yaml` — con chiavi morte (`port: 3100`, `base_url`, blocco `rabbitmq` commentato) e valori Mongo (`host`, `port: 27018`) di fatto ignorati a runtime;
2. variabili d'ambiente (`TELEGRAM_TOKEN`, `MONGO_URI`, `ADMIN_CHAT_ID`) — senza validazione: se `TELEGRAM_TOKEN` manca si ottiene un errore criptico da PTB (`calliope.py:30`); `ADMIN_CHAT_ID` non è nemmeno in `.env.example`;
3. flag CLI (`-v`).

`python-dotenv` è dichiarato tra le dipendenze **ma mai usato**: in locale il `.env` non viene caricato (funziona solo via docker-compose `env_file`). `pydantic` è già una dipendenza: la soluzione naturale è `pydantic-settings` con un unico oggetto Settings validato.

### A7 — `ConfigsLoader` fragile
`configs_manager.py`: path relativo `"calliope/src/config/configs.yaml"` risolto rispetto alla CWD (altro motivo dell'hack `PYTHONPATH=.`/esecuzione obbligata dalla root); la docstring promette una ricerca in una cartella "conf" mai implementata; `path=None` (default dichiarato) → `TypeError` su `open(None)`; `ConfigsNotFoundError` definita e mai usata; eredita da `dict` invece di essere un oggetto tipizzato.

### A8 — Modello dati MongoDB debole
- Date salvate come **stringhe formattate** invece che `datetime` (niente query/sort temporali sensate); `datetime.now()` senza timezone;
- pattern `find_one` + `insert_one`/`update_one` non atomico (race condition con update concorrenti; nessun indice unico su `user_id`/`group_id`) — si risolve con `update_one(..., upsert=True)`;
- `str(str(update.message.chat.id))` doppia conversione (`MongoClient.py:95`);
- parametro `time_used=0` di `update_single_user` mai usato;
- in `update_group`, per un gruppo nuovo si fa `insert_one` con `times_used: 0` seguito immediatamente da un secondo `update_one` con `$inc` — due round-trip dove ne basterebbe uno.

### A9 — Streaming della trascrizione O(n²) e API-intensive
Il loop in `stt.py:66-100` ri-splitta e ri-edita l'intera trascrizione **a ogni segmento** Whisper: numero di chiamate API quadratico rispetto alla lunghezza, che è la causa diretta del flood control che il codice poi "gestisce" con il workaround di C5. Nel refactor: aggiornare il messaggio a intervalli (es. ogni N secondi o M caratteri), oppure inviare la trascrizione a fine elaborazione.

---

## 3. Sicurezza e privacy

### S1 — Trascrizioni complete loggate su disco
`stt.py:102-104` logga con `logger.success` **l'intera trascrizione** insieme allo username. Il README vende Calliope proprio sulla privacy ("without having to give private information to anyone"): i log su file (`logs/`) contraddicono la promessa. Loggare solo metadati (durata, tempo di elaborazione, esito).

### S2 — Dettagli interni inviati agli utenti
`stt.py:108` e `timestamp.py:25` rispondono all'utente con `str(e)` dell'eccezione: leak di path, nomi di moduli e dettagli d'infrastruttura. Serve un messaggio di errore generico + log interno completo.

### S3 — MongoDB esposto senza autenticazione
`docker-compose.yml:23-24` pubblica Mongo sulla porta host `27018` senza alcuna auth. Chiunque raggiunga la macchina legge/scrive il DB. Rimuovere il port mapping (i container comunicano già sulla rete interna) o abilitare l'autenticazione. In più l'immagine è `mongo:8.0.0-rc6`, una **release candidate**.

### S4 — `admin_feature.py` problematico (e mai integrato)
- Token del bot e messaggio concatenati **a mano nell'URL** senza URL-encoding (`admin_feature.py:23-30`): un messaggio con `&`, spazi o `%` rompe o altera la richiesta;
- `requests.get` sincrono (bloccherebbe l'event loop se mai usato da un handler);
- `markdown_escape` con lista di caratteri incompleta e commentata a metà;
- `TOKEN_PATH`/`TOKEN_CHAT_ID_PATH` puntano a file `TOKEN.txt` che non esistono più (residuo di un vecchio sistema di config);
- di fatto **nessuno chiama `send_to_admin`**.

È l'embrione di una **feature voluta**: il toolkit dell'owner del servizio. Va riscritto come modulo admin di prima classe — notifiche errori, eventi d'uso (nuovi utenti/gruppi), comandi `/admin` riservati all'owner, broadcast — usando il bot PTB già istanziato (niente URL raw, niente `requests`).

### S5 — Nessun controllo di accesso o limite d'uso
Il bot accetta richieste da chiunque: niente whitelist/blacklist, niente rate limiting per utente, **nessun limite sulla durata** dei media. Un video di 2 ore monopolizza la GPU e (per A1) blocca il bot per tutti. Nel refactor: limite configurabile di durata/dimensione + eventuale lista di utenti/gruppi autorizzati.

### S6 — Container root e immagine sovradimensionata
Il Dockerfile usa `nvidia/cuda:...-cudnn8-devel` (immagine di sviluppo, svariati GB) invece della variante `runtime`, e il processo gira come **root**. Manca `.dockerignore` (il contesto di build include log, notebook, `.env`… — oggi il `COPY` è selettivo, ma basta un `COPY . .` futuro per copiare i segreti nell'immagine).

---

## 4. Dipendenze e packaging

### D1 — `poetry.lock` nel `.gitignore` ma richiesto dal Dockerfile
`.gitignore` esclude `poetry.lock`, ma `Dockerfile:21` fa `COPY pyproject.toml poetry.lock /app/`. Su un **clone fresco la build Docker fallisce** (file mancante) e senza lockfile versionato la riproducibilità delle build è persa. Il lockfile va committato (la nota nel `.gitignore` standard lo dice esplicitamente per le applicazioni).

### D2 — Dipendenze dichiarate e mai usate
Da verifica sugli import: `rich`, `pandas` (referenziata solo dal `stats.py` rotto, senza nemmeno l'import — la riscrittura di `/stats` non ne avrà bisogno, basta un sort), `pydantic`, `python-dotenv`, `torchvision` non sono mai importate. `torch` è importato **solo** per la detection CUDA che poi viene ignorata (C3) — `ctranslate2`/`faster-whisper` non richiedono torch: potenzialmente si eliminano ~4-5 GB di dipendenze.

### D3 — Versioni pinnate vecchie / incoerenti
`torch 2.0.0`, `torchvision 0.15.1`, `torchaudio 2.0.1` (inizio 2023) su base CUDA 12.1; `python-telegram-bot ^20.6` (v21+ da tempo disponibile con API migliorate); `moviepy ^1.0.3` usata solo per estrarre l'audio — un singolo comando `ffmpeg` (già nell'immagine) farebbe lo stesso senza la dipendenza. `av` e `ctranslate2` pinnati esatti con commenti-workaround che andranno rivisti.

### D4 — Il package non è installato come tale
`poetry install --no-root` + assenza di `__init__.py` + path relativi ⇒ il progetto funziona solo con `env PYTHONPATH=. python -m calliope` lanciato dalla root (vedi `makefile` e `docker-compose.yml:17`). Installando il package (`poetry install`) e definendo un entry point (`[tool.poetry.scripts] calliope = "calliope.main:main"`) l'hack sparisce. Inoltre `--no-root` senza `--only main` installa anche il gruppo dev (`ipykernel`, `memory-profiler`) nell'immagine di produzione.

### D5 — Dockerfile e makefile incompleti
- Il Dockerfile non ha `CMD`/`ENTRYPOINT`: l'immagine non è avviabile senza il compose;
- `make docker-run` lancia il container **senza** `--env-file` e senza Mongo → non può funzionare;
- Nessun `HEALTHCHECK`; `pip install --upgrade pip` e `poetry install` in layer separati non ottimizzati.

---

## 5. Codice morto, residui e feature incompiute

### 5a. Feature incompiute — da completare, NON eliminare

Codice oggi scollegato o rotto, ma che rappresenta funzionalità volute: il refactor lo deve portare a compimento.

| Elemento | Posizione | Stato e destino |
|---|---|---|
| `stats.py` intero | `commands/stats.py` | Rotto (C4): import mancanti, legge `stast.json` invece di Mongo. **Da riscrivere su Mongo**: statistiche d'uso per utenti e gruppi |
| `send_to_admin` / `markdown_escape` | `admin_feature.py` | Mai integrati e implementati male (S4). **Da riscrivere come modulo admin**: notifiche errori, eventi d'uso, comandi `/admin`, broadcast |
| `detect_silence` | `utils.py:52` | Mai integrata. **Da fixare e collegare** come pre-filtro: niente trascrizione se nessuno parla, reaction 🔇. Bug attuali: annotazione di ritorno errata (`int` vs tupla), rileva solo il silenzio in coda mentre serve sull'intero audio, il passo è di 1 s ma la docstring dice 0.5 s, soglia hardcoded |
| `get_language` | `MongoClient.py:168` | Mai chiamato (causa C1). **Da collegare** alla trascrizione per far funzionare `/lang` |
| `format_timedelta` | `utils.py:32-48` | Commentata. **Da reimplementare pulita**: servirà al nuovo `/stats` |

### 5b. Codice morto vero — da eliminare

| Elemento | Posizione | Note |
|---|---|---|
| `ConfigsNotFoundError` | `configs_manager.py:14` | Mai sollevata |
| `change_language` (modello) | `inference_model.py:41-46` | Commentato "coming soon"; superato dal passare `language` a `transcribe()` |
| Chiavi config morte | `configs.yaml` | `port`, `base_url`, blocco `rabbitmq` |
| Import inutilizzati | `utils.py` (`tempfile`, `timedelta`, `List`, `Update`), `stt.py` (`os` parzialm.) | Un linter li segnala tutti |
| `title()` + figlet | `utils.py:103` | `os.system("clear && figlet ...")`: dipendenza di sistema per un banner; da rimuovere o sostituire con `rich` (già dichiarata) |
| File spuri nella working dir | `temp_audio.wav`, `logs/*.log`, notebook `*.ipynb` | Non tracciati ma inquinano il progetto; i log contengono dati utente (S1) |
| TODO sparsi | 9+ occorrenze | Da triage: risolvere o eliminare |

---

## 6. Qualità del codice e tooling

- **Zero test.** Nessun framework configurato, e l'architettura attuale (A2/A3) rende comunque impossibile scrivere unit test. Il refactor deve portare almeno test su: `split_message`, formattazione timestamp, logica Mongo (con `mongomock` o fixture), parsing comando `/lang`.
- **Zero linting/formatting/type-checking**: nessun `ruff`/`black`/`mypy`/`pre-commit`. Molti dei problemi elencati (import inutilizzati, `except` nudi, E402, nomi non conformi) sarebbero stati intercettati da `ruff` con configurazione base.
- **Nessuna CI/CD**: niente pipeline che builda l'immagine, esegue lint e test.
- **Type hints incompleti o errati**: `detect_silence -> int` ma ritorna una tupla; `split_message -> list` non parametrizzato; la maggior parte delle funzioni Mongo senza tipi.
- **Lingua incoerente**: commenti, docstring e log mescolano italiano e inglese (perfino nella stessa funzione, es. `transcribe_with_timestamps`). Scegliere una lingua (consiglio: inglese nel codice) e uniformare.
- **Logging**: `logger.remove(0)` fragile (dipende dall'ordine di configurazione); un file di log per avvio senza `rotation`/`retention`/`compression` (loguru li supporta nativamente); livelli usati in modo incoerente (`logger.info` per errori utente, `logger.error` per condizioni normali come "Stats not found").
- **README**: typo ("mesage", "runnig"), path screenshot con backslash Windows (`screenshots\screenshot.PNG`, rotto su GitHub), nessuna sezione di sviluppo (setup locale, test, contributi), badge di licenza che punta a un repo altrui.

---

## 7. Priorità suggerite per il refactor

### Fase 1 — Fondamenta (prerequisito di tutto il resto)
1. Committare `poetry.lock` (D1) e sistemare il packaging: `__init__.py`, entry point, via l'hack `PYTHONPATH` (D4, A5).
2. Introdurre `ruff` + `mypy` + `pre-commit` e ripulire ciò che segnalano: **solo il codice realmente morto** (§5b), import, `except` nudi — le feature incompiute (§5a) si parcheggiano e si completano nelle fasi successive.
3. Unificare la configurazione in un unico `Settings` pydantic (env + .env), validato all'avvio, con errore chiaro se manca il token (A6, A7).
4. Eliminare i side effects a import time: bootstrap esplicito in `main()`, dipendenze in `context.bot_data` (A2, A3).

### Fase 2 — Correttezza e completamento feature
5. Fix dei bug: `/lang` collegato davvero alla trascrizione (C1, C7), statistiche video note (C2), device detection (C3), flood control con retry corretto (C5), chiusura risorse (C10), `MongoWriter` con upsert atomici, date `datetime` e gestione connessione onesta (C6, A8).
6. Estrarre un modulo unico di media processing (download → estrazione audio → load) condiviso da `stt` e `timestamp`, valutando ffmpeg diretto al posto di moviepy (A4, D3).
7. Riscrivere `/stats` su Mongo: statistiche per utenti e gruppi (C4).
8. Integrare la silence detection come pre-filtro: audio muto → reaction 🔇, niente inferenza (§5a).

### Fase 3 — Architettura e robustezza
9. Spostare l'inferenza fuori dall'event loop e abilitare la concorrenza degli update (A1).
10. Ridisegnare lo streaming dei messaggi con aggiornamenti a intervalli (A9).
11. Limiti d'uso: durata massima media, eventuale whitelist, messaggi d'errore user-friendly senza leak (S2, S5).
12. Modulo admin completo per l'owner: notifiche errori, eventi d'uso, comandi `/admin`, broadcast (S4).

### Fase 4 — Sicurezza, immagine, DX
13. Mongo non esposto / autenticato, immagine `runtime` non-root, `.dockerignore`, `CMD` nel Dockerfile (S3, S6, D5).
14. Log senza contenuti delle trascrizioni + rotation (S1).
15. Potatura dipendenze (torch/torchvision/pandas/rich o uso effettivo) e aggiornamento PTB/faster-whisper (D2, D3).
16. Test, CI, README aggiornato (§6).
