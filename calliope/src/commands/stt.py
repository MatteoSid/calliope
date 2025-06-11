import json
import os
import tempfile
import time
from datetime import timedelta
from uuid import uuid4
from loguru import logger

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

        # Store the full transcription in Redis
        uuid = uuid4().hex
        try:
            # Ensure we're storing a string
            if not isinstance(full_transcription, str):
                full_transcription = str(full_transcription)
                
            redis_connection.setex(uuid, redis_timeout, full_transcription)
            logger.debug(f"Stored transcription in Redis with UUID: {uuid}, length: {len(full_transcription)}")
        except Exception as e:
            logger.error(f"Error storing transcription in Redis: {e}")
            # Continue anyway, the button will just not work if Redis is down

        # Only show summarize button for longer messages (> 1 minute of speech)
        word_count = len(full_transcription.split())
        keyboard = []
        
        if word_count >= 140:  # ~150 words = ~1 minute of speech
            try:
                # Create a simple dictionary for callback data
                callback_data = {"a": "summ", "u": uuid}  # Using shorter keys to save space
                callback_json = json.dumps(callback_data)
                
                # Log the callback data for debugging
                logger.debug(f"Callback data: {callback_json}")
                
                keyboard.append([
                    InlineKeyboardButton(
                        "📝 Riassunto", 
                        callback_data=callback_json
                    )
                ])
                logger.info(f"Added summarize button for message with {word_count} words")
            except Exception as e:
                logger.error(f"Error creating callback data: {e}", exc_info=True)
                # Don't add the button if we can't create the callback data
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

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
