"""Test dell'estrazione media (parti pure: attachment, durata, limiti)."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from calliope.media.extract import (
    MediaTooLongError,
    UnsupportedMediaError,
    _extract_attachment,
    _to_seconds,
    download_audio,
)


def _msg(voice=None, video_note=None, video=None):
    return SimpleNamespace(voice=voice, video_note=video_note, video=video)


class TestExtractAttachment:
    def test_voice(self):
        m = _msg(voice=SimpleNamespace(file_id="v", duration=12))
        assert _extract_attachment(m) == ("v", 12)

    def test_video_note(self):
        m = _msg(video_note=SimpleNamespace(file_id="vn", duration=30))
        assert _extract_attachment(m) == ("vn", 30)

    def test_video(self):
        m = _msg(video=SimpleNamespace(file_id="vid", duration=45))
        assert _extract_attachment(m) == ("vid", 45)

    def test_unsupported_raises(self):
        with pytest.raises(UnsupportedMediaError):
            _extract_attachment(_msg())


class TestToSeconds:
    def test_int(self):
        assert _to_seconds(42) == 42

    def test_timedelta(self):
        assert _to_seconds(timedelta(seconds=90)) == 90

    def test_none(self):
        assert _to_seconds(None) == 0


class _FakeBot:
    def __init__(self):
        self.get_file_called = False

    async def get_file(self, file_id):
        self.get_file_called = True
        raise AssertionError("download must not happen when over the limit")


async def test_download_rejects_over_limit_before_download():
    bot = _FakeBot()
    msg = _msg(voice=SimpleNamespace(file_id="v", duration=100))
    with pytest.raises(MediaTooLongError) as exc:
        await download_audio(bot, msg, max_duration_s=60)
    assert exc.value.duration == 100
    assert exc.value.limit == 60
    assert bot.get_file_called is False
