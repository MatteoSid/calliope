import asyncio
import time
from datetime import timedelta

from loguru import logger
from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from calliope.media.extract import download_audio
from calliope.media.silence import detect_silence
from calliope.notifier import notify_error, notify_registration
from calliope.settings import settings
from calliope.transcription.formatting import split_message


async def _send_or_edit_with_retry(operation, *, max_attempts: int = 5):
    """Esegue un invio/modifica Telegram ritentando la STESSA operazione sul
    flood control (``RetryAfter``), rispettando l'attesa richiesta dall'API e
    senza bloccare l'event loop (``asyncio.sleep``).

    ``operation`` è una callable senza argomenti che restituisce una nuova
    coroutine a ogni tentativo (una coroutine non può essere ri-attesa).
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except RetryAfter as e:
            logger.warning(
                f"Flood control, waiting {e.retry_after}s "
                f"(attempt {attempt}/{max_attempts})"
            )
            delay = (
                e.retry_after.total_seconds()
                if isinstance(e.retry_after, timedelta)
                else float(e.retry_after)
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Flood control: giving up after {max_attempts} attempts")


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    storage = context.bot_data["storage"]
    transcriber = context.bot_data["transcriber"]

    message = update.effective_message
    if message is None:
        return

    # Download + estrazione audio unificati (voice/video_note via ffmpeg): un
    # solo percorso, nessun leak di risorse, audio già mono 16 kHz.
    start_time = time.time()
    audio_data = await download_audio(context.bot, message)
    duration = audio_data.duration
    logger.info(f"Audio loaded in {time.time() - start_time:.2f} seconds")

    # Pre-filtro: audio senza parlato → reaction 🔇, nessuna trascrizione né
    # aggiornamento delle statistiche.
    if detect_silence(audio_data.samples, audio_data.sample_rate):
        logger.info(
            f"{update.message.from_user.username}: silent audio, skipping transcription"
        )
        await update.message.set_reaction("🔇")
        return

    # Solo l'uso reale (audio con parlato) viene conteggiato nelle statistiche.
    registration = storage.update(update, duration)
    if registration:
        await notify_registration(context.bot, registration, update)

    try:
        start_time = time.time()
        language = storage.get_language(update) or settings.default_language
        segments = transcriber.transcribe(audio_data.samples, language=language)
        full_transcription = ""

        current_message = await update.message.reply_text(
            text="[...]",
            disable_notification=True,
        )
        for segment in segments:
            full_transcription += segment.text
            message_parts = split_message(
                full_transcription, 4096 - 6
            )  # -6 per "[...]"

            for i, part in enumerate(message_parts):
                if i < len(message_parts) - 1:
                    part += " [...]"

                # Su flood control la STESSA parte viene ritentata (niente più
                # perdita di testo) e l'attesa non blocca l'event loop.
                if i == 0:
                    await _send_or_edit_with_retry(
                        lambda part=part, cm=current_message: (
                            context.bot.edit_message_text(
                                text=part,
                                chat_id=cm.chat_id,
                                message_id=cm.message_id,
                            )
                        )
                    )
                else:
                    current_message = await _send_or_edit_with_retry(
                        lambda part=part, cm=current_message: context.bot.send_message(
                            chat_id=cm.chat_id,
                            text=part,
                            disable_notification=True,
                        )
                    )

            full_transcription = message_parts[
                -1
            ]  # Mantieni l'ultima parte per il prossimo ciclo

        logger.success(
            f"{update.message.from_user.username}: {full_transcription} - in {round(time.time() - start_time, 2)}s"
        )

    except Exception as e:
        logger.exception(e)
        await notify_error(context.bot, update, e)
        await update.message.reply_text("Something went wrong, please try again.")
