import os
import tempfile

import librosa
import telegram
from loguru import logger
from moviepy.editor import VideoFileClip
from telegram import Update
from telegram.ext import ContextTypes

from calliope.src.models.inference_model import WhisperInferenceModel

whisper = WhisperInferenceModel()


async def timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    logger.info(f"Request from: {update.message.from_user.username}")
    with tempfile.TemporaryDirectory() as temp_dir:

        try:
            file = await context.bot.get_file(update.effective_message.video.file_id)
        except telegram.error.BadRequest as e:
            logger.error(str(e))
            await update.message.reply_text(str(e))
            return
        file_video_path = os.path.join(temp_dir, "temp_video.mp4")
        await file.download_to_drive(file_video_path)
        video = VideoFileClip(file_video_path)
        audio = video.audio

        file_audio_path = os.path.join(temp_dir, "temp_audio.ogg")
        audio.write_audiofile(file_audio_path, verbose=False, logger=None)

        audio, sr = librosa.load(file_audio_path)

    # Chiama il metodo che lavora direttamente con audio e sample rate
    result_str = whisper.transcribe_with_timestamps(audio)

    # Scriviamo il risultato in un file di testo
    with tempfile.TemporaryDirectory() as temp_dir:
        transcript_path = os.path.join(temp_dir, "trascrizione.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(result_str)

        # Inviamo il file .txt di trascrizione all'utente
        await update.message.reply_document(
            document=open(transcript_path, "rb"), filename="trascrizione.txt"
        )
    logger.success("Trascrizione completata")
