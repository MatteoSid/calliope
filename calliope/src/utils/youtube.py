import re
from telegram import Update
from telegram.ext import ContextTypes
import yt_dlp
import ffmpeg
import tempfile
import time
from loguru import logger
from calliope.src.models.inference_model import WhisperInferenceModel

whisper = WhisperInferenceModel()

def is_youtube_link(text: str) -> bool:
    youtube_pattern = r"(https?://)?(www\.)?youtube\.com/+"
    youtu_be_pattern = r"(https?://)?(www\.)?youtu\.be/+"
    return bool(re.match(youtube_pattern, text) or re.match(youtu_be_pattern, text))


def youtube_to_audio(update: Update, temp_dir: str) -> str:
    """
    It converts a youtube video into text
    """
    logger.info(f"Request from: {update.message.from_user.username}")
    # Save the user
    # save_user(update)

    url = update.message.text
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": temp_dir + "/output",
        "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            ],
        }

    def download_from_url(url):
        ydl.download([url])
        stream = ffmpeg.input(temp_dir + "/output")
        stream = ffmpeg.output(stream, temp_dir + "/output.wav")

    ydl = yt_dlp.YoutubeDL(ydl_opts)
    download_from_url(url)
        
    return temp_dir + "/output.wav"