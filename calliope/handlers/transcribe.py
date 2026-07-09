import asyncio
import time

from loguru import logger
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from calliope.media.extract import download_audio
from calliope.media.silence import detect_silence
from calliope.notifier import notify_error, notify_registration
from calliope.settings import settings
from calliope.transcription.streaming import TranscriptionStreamer


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
    # aggiornamento delle statistiche. Il check è CPU-bound: fuori dall'event loop.
    is_silent = await asyncio.to_thread(
        detect_silence, audio_data.samples, audio_data.sample_rate
    )
    if is_silent:
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

        # Streaming a intervalli: il placeholder compare subito, poi il messaggio
        # viene aggiornato man mano (non a ogni segmento) → chiamate API lineari
        # e prevedibili, niente flood control nei casi d'uso normali.
        await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
        streamer = TranscriptionStreamer(message)
        await streamer.start()
        async for text in transcriber.stream_segments(
            audio_data.samples, language=language
        ):
            await streamer.add(text)
        await streamer.finish()

        logger.success(
            f"{update.message.from_user.username}: "
            f"{len(streamer.text)} chars in {round(time.time() - start_time, 2)}s"
        )

    except Exception as e:
        logger.exception(e)
        await notify_error(context.bot, update, e)
        await update.message.reply_text("Something went wrong, please try again.")
