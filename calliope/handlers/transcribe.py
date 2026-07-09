import asyncio
import time

from loguru import logger
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from calliope.media.extract import MediaTooLongError, download_audio
from calliope.media.silence import detect_silence
from calliope.notifier import notify_registration
from calliope.settings import settings
from calliope.transcription.streaming import TranscriptionStreamer


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    # Download + estrazione audio (voice/video_note via ffmpeg). Il limite di
    # durata è verificato PRIMA del download: media troppo lunghi sono rifiutati
    # senza scaricare nulla.
    start_time = time.time()
    try:
        audio_data = await download_audio(
            context.bot, message, max_duration_s=settings.max_media_duration_s
        )
    except MediaTooLongError as e:
        await message.reply_text(
            f"⏱ This message is too long ({e.duration}s). The limit is {e.limit}s."
        )
        return
    except BadRequest:
        logger.warning(f"Could not download media from chat {message.chat_id}")
        await message.reply_text("Couldn't download this message (is it too large?).")
        return
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

    # Streaming a intervalli: il placeholder compare subito, poi il messaggio
    # viene aggiornato man mano (non a ogni segmento) → chiamate API lineari.
    # Gli errori imprevisti dell'inferenza propagano all'error handler globale
    # (messaggio generico all'utente + notifica all'owner).
    start_time = time.time()
    language = storage.get_language(update) or settings.default_language
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    streamer = TranscriptionStreamer(message)
    await streamer.start()
    async for text in transcriber.stream_segments(
        audio_data.samples, language=language
    ):
        await streamer.add(text)
    await streamer.finish()

    # Log di solo metadati (nessun testo di trascrizione): utente, durata audio,
    # caratteri prodotti, tempo di elaborazione, lingua richiesta.
    logger.success(
        f"{update.message.from_user.username}: transcribed {duration}s audio "
        f"({len(streamer.text)} chars) in {round(time.time() - start_time, 2)}s "
        f"[lang={language or 'auto'}]"
    )
