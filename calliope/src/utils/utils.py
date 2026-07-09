import os
from datetime import timedelta

import numpy as np
from telegram import Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice

from calliope.settings import settings


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


def format_timedelta(td: timedelta) -> str:
    """Formatta una ``timedelta`` in una stringa leggibile, es. ``"1h 2m 3s"``.

    Restituisce ``"0s"`` per durate nulle o negative. Mostra solo le unità
    diverse da zero, dalla più grande alla più piccola.
    """
    total_seconds = int(td.total_seconds())
    if total_seconds <= 0:
        return "0s"

    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def detect_silence(audio: np.ndarray, sr: int, threshold: int | None = None) -> bool:
    """Determina se l'audio è (essenzialmente) muto, cioè non contiene parlato.

    Scandisce l'**intero** audio in finestre da 1 secondo e ne calcola l'energia
    (somma delle ampiezze assolute). Se nessuna finestra supera la soglia,
    l'audio è considerato muto. È un pre-filtro energetico economico: serve a
    evitare l'inferenza su clip senza parlato.

    Args:
        audio: campioni audio come array NumPy (mono).
        sr: frequenza di campionamento in Hz (dimensione della finestra da 1 s).
        threshold: energia minima per considerare una finestra "con parlato".
            Se ``None`` usa ``settings.silence_threshold``.

    Returns:
        ``True`` se l'audio è muto (nessuna finestra sopra la soglia),
        ``False`` se almeno una finestra contiene parlato.
    """
    if threshold is None:
        threshold = settings.silence_threshold

    window = int(sr)
    if window <= 0 or len(audio) == 0:
        return True

    for start in range(0, len(audio), window):
        window_energy = np.abs(audio[start : start + window]).sum()
        if window_energy >= threshold:
            return False  # trovata una finestra con parlato

    return True  # nessuna finestra sopra la soglia → audio muto


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
