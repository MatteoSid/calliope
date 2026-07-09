"""Test dello streaming a intervalli e del retry sul flood control (C5)."""

import pytest
from telegram.error import RetryAfter

from calliope.transcription.formatting import split_message
from calliope.transcription.streaming import (
    _SPLIT_LIMIT,
    CONTINUATION,
    TranscriptionStreamer,
    send_or_edit_with_retry,
)


class FakeChat:
    def __init__(self):
        self.messages: list[FakeMessage] = []
        self.api_calls = 0

    def _new(self, text):
        m = FakeMessage(self, text)
        self.messages.append(m)
        return m

    async def send_message(self, text, disable_notification=False):
        self.api_calls += 1
        return self._new(text)


class FakeMessage:
    def __init__(self, chat, text=None):
        self.chat = chat
        self.text = text

    async def reply_text(self, text, disable_notification=False):
        self.chat.api_calls += 1
        return self.chat._new(text)

    async def edit_text(self, text):
        self.chat.api_calls += 1
        self.text = text
        return self


async def test_multipart_matches_split_and_bounded():
    chat = FakeChat()
    origin = FakeMessage(chat)
    streamer = TranscriptionStreamer(origin, min_interval_s=1e9, min_chars=400)
    await streamer.start()

    chunks = [f"parola{i:04d} " for i in range(750)]  # ~9000 caratteri
    for c in chunks:
        await streamer.add(c)
    await streamer.finish()

    full = "".join(chunks)
    expected = split_message(full, _SPLIT_LIMIT)
    assert len(chat.messages) == len(expected)
    for i, msg in enumerate(chat.messages):
        target = expected[i] + (CONTINUATION if i < len(expected) - 1 else "")
        assert msg.text == target
    # chiamate API lineari e limitate (<< 750 add)
    assert chat.api_calls < 100


async def test_finish_skips_identical_edit():
    chat = FakeChat()
    origin = FakeMessage(chat)
    streamer = TranscriptionStreamer(origin, min_interval_s=0.0, min_chars=1)
    await streamer.start()
    await streamer.add("ciao mondo")
    calls = chat.api_calls
    await streamer.finish()  # nessun nuovo testo → nessun edit
    assert chat.api_calls == calls
    assert chat.messages[0].text == "ciao mondo"


async def test_empty_transcription_gets_fallback():
    chat = FakeChat()
    origin = FakeMessage(chat)
    streamer = TranscriptionStreamer(origin)
    await streamer.start()
    await streamer.finish()  # nessun testo prodotto
    assert chat.messages[0].text == "🔇"


class TestFloodControlRetry:
    async def test_retries_same_operation_and_succeeds(self, monkeypatch):
        import calliope.transcription.streaming as streaming_mod

        async def _no_sleep(_):
            return None

        monkeypatch.setattr(streaming_mod.asyncio, "sleep", _no_sleep)

        attempts = {"n": 0}

        async def op():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RetryAfter(1)
            return "ok"

        result = await send_or_edit_with_retry(op, max_attempts=3)
        assert result == "ok"
        assert attempts["n"] == 2  # ha ritentato la STESSA operazione

    async def test_gives_up_after_max_attempts(self, monkeypatch):
        import calliope.transcription.streaming as streaming_mod

        async def _no_sleep(_):
            return None

        monkeypatch.setattr(streaming_mod.asyncio, "sleep", _no_sleep)

        async def always_flood():
            raise RetryAfter(1)

        with pytest.raises(RuntimeError):
            await send_or_edit_with_retry(always_flood, max_attempts=3)
