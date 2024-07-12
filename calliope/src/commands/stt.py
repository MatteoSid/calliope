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
from calliope.src.utils.utils import message_type, split_string

calliope_db = calliope_db_init()
logger.info("Loading model...")
whisper = whisper_inference_model(new_sample_rate=16000, seconds_per_chunk=20)
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
        language = calliope_db.get_language(update)
        chunks, num_chunks = whisper.get_chunks(audio, sr, language=language)

        decoded_message: str = ""

        # Create a progress bar
        current_percentage = 0
        message = await update.message.reply_text(
            text=f"Processing data: {current_percentage}%",
            disable_notification=True,
        )
        for i, chunk in enumerate(chunks):
            # Transcribe the chunk
            input_features = whisper.processor(
                chunk, return_tensors="pt", sampling_rate=whisper.new_sr
            ).input_features

            # Generate the transcription
            predicted_ids = whisper.model.generate(
                input_features.to(whisper.device),
                is_multilingual=True,
                max_length=10000,
            )

            # Decode the transcription
            transcription = whisper.processor.batch_decode(
                predicted_ids, skip_special_tokens=True
            )

            decoded_message += transcription[0]

            # Update the progress bar
            current_percentage = int((i + 1) / num_chunks * 100)
            # TODO: add chunks durng inference (the problem is when the message is too long)
            text = f"Processing data: {current_percentage}%\n"
            await context.bot.edit_message_text(
                text=text,
                chat_id=message.chat_id,
                message_id=message.message_id,
            )

        # Delete the progress bar
        await context.bot.delete_message(
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        msgs_list = split_string(decoded_message)
        for msg in msgs_list:
            logger.info(f"{update.message.from_user.username}: {msg}")
            if msg.strip() not in [
                "Sottotitoli e revisione a cura di QTSS",
                "Sottotitoli creati dalla comunità Amara.org",
                "...",
            ]:
                try:
                    await update.message.reply_text(
                        msg,
                        disable_notification=True,
                    )
                    logger.success("Message sent")
                except Exception as e:
                    logger.error(e)
                    await update.message.reply_text(
                        "error",
                        disable_notification=True,
                    )
            else:
                logger.success(
                    f"{update.message.from_user.username}: found silence in inference, skipped"
                )

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))
