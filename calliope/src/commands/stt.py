import os
import tempfile
import time

import librosa
from loguru import logger
from moviepy.editor import VideoFileClip
from telegram import Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from calliope.src.models.inference_model import whisper_inference_model
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import message_type, split_message

calliope_db = calliope_db_init()
logger.info("Loading model...")
whisper = whisper_inference_model()
logger.info("Model loaded.")


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    calliope_db.update(update)

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
            audio.write_audiofile(file_audio_path, verbose=False, logger=None)

            audio, sr = librosa.load(file_audio_path)
        elif message_type(update) == Voice:
            file_id = update.message.voice.file_id
            duration = update.message.voice.duration
            new_file = await context.bot.get_file(file_id)

            file_path = os.path.join(temp_dir, "temp_audio.ogg")
            await new_file.download_to_drive(file_path)
            audio, sr = librosa.load(file_path)

        logger.info("Audio loaded in {:.2f} seconds".format(time.time() - start_time))

    try:
        start_time = time.time()
        segments = whisper.transcrbe(audio)
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
                try:
                    if i < len(message_parts) - 1:
                        part += " [...]"

                    if i == 0:
                        await context.bot.edit_message_text(
                            text=part,
                            chat_id=current_message.chat_id,
                            message_id=current_message.message_id,
                        )
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

            full_transcription = message_parts[
                -1
            ]  # Mantieni l'ultima parte per il prossimo ciclo

        logger.success(
            f"{update.message.from_user.username}: {full_transcription} - in {round(time.time() - start_time, 2)}s"
        )

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))
