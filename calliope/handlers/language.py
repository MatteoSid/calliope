from faster_whisper.tokenizer import _LANGUAGE_CODES
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from calliope.storage.mongo import calliope_db_init

calliope_db = calliope_db_init()

# Codici lingua supportati da faster-whisper (ISO 639-1, es. "it", "en", "es").
SUPPORTED_LANGUAGES = set(_LANGUAGE_CODES)


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestisce il comando /lang per scegliere la lingua di trascrizione.

    - ``/lang`` senza argomenti mostra la lingua attualmente impostata.
    - ``/lang <codice>`` valida il codice contro le lingue supportate da
      faster-whisper e lo salva; alla trascrizione successiva la lingua viene
      forzata (vedi ``WhisperInferenceModel.transcribe``).
    - ``/lang auto`` ripristina l'auto-detect.
    """
    username = update.message.from_user.username or update.message.from_user.id
    args = context.args if context.args is not None else update.message.text.split()[1:]

    # /lang senza argomenti → mostra la lingua corrente
    if not args:
        current = calliope_db.get_language(update)
        if current:
            await update.message.reply_text(
                f"Current transcription language: {current}\n"
                "Use /lang <code> to change it (e.g. /lang en), "
                "or /lang auto to enable auto-detection.",
                disable_notification=True,
            )
        else:
            await update.message.reply_text(
                "Transcription language is set to auto-detect.\n"
                "Use /lang <code> to force a language (e.g. /lang es for Spanish).",
                disable_notification=True,
            )
        return

    requested = args[0].lower()

    # /lang auto → torna all'auto-detect (lingua salvata = None)
    if requested == "auto":
        language: str | None = None
        confirmation = "Transcription language set to auto-detect."
    elif requested in SUPPORTED_LANGUAGES:
        language = requested
        confirmation = f"Transcription language set to {requested}."
    else:
        logger.info(f"{username}: unsupported language code '{requested}'")
        await update.message.reply_text(
            f'Language "{requested}" is not supported.\n'
            "Use a two-letter ISO code, e.g. /lang en, /lang it, /lang es, "
            "or /lang auto for auto-detection.",
            disable_notification=True,
        )
        return

    # Persistenza: separa l'errore DB dagli altri casi.
    try:
        calliope_db.change_language(update=update, language=language)
    except Exception:
        await update.message.reply_text(
            "Could not save your language preference right now, please try again later.",
            disable_notification=True,
        )
        return

    logger.info(f"{username}: set transcription language to {language or 'auto'}")
    await update.message.reply_text(confirmation, disable_notification=True)
