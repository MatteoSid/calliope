"""Streaming della trascrizione verso Telegram a intervalli controllati.

Isola l'accumulo del testo, lo split a 4096 caratteri e l'invio/modifica dei
messaggi (logica prima mescolata nell'handler). Il messaggio viene aggiornato a
**intervalli** — di tempo o di caratteri — invece che a ogni segmento prodotto
dal modello: così il numero di chiamate API resta lineare e prevedibile, senza
scatenare il flood control di Telegram, e il testo finale è comunque completo.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from time import monotonic

from loguru import logger
from telegram import Message
from telegram.error import RetryAfter

from calliope.transcription.formatting import split_message

TELEGRAM_MAX_CHARS = 4096
CONTINUATION = " [...]"
# Sui messaggi non finali resta spazio per il marcatore di continuazione.
_SPLIT_LIMIT = TELEGRAM_MAX_CHARS - len(CONTINUATION)


async def send_or_edit_with_retry(
    operation: Callable[..., Awaitable], *, max_attempts: int = 5
):
    """Esegue un invio/modifica Telegram ritentando la STESSA operazione sul
    flood control (``RetryAfter``): rispetta l'attesa richiesta dall'API e non
    blocca l'event loop (``asyncio.sleep``).

    ``operation`` è una callable senza argomenti che restituisce una nuova
    coroutine a ogni tentativo (una coroutine non può essere ri-attesa).
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except RetryAfter as e:
            delay = (
                e.retry_after.total_seconds()
                if isinstance(e.retry_after, timedelta)
                else float(e.retry_after)
            )
            logger.warning(
                f"Flood control, waiting {delay}s (attempt {attempt}/{max_attempts})"
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Flood control: giving up after {max_attempts} attempts")


class TranscriptionStreamer:
    """Riflette il testo della trascrizione su Telegram aggiornando a intervalli.

    Mantiene lo stato (messaggi inviati, testo già mostrato) e decide quando
    fare l'edit. Uso::

        streamer = TranscriptionStreamer(message)
        await streamer.start()
        async for chunk in transcriber.stream_segments(...):
            await streamer.add(chunk)
        await streamer.finish()
    """

    def __init__(
        self,
        reply_to: Message,
        *,
        min_interval_s: float = 3.0,
        min_chars: int = 400,
    ) -> None:
        self._reply_to = reply_to
        self._min_interval_s = min_interval_s
        self._min_chars = min_chars
        self._text = ""
        self._messages: list[Message] = []
        self._rendered: list[str] = []  # testo attualmente mostrato da ogni messaggio
        self._finalized = 0  # numero di messaggi iniziali ormai definitivi
        self._last_flush = 0.0
        self._chars_since_flush = 0

    @property
    def text(self) -> str:
        """Il testo completo accumulato finora."""
        return self._text

    async def start(self) -> None:
        """Invia il placeholder iniziale (feedback immediato prima dell'inferenza)."""
        placeholder = await self._reply_to.reply_text(
            "[...]", disable_notification=True
        )
        self._messages.append(placeholder)
        self._rendered.append("[...]")
        self._last_flush = monotonic()

    async def add(self, chunk: str) -> None:
        """Accumula un nuovo pezzo di testo; aggiorna Telegram se è ora di farlo."""
        self._text += chunk
        self._chars_since_flush += len(chunk)
        now = monotonic()
        if (
            now - self._last_flush >= self._min_interval_s
            or self._chars_since_flush >= self._min_chars
        ):
            await self._flush()

    async def finish(self) -> None:
        """Flush finale: garantisce che il testo completo sia visibile in chat."""
        if not self._text.strip():
            # Non si può inviare un messaggio vuoto: mostra un fallback.
            self._text = "🔇"
        await self._flush()

    async def _flush(self) -> None:
        self._last_flush = monotonic()
        self._chars_since_flush = 0

        parts = split_message(self._text, _SPLIT_LIMIT) or [""]
        for i, part in enumerate(parts):
            if i < self._finalized:
                continue  # messaggio già definitivo: non lo tocchiamo più
            target = part + CONTINUATION if i < len(parts) - 1 else part
            await self._render(i, target)

        # Tutti i messaggi tranne l'ultimo non cambieranno più.
        self._finalized = max(self._finalized, len(parts) - 1)

    async def _render(self, index: int, target: str) -> None:
        if index < len(self._messages):
            if self._rendered[index] == target:
                return  # nessuna modifica: evita l'errore "message is not modified"
            message = self._messages[index]
            await send_or_edit_with_retry(
                lambda t=target, m=message: m.edit_text(text=t)
            )
            self._rendered[index] = target
        else:
            sent = await send_or_edit_with_retry(
                lambda t=target: self._reply_to.chat.send_message(
                    text=t, disable_notification=True
                )
            )
            self._messages.append(sent)
            self._rendered.append(target)
