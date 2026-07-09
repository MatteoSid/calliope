"""Estrazione audio unificata da un messaggio Telegram.

Un unico percorso per i tre tipi di allegato supportati (voice, video_note,
video): scarica il file e ne decodifica l'audio in un array NumPy mono float32
a 16 kHz, pronto per faster-whisper.

La decodifica usa **ffmpeg diretto** (nessun moviepy, nessun librosa): elimina
la dipendenza pesante, i leak di ``VideoFileClip`` e il doppio ricampionamento
ogg→librosa→whisper. Si decodifica direttamente a 16 kHz mono (la frequenza a
cui lavora faster-whisper), quindi il modello non deve ricampionare di nuovo.
"""

import asyncio
import os
import tempfile
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
from loguru import logger
from telegram import Bot, Message

# faster-whisper lavora a 16 kHz mono: decodifichiamo direttamente al target.
SAMPLE_RATE = 16000


def _to_seconds(duration: int | timedelta | None) -> int:
    """Normalizza la durata di Telegram a secondi interi.

    python-telegram-bot 22 può esporre le durate come ``timedelta`` (oltre che
    come ``int``) a seconda della configurazione; questo helper le uniforma.
    """
    if isinstance(duration, timedelta):
        return int(duration.total_seconds())
    return int(duration or 0)


class UnsupportedMediaError(Exception):
    """Il messaggio non contiene un allegato audio/video gestito."""


@dataclass
class AudioData:
    """Audio decodificato e pronto per l'inferenza."""

    samples: np.ndarray  # mono float32 a 16 kHz, in [-1, 1]
    sample_rate: int
    duration: int  # durata dichiarata da Telegram, in secondi


def _extract_attachment(message: Message) -> tuple[str, int]:
    """Ritorna ``(file_id, duration)`` per l'allegato supportato.

    Match esplicito su voice/video_note/video con ramo ``else`` parlante: gli
    handler sono già filtrati per tipo, quindi il fallimento è un vero errore di
    routing, non un input dell'utente.
    """
    if message.voice is not None:
        return message.voice.file_id, _to_seconds(message.voice.duration)
    if message.video_note is not None:
        return message.video_note.file_id, _to_seconds(message.video_note.duration)
    if message.video is not None:
        return message.video.file_id, _to_seconds(message.video.duration)
    raise UnsupportedMediaError(
        "Message has no supported audio/video attachment (voice, video_note or video)."
    )


async def _decode_to_pcm(source_path: str) -> np.ndarray:
    """Decodifica un file media in PCM float32 mono a 16 kHz via ffmpeg.

    L'input è un file su disco (robusto anche con MP4 il cui moov atom è in
    coda); l'output PCM raw viene letto da stdout in memoria, senza file
    intermedi. Solleva ``RuntimeError`` se ffmpeg fallisce.
    """
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-threads",
        "0",
        "-i",
        source_path,
        "-vn",  # scarta l'eventuale traccia video
        "-f",
        "f32le",  # PCM float32 little-endian su stdout
        "-ac",
        "1",  # mono
        "-ar",
        str(SAMPLE_RATE),
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1] if detail else "unknown error"
        raise RuntimeError(f"ffmpeg failed (code {process.returncode}): {tail}")

    # frombuffer restituisce un array read-only che condivide il buffer di
    # stdout: copiamo per ottenere un array scrivibile e proprietario dei dati.
    return np.frombuffer(stdout, dtype=np.float32).copy()


async def download_audio(bot: Bot, message: Message) -> AudioData:
    """Scarica l'allegato di ``message`` e ne estrae l'audio.

    Gestisce voice, video_note e video restituendo sempre audio mono float32 a
    16 kHz. Solleva ``UnsupportedMediaError`` se il messaggio non ha un allegato
    gestito; propaga gli errori di Telegram (es. ``BadRequest`` per file troppo
    grandi) e di ffmpeg al chiamante.
    """
    file_id, duration = _extract_attachment(message)
    telegram_file = await bot.get_file(file_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = os.path.join(temp_dir, "input")
        await telegram_file.download_to_drive(source_path)
        samples = await _decode_to_pcm(source_path)

    logger.info(
        f"Audio decoded: {samples.size / SAMPLE_RATE:.1f}s of samples "
        f"(declared duration {duration}s)"
    )
    return AudioData(samples=samples, sample_rate=SAMPLE_RATE, duration=duration)
