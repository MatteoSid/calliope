"""Test della configurazione (pydantic-settings)."""

import pytest
from pydantic import ValidationError

from calliope.settings import Settings


def test_defaults(make_settings):
    s = make_settings()
    assert s.whisper_model == "deepdml/faster-whisper-large-v3-turbo-ct2"
    assert s.device == "auto"
    assert s.default_language is None
    assert s.max_media_duration_s == 1800
    assert s.allowed_chat_ids == []
    assert s.log_file is None


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_token_is_secret(make_settings):
    s = make_settings(telegram_token="super-secret")
    # il repr non deve esporre il valore
    assert "super-secret" not in repr(s)
    assert s.telegram_token.get_secret_value() == "super-secret"


def test_empty_optional_becomes_none(make_settings):
    s = make_settings(admin_chat_id="", default_language="", log_file="")
    assert s.admin_chat_id is None
    assert s.default_language is None
    assert s.log_file is None


class TestAllowedChatIds:
    def test_empty_allows_all(self, make_settings):
        s = make_settings(allowed_chat_ids="")
        assert s.allowed_chat_ids == []
        assert s.chat_allowed(12345) is True

    def test_csv_parsing(self, make_settings):
        s = make_settings(allowed_chat_ids="123, 456, -789")
        assert s.allowed_chat_ids == [123, 456, -789]

    def test_allowlist_enforced(self, make_settings):
        s = make_settings(allowed_chat_ids="123")
        assert s.chat_allowed(123) is True
        assert s.chat_allowed(999) is False
