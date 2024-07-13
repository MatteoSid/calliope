import os
import tempfile

import librosa
from loguru import logger
from moviepy.editor import VideoFileClip
from telegram import Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice
from telegram.ext import ContextTypes

from calliope.src.models.inference_model import whisper_inference_model
from calliope.src.utils.MongoClient import calliope_db_init
from calliope.src.utils.utils import message_type

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

        if message_type(update) == VideoNote:
            file_id = update.message.video_note.file_id

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

            new_file = await context.bot.get_file(file_id)

            file_path = os.path.join(temp_dir, "temp_audio.ogg")
            await new_file.download_to_drive(file_path)
            audio, sr = librosa.load(file_path)

    try:
        segments = whisper.transcrbe(audio)
        decoded_message = ""

        message = await update.message.reply_text(
            text="[...]",
            disable_notification=True,
        )
        for i, segment in enumerate(segments):
            decoded_message += segment.text

            # BUG: when the message is too long, the bot can't edit the message
            await context.bot.edit_message_text(
                text=f"{decoded_message} [...]",
                chat_id=message.chat_id,
                message_id=message.message_id,
            )

        await context.bot.edit_message_text(
            text=decoded_message,
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        logger.success(f"{update.message.from_user.username}: {decoded_message}")

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))
