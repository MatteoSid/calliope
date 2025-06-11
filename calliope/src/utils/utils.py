import os
import tempfile
import time
from functools import lru_cache

import librosa
import numpy as np
from loguru import logger
from more_itertools import peekable
from moviepy.editor import VideoFileClip
from redis import Redis
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice


def split_message(message: str, max_length: int) -> tuple[list, int]:
    """
    Divide il messaggio in parti senza troncare le parole.
    Restituisce una tupla con (lista_delle_partizioni, numero_totale_pagine).
    """
    parts = []
    while len(message) > max_length:
        split_index = message.rfind(" ", 0, max_length)
        if (
            split_index == -1
        ):  # Se non troviamo uno spazio, dividiamo al massimo della lunghezza
            split_index = max_length
        parts.append(message[:split_index].strip())
        message = message[split_index:].strip()
    if message:
        parts.append(message)
    return parts, len(parts)


# def format_timedelta(td: timedelta) -> str:
#     """
#     Format a timedelta object into a string
#     """
#     days = td.days
#     hours, remainder = divmod(td.seconds, 3600)
#     minutes, seconds = divmod(remainder, 60)
#     result = []
#     if days > 0:
#         result.append(f"{days} days")
#     if hours > 0:
#         result.append(f"{hours} hours")
#     if minutes > 0:
#         result.append(f"{minutes} minutes")
#     if seconds > 0:
#         result.append(f"{seconds} seconds")
#     return " e ".join(result)


# TODO: introduce silence detection
def detect_silence(audio: np.ndarray, sr: int, threshold: int = 70) -> int:
    """
    Detects the number of half seconds of total silence at the end of an audio file.

    Args:
        audio_file (str): The path to the audio file to be analyzed.
        threshold (int, optional): The threshold value below which a half second of audio is considered silent. Defaults to 70.

    Returns:
        Tuple[int, float]: A tuple containing the number of half seconds of total silence at the end of the audio file and the duration of the audio file in seconds.
    """
    try:
        duration = librosa.get_duration(y=audio, sr=sr) * 1000  # in milliseconds
        seconds = []

        # transform the amplitude of the audio signal into decibels for every 0.5 seconds
        for s in range(0, len(audio), int(sr)):
            seconds.append(np.abs(audio[s : s + int(sr)]).sum())

        seconds = seconds[::-1]

        count = 0
        for s in seconds:
            if s < threshold:
                count += 1
            else:
                break
        return count, duration / 1000
    except Exception as e:
        logger.exception(e)
        raise e


def message_type(update):
    """Determines the type of media attachment in a Telegram update.

    Args:
        update: A Telegram Update object.

    Returns:
        The type of media attachment (Voice or VideoNote) if present,
        otherwise None.
    """
    if type(update.effective_message.effective_attachment) == Voice:
        return Voice
    elif type(update.effective_message.effective_attachment) == VideoNote:
        return VideoNote
    else:
        return None


def title():
    os.system(f"clear && figlet -f slant 'Calliope'")


async def extract_audio(update, context):
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
        return audio, duration


@lru_cache()
def redis_init():

    redis_conn = Redis(
        host=os.environ.get("REDIS_HOST"),
        port=int(os.environ.get("REDIS_PORT")),
        db=int(os.environ.get("REDIS_DB")),
    )
    logger.info(
        f"Redis: Connected at {os.environ.get('REDIS_HOST')}:{os.environ.get('REDIS_PORT')}"
    )
    return redis_conn


redis_connection = redis_init()
