"""Fixture e fake condivisi dai test.

Nessun test tocca GPU, Mongo reale o rete: gli oggetti Telegram sono finti
(``SimpleNamespace``) e lo storage usa ``mongomock``.
"""

from types import SimpleNamespace

import mongomock
import pytest

from calliope.settings import Settings


def _build_update(
    *,
    user_id: int = 1,
    username: str | None = "alice",
    first_name: str = "Alice",
    chat_type: str = "private",
    chat_id: int | None = None,
    chat_title: str | None = None,
    text: str | None = None,
) -> SimpleNamespace:
    """Costruisce un finto ``Update`` con i soli attributi usati dal codice."""
    if chat_id is None:
        chat_id = user_id if chat_type == "private" else 1000
    user = SimpleNamespace(id=user_id, username=username, first_name=first_name)
    chat = SimpleNamespace(id=chat_id, type=chat_type, title=chat_title)
    message = SimpleNamespace(from_user=user, chat=chat, text=text)
    return SimpleNamespace(
        message=message, effective_message=message, effective_user=user
    )


@pytest.fixture
def make_update():
    """Factory di finti ``Update`` (vedi :func:`_build_update`)."""
    return _build_update


@pytest.fixture
def make_settings():
    """Factory di ``Settings`` isolata dal file .env del progetto."""

    def _factory(**overrides) -> Settings:
        overrides.setdefault("telegram_token", "test-token")
        return Settings(_env_file=None, **overrides)

    return _factory


@pytest.fixture
def storage(monkeypatch, make_settings):
    """``MongoStorage`` su un MongoDB in-memory (mongomock)."""
    monkeypatch.setattr(
        "calliope.storage.mongo.pymongo.MongoClient", mongomock.MongoClient
    )
    from calliope.storage.mongo import MongoStorage

    store = MongoStorage(make_settings())
    assert store.available, "mongomock storage should be available"
    return store
