"""Formattazione del testo prodotto dalla trascrizione e delle durate."""

from datetime import timedelta


def split_message(message: str, max_length: int) -> list[str]:
    """Divide il messaggio in parti senza troncare le parole."""
    parts = []
    while len(message) > max_length:
        split_index = message.rfind(" ", 0, max_length)
        if split_index == -1:
            # Nessuno spazio: si divide alla lunghezza massima.
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
