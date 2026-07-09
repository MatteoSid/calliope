import asyncio
import io

from loguru import logger
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from calliope.media.extract import MediaTooLongError, download_audio
from calliope.media.silence import detect_silence
from calliope.settings import settings


async def timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    storage = context.bot_data["storage"]
    transcriber = context.bot_data["transcriber"]

    message = update.effective_message
    if message is None:
        return

    # Allowlist: se configurata, solo le chat abilitate possono usare il bot.
    if not settings.chat_allowed(message.chat_id):
        logger.info(f"Chat {message.chat_id} not in allowlist, ignoring")
        await message.reply_text("🔒 This Calliope instance is private.")
        return

    # Download + estrazione audio (video via ffmpeg). Limite di durata verificato
    # prima del download; niente str(e) esposto all'utente.
    try:
        audio_data = await download_audio(
            context.bot, message, max_duration_s=settings.max_media_duration_s
        )
    except MediaTooLongError as e:
        await message.reply_text(
            f"⏱ This video is too long ({e.duration}s). The limit is {e.limit}s."
        )
        return
    except BadRequest:
        logger.warning(f"Could not download video from chat {message.chat_id}")
        await message.reply_text("Couldn't download this video (is it too large?).")
        return

    # Pre-filtro: video senza parlato → reaction 🔇, nessuna trascrizione.
    # Il check è CPU-bound: fuori dall'event loop.
    is_silent = await asyncio.to_thread(
        detect_silence, audio_data.samples, audio_data.sample_rate
    )
    if is_silent:
        logger.info(
            f"{update.message.from_user.username}: silent video, skipping transcription"
        )
        await update.message.set_reaction("🔇")
        return

    # Trascrizione con timestamp direttamente dall'array audio (fuori dall'event
    # loop). Azione "typing" come feedback durante l'elaborazione.
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    language = storage.get_language(update) or settings.default_language
    result_str = await transcriber.transcribe_with_timestamps(
        audio_data.samples, language=language
    )

    # Inviamo il risultato come file .txt costruito in memoria (nessun file
    # temporaneo su disco).
    document = io.BytesIO(result_str.encode("utf-8"))
    document.name = "trascrizione.txt"
    await update.message.reply_document(document=document, filename="trascrizione.txt")
    logger.success("Trascrizione completata")
