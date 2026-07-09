from datetime import datetime

from loguru import logger
from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from calliope.handlers.admin import admin, broadcast_callback, error_handler
from calliope.handlers.help import help_command
from calliope.handlers.language import change_language
from calliope.handlers.start import start
from calliope.handlers.stats import stats
from calliope.handlers.timestamp import timestamp
from calliope.handlers.transcribe import stt
from calliope.logging_setup import setup_logging
from calliope.settings import settings
from calliope.storage.mongo import MongoStorage
from calliope.transcription.whisper import WhisperTranscriber

# Comandi mostrati nel menu di Telegram (impostati all'avvio via set_my_commands).
BOT_COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "How to use Calliope"),
    BotCommand("stats", "Show your usage statistics"),
    BotCommand("lang", "Set the transcription language"),
]


async def _post_init(application: Application) -> None:
    """Registra i comandi del bot e memorizza l'istante di avvio (uptime)."""
    application.bot_data["start_time"] = datetime.now()
    await application.bot.set_my_commands(BOT_COMMANDS)


async def _post_shutdown(application: Application) -> None:
    """Rilascio ordinato delle risorse allo spegnimento (SIGTERM/SIGINT).

    A questo punto PTB ha già atteso il completamento degli handler in corso
    (una trascrizione in coda viene portata a termine, nessun messaggio appeso
    su "[...]"): l'executor è quindi inattivo e si chiude subito.
    """
    logger.info("Shutting down: releasing resources")
    transcriber = application.bot_data.get("transcriber")
    if transcriber is not None:
        transcriber.shutdown()
    storage = application.bot_data.get("storage")
    if storage is not None:
        storage.close()


def main() -> None:
    """Bootstrap esplicito: logging → storage → modello → application.

    Tutte le risorse costose sono create qui (nessun side effect a import-time)
    e iniettate negli handler tramite ``application.bot_data``.
    """
    setup_logging(settings)
    logger.info("Starting Calliope")

    storage = MongoStorage(settings)
    transcriber = WhisperTranscriber(settings)

    application = (
        Application.builder()
        .token(settings.telegram_token.get_secret_value())
        .read_timeout(60)
        .write_timeout(60)
        # Gestisce gli update in modo concorrente: i comandi (/start, /help, ...)
        # rispondono anche mentre è in corso una trascrizione (che gira comunque
        # su un thread executor dedicato, fuori dall'event loop).
        .concurrent_updates(True)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    # Dependency injection: gli handler leggono queste chiavi da context.bot_data.
    application.bot_data["settings"] = settings
    application.bot_data["storage"] = storage
    application.bot_data["transcriber"] = transcriber

    logger.info("Application is running")

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("lang", change_language))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(
        CallbackQueryHandler(broadcast_callback, pattern="^broadcast:")
    )

    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, stt))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, stt))
    application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND, timestamp))

    # Handler globale degli errori (notifica l'owner, risposta generica all'utente)
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
