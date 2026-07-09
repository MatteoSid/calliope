import io

import telegram
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from calliope.media.extract import download_audio
from calliope.media.silence import detect_silence
from calliope.settings import settings


async def timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    storage = context.bot_data["storage"]
    transcriber = context.bot_data["transcriber"]

    message = update.effective_message
    if message is None:
        return

    # Download + estrazione audio unificati (video via ffmpeg): niente moviepy,
    # nessun file intermedio, audio già mono 16 kHz.
    try:
        audio_data = await download_audio(context.bot, message)
    except telegram.error.BadRequest as e:
        logger.error(str(e))
        await update.message.reply_text(str(e))
        return

    # Pre-filtro: video senza parlato → reaction 🔇, nessuna trascrizione.
    if detect_silence(audio_data.samples, audio_data.sample_rate):
        logger.info(
            f"{update.message.from_user.username}: silent video, skipping transcription"
        )
        await update.message.set_reaction("🔇")
        return

    # Trascrizione con timestamp direttamente dall'array audio.
    language = storage.get_language(update) or settings.default_language
    result_str = transcriber.transcribe_with_timestamps(
        audio_data.samples, language=language
    )

    # Inviamo il risultato come file .txt costruito in memoria (nessun file
    # temporaneo su disco).
    document = io.BytesIO(result_str.encode("utf-8"))
    document.name = "trascrizione.txt"
    await update.message.reply_document(document=document, filename="trascrizione.txt")
    logger.success("Trascrizione completata")
