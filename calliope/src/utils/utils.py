import os
import tempfile
from datetime import timedelta
from typing import List

import librosa
import numpy as np
from loguru import logger
from telegram import Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice


def split_message(message: str, max_length: int) -> list:
    """
    Divide il messaggio in parti senza troncare le parole.
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
    return parts


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
    if type(update.effective_message.effective_attachment) == Voice:
        return Voice
    elif type(update.effective_message.effective_attachment) == VideoNote:
        return VideoNote


def title():
    os.system(f"clear && figlet -f slant 'Calliope'")
