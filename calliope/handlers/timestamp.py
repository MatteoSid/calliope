import os
import tempfile

import librosa
import telegram
from loguru import logger
from moviepy import VideoFileClip
from telegram import Update
from telegram.ext import ContextTypes

from calliope.media.silence import detect_silence
from calliope.settings import settings


async def timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")

    storage = context.bot_data["storage"]
    transcriber = context.bot_data["transcriber"]

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
        audio.write_audiofile(file_audio_path, logger=None)

        audio, sr = librosa.load(file_audio_path)

    # Pre-filtro: video senza parlato → reaction 🔇, nessuna trascrizione.
    if detect_silence(audio, sr):
        logger.info(
            f"{update.message.from_user.username}: silent video, skipping transcription"
        )
        await update.message.set_reaction("🔇")
        return

    # Chiama il metodo che lavora direttamente con audio e sample rate
    language = storage.get_language(update) or settings.default_language
    result_str = transcriber.transcribe_with_timestamps(audio, language=language)

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
