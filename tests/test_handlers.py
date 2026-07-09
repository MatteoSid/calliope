"""Test degli handler con Update/Context finti (no rete, no Telegram reale)."""

from types import SimpleNamespace

from calliope.handlers.admin import admin
from calliope.handlers.language import change_language
from calliope.handlers.start import start


class RecordingMessage:
    def __init__(self, user, chat, text=None):
        self.from_user = user
        self.chat = chat
        self.text = text
        self.replies: list[str] = []
        self.reactions: list[str] = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)
        return self

    async def reply_html(self, text, **kw):
        self.replies.append(text)
        return self

    async def set_reaction(self, emoji):
        self.reactions.append(emoji)


class FakeBot:
    def __init__(self):
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def make_handler_update(*, user_id=1, username="alice", chat_type="private", text=None):
    user = SimpleNamespace(
        id=user_id,
        username=username,
        first_name="Alice",
        full_name="Alice A.",
        mention_html=lambda: f"<a>{username}</a>",
    )
    chat = SimpleNamespace(
        id=user_id if chat_type == "private" else -100,
        type=chat_type,
        title=None if chat_type == "private" else "Group",
    )
    msg = RecordingMessage(user, chat, text=text)
    return SimpleNamespace(
        message=msg, effective_message=msg, effective_user=user, effective_chat=chat
    )


def make_ctx(storage=None, args=None, transcriber=None):
    bot_data = {}
    if storage is not None:
        bot_data["storage"] = storage
    if transcriber is not None:
        bot_data["transcriber"] = transcriber
    return SimpleNamespace(bot_data=bot_data, args=args, user_data={}, bot=FakeBot())


async def test_start_replies_and_registers(storage):
    upd = make_handler_update(user_id=5)
    ctx = make_ctx(storage=storage)
    await start(upd, ctx)
    assert len(upd.message.replies) == 1
    assert storage.users_collection.count_documents({"user_id": "5"}) == 1


class TestChangeLanguage:
    async def test_invalid_code(self, storage):
        upd = make_handler_update(text="/lang xx")
        ctx = make_ctx(storage=storage, args=["xx"])
        await change_language(upd, ctx)
        assert any("not supported" in r for r in upd.message.replies)
        assert storage.get_language(upd) is None  # nulla salvato

    async def test_valid_code(self, storage):
        upd = make_handler_update(text="/lang en")
        ctx = make_ctx(storage=storage, args=["en"])
        await change_language(upd, ctx)
        assert storage.get_language(upd) == "en"
        assert any("set to en" in r for r in upd.message.replies)

    async def test_no_args_shows_current(self, storage):
        upd = make_handler_update(text="/lang")
        storage.change_language(update=upd, language="it")
        ctx = make_ctx(storage=storage, args=[])
        await change_language(upd, ctx)
        assert any("it" in r for r in upd.message.replies)

    async def test_auto_resets(self, storage):
        upd = make_handler_update(text="/lang auto")
        storage.change_language(update=upd, language="en")
        ctx = make_ctx(storage=storage, args=["auto"])
        await change_language(upd, ctx)
        assert storage.get_language(upd) is None


class TestAdminAuthorization:
    async def test_unauthorized_is_ignored(self, storage, monkeypatch):
        import calliope.notifier as notifier

        monkeypatch.setattr(notifier.settings, "admin_chat_id", 999)
        upd = make_handler_update(user_id=111)  # non è l'owner
        ctx = make_ctx(storage=storage, args=["stats"])
        await admin(upd, ctx)
        assert upd.message.replies == []  # nessuna risposta

    async def test_authorized_gets_help(self, storage, monkeypatch):
        import calliope.notifier as notifier

        monkeypatch.setattr(notifier.settings, "admin_chat_id", 111)
        upd = make_handler_update(user_id=111)  # è l'owner
        ctx = make_ctx(storage=storage, args=[])
        await admin(upd, ctx)
        assert len(upd.message.replies) == 1
        assert "Admin commands" in upd.message.replies[0]
