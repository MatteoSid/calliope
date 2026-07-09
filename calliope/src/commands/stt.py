import asyncio
import os
import tempfile
import time

import librosa
from loguru import logger
from moviepy import VideoFileClip
from telegram import Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from calliope.settings import settings
from calliope.src.models.inference_model import WhisperInferenceModel
from calliope.src.utils.admin import notify_error, notify_registration
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import detect_silence, message_type, split_message

calliope_db = calliope_db_init()

whisper = WhisperInferenceModel()


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
            await asyncio.sleep(e.retry_after)
    raise RuntimeError(f"Flood control: giving up after {max_attempts} attempts")


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    # get audio from message
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(temp_dir)

        start_time = time.time()
        if message_type(update) == VideoNote:
            file_id = update.message.video_note.file_id
            duration = update.message.video_note.duration
            new_file = await context.bot.get_file(file_id)
            file_video_path = os.path.join(temp_dir, "temp_video.mp4")
            await new_file.download_to_drive(file_video_path)
            video = VideoFileClip(file_video_path)
            audio = video.audio

            file_audio_path = os.path.join(temp_dir, "temp_audio.ogg")
            audio.write_audiofile(file_audio_path, logger=None)

            audio, sr = librosa.load(file_audio_path)
        elif message_type(update) == Voice:
            file_id = update.message.voice.file_id
            duration = update.message.voice.duration
            new_file = await context.bot.get_file(file_id)

            file_path = os.path.join(temp_dir, "temp_audio.ogg")
            await new_file.download_to_drive(file_path)
            audio, sr = librosa.load(file_path)

        logger.info("Audio loaded in {:.2f} seconds".format(time.time() - start_time))

    # Pre-filtro: audio senza parlato → reaction 🔇, nessuna trascrizione né
    # aggiornamento delle statistiche.
    if detect_silence(audio, sr):
        logger.info(
            f"{update.message.from_user.username}: silent audio, skipping transcription"
        )
        await update.message.set_reaction("🔇")
        return

    # Solo l'uso reale (audio con parlato) viene conteggiato nelle statistiche.
    registration = calliope_db.update(update, duration)
    if registration:
        await notify_registration(context.bot, registration, update)

    try:
        start_time = time.time()
        language = calliope_db.get_language(update) or settings.default_language
        segments = whisper.transcribe(audio, language=language)
        full_transcription = ""

        current_message = await update.message.reply_text(
            text="[...]",
            disable_notification=True,
        )
        for x, segment in enumerate(segments):
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
                        lambda part=part: context.bot.edit_message_text(
                            text=part,
                            chat_id=current_message.chat_id,
                            message_id=current_message.message_id,
                        )
                    )
                else:
                    current_message = await _send_or_edit_with_retry(
                        lambda part=part: context.bot.send_message(
                            chat_id=current_message.chat_id,
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
