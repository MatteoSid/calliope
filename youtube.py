import re
from telegram import Update, InputFile
from pytube import YouTube
from tempfile import NamedTemporaryFile
from pathlib import Path


async def youtube_link_handler(update: Update, context):
    message_text = update.message.text
    youtube_links = re.match(
        r"(https?://(www\.)?(youtube\.com|youtu\.be)/\S+)", message_text
    ).group(0)
    if youtube_links:
        await youtube_downloader(update, youtube_links.split("/")[-1])
    else:
        await update.message.reply_text("No YouTube links found.")


async def youtube_downloader(update, video_id):
    yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
    audio_stream = yt.streams.filter(only_audio=True).first()
    with NamedTemporaryFile(prefix="ytaudio_", suffix=".mp4", dir=".") as temp_file:
        parent_dir = str(Path(temp_file.name).parent)
        filename = str(Path(temp_file.name).name)
        # throws permission error
        audio_stream.download(output_path=parent_dir, filename=filename)
        audio_file = InputFile(temp_file)
        await update.message.reply_audio(audio_file)
