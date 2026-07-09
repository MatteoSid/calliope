"""Test del plumbing asincrono del transcriber (stream_segments).

Usa un modello fittizio: nessun modello Whisper reale viene caricato.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from calliope.transcription.whisper import WhisperTranscriber


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self):
        self.calls = []
        self.thread = None

    def transcribe(self, audio, language=None, **kw):
        self.calls.append({"language": language})
        self.thread = threading.current_thread().name

        def _gen():
            for w in ["uno ", "due ", "tre"]:
                yield _Seg(w)

        return _gen(), None


class _BoomModel:
    def transcribe(self, audio, language=None, **kw):
        raise ValueError("boom")


def _make(model):
    t = WhisperTranscriber.__new__(WhisperTranscriber)
    t.model = model
    t._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
    return t


async def test_stream_segments_order_and_language_forwarded():
    t = _make(_FakeModel())
    out = [text async for text in t.stream_segments([0.0], language="en")]
    t.shutdown()

    assert out == ["uno ", "due ", "tre"]
    # C1 (regressione): la lingua richiesta viene passata al modello.
    assert t.model.calls[0]["language"] == "en"
    # eseguito nel thread executor, non nell'event loop.
    assert t.model.thread.startswith("whisper")


async def test_stream_segments_propagates_error():
    t = _make(_BoomModel())
    with pytest.raises(ValueError):
        async for _ in t.stream_segments([0.0]):
            pass
    t.shutdown()
