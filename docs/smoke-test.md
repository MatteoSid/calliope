# Calliope — Smoke test manuale

> Checklist di verifica manuale ripetibile. Non esistono ancora test automatici
> (arrivano nello step 4.4 della [ROADMAP](../ROADMAP.md)); questa checklist è la
> rete di sicurezza per non regredire durante il refactor.
>
> Eseguirla **a ogni step** che tocca il comportamento a runtime e annotare gli
> scostamenti. Distingue *comportamento da preservare* da *bug noti* già tracciati.

## Prerequisiti

- `.env` valorizzato (almeno `TELEGRAM_TOKEN`; opzionale `ADMIN_CHAT_ID`).
- GPU NVIDIA con driver compatibile **oppure** CPU (da 2.3 il bot gira anche su CPU).
- Un secondo account Telegram utile per i test di concorrenza (3.1) e broadcast (3.4).

## Avvio

```bash
docker compose up -d --build
docker compose logs -f calliope
```

Atteso nei log, in sequenza: `Using GPU`/`Using CPU` → `Connected to MongoDB` →
`Model loaded` → `Application is running`. Nessun traceback.

## Checklist funzionale

| # | Azione | Atteso | Preserva / Bug noto |
|---|--------|--------|---------------------|
| 1 | `/start` in privato | Messaggio di benvenuto; utente creato in `users_db` | preserva |
| 2 | `/help` | Testo di aiuto formattato (MarkdownV2), menziona `/lang` e `/stats` | preserva |
| 3 | Invio vocale breve (<1 min) | Trascrizione in chat; documento utente aggiornato (`times_used`, `total_speech_time`) | preserva |
| 4 | Invio vocale lungo (trascrizione > 4096 caratteri) | Messaggio splittato in più parti, testo completo senza perdite | preserva (fix flood control C5 in 2.5) |
| 5 | Invio **video note** | Trascrizione; statistiche aggiornate con la durata reale | ~~bug C2~~ risolto: la durata ora è esplicita |
| 6 | Invio **video** | File `.txt` con timestamp a intervalli di 1 minuto | preserva |
| 7 | Audio **muto** (vocale senza parlato) | Reaction 🔇, nessuna trascrizione, statistiche NON incrementate | preserva (silence detection 2.7) |
| 8 | `/lang es` + vocale in spagnolo | Trascrizione forzata in spagnolo | preserva (2.2) |
| 9 | `/lang` senza argomenti | Mostra la lingua corrente | preserva (2.2) |
| 10 | `/lang xx` (codice non valido) | Messaggio "lingua non supportata" | preserva (2.2) |
| 11 | `/lang auto` | Ripristina l'auto-detect | preserva (2.2) |
| 12 | `/stats` in privato | Statistiche personali reali dal DB | preserva (2.6) |
| 13 | `/stats` in un gruppo | Classifica dei membri per tempo di parlato | preserva (2.6) |
| 14 | Uso in un **gruppo** (aggiunta bot + vocale) | Trascrizione nel gruppo; documento in `groups_db` con `members_stats` | preserva |

## Comandi admin (solo se `ADMIN_CHAT_ID` è impostato)

| # | Azione | Atteso |
|---|--------|--------|
| A1 | `/admin` da un utente non-owner | Nessuna risposta (ignorato) |
| A2 | `/admin stats` dall'owner | Statistiche globali (utenti/gruppi/trascrizioni/minuti) |
| A3 | `/admin status` dall'owner | Uptime, modello, device |
| A4 | `/admin broadcast <msg>` | Anteprima + conferma inline; all'invio, report inviati/falliti |
| A5 | Primo uso da un nuovo utente/gruppo | Notifica "nuovo utente/gruppo" all'owner |
| A6 | Eccezione forzata in un handler | Messaggio generico all'utente + notifica all'owner + stack trace nei log |

## Verifica dati su MongoDB

```bash
docker exec mongodb_calliope mongosh --quiet calliope --eval 'printjson(db.users_db.findOne()); printjson(db.groups_db.findOne())'
```

Atteso: documenti con `user_id`/`group_id`, `times_used`, `total_speech_time`,
`first_use`/`last_use`, `language_code`.

## Bug noti ancora aperti (da fixare negli step indicati)

- Inferenza bloccante sull'event loop → i comandi non rispondono durante una
  trascrizione lunga (**3.1**).
- Streaming O(n²) delle edit → possibile flood control su audio molto lunghi (**3.2**).
- Nessun limite di durata sul media in ingresso (**3.3**).
- Trascrizione completa loggata (privacy) e log su file senza rotation (**4.2**).
- Container che gira come root, immagine non multi-stage (**4.1**).
