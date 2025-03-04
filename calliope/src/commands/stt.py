import json
import os
import tempfile
import time
from datetime import timedelta
from uuid import uuid4

import librosa
from loguru import logger
from moviepy.editor import VideoFileClip
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice
from telegram.error import RetryAfter
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from calliope.src.models.inference_model import WhisperInferenceModel
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import (
    extract_audio,
    mark_last,
    message_type,
    redis_connection,
    split_message,
)

redis_timeout = timedelta(minutes=60)

calliope_db = calliope_db_init()

whisper = WhisperInferenceModel()


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    calliope_db.update(update)

    audio, duration = await extract_audio(update, context)

    try:
        start_time = time.time()
        segments = whisper.transcribe(audio)

        # avviso l'utente che la trascrizione è in corso
        current_message = await update.message.reply_text(
            text="[...]",
            disable_notification=True,
        )

        # unisco le trascrizioni
        full_transcription = ""
        for segment in segments:
            full_transcription += segment.text

        # se la trascrizione è troppo lunga, la divido in modo da non superare 4096 caratteri
        message_parts = split_message(full_transcription, 4096 - 6)  # -6 per "[...]"

        # Definisco bottone e markup
        uuid = uuid4().hex
        redis_connection.setex(uuid, redis_timeout, full_transcription)

        keyboard = [
            [
                InlineKeyboardButton(
                    "Summarize", callback_data=json.dumps({"uuid": uuid})
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        for i, part in enumerate(message_parts):
            try:
                # Se non siamo all'ultimo pezzo, aggiungiamo un indicatore "[...]"
                # per indicare che il testo continua.
                if i < len(message_parts) - 1:
                    part += " [...]"

                # Se è il primo pezzo, modifichiamo il messaggio esistente.
                if i == 0:
                    # FIXME: se il testo viene splittato il bottone viene messo sul primo messaggio
                    await context.bot.edit_message_text(
                        text=part,
                        chat_id=current_message.chat_id,
                        message_id=current_message.message_id,
                        reply_markup=reply_markup,
                    )
                # Altrimenti, inviamo un nuovo messaggio con il pezzo successivo.
                else:
                    current_message = await context.bot.send_message(
                        chat_id=current_message.chat_id,
                        text=part,
                        disable_notification=True,
                    )

            except RetryAfter as e:
                # Workaraound for Flood Control
                # TODO: find a better solution
                logger.warning(
                    f"{update.message.from_user.username}: Flood control, sleeping for {e.retry_after}s"
                )
                logger.warning(f"message length: {duration}")
                time.sleep(e.retry_after)

        logger.success(
            f"{update.message.from_user.username}: {full_transcription} - in {round(time.time() - start_time, 2)}s"
        )

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))
