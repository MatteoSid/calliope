"""Notifiche e utilità per l'owner del bot.

Sostituisce il vecchio ``admin_feature.py`` (che costruiva l'URL dell'API a mano
e usava ``requests`` sincrono) con notifiche inviate tramite il bot PTB già
istanziato. Tutte le funzioni sono no-op se ``ADMIN_CHAT_ID`` non è configurato.
"""

from loguru import logger
from telegram import Bot, Update
from telegram.error import TelegramError

from calliope.settings import settings


def is_admin(user_id: int | None) -> bool:
    """True se ``user_id`` corrisponde all'owner configurato (ADMIN_CHAT_ID)."""
    return settings.admin_chat_id is not None and user_id == settings.admin_chat_id


async def notify_admin(bot: Bot, text: str) -> None:
    """Invia un messaggio all'owner, se ADMIN_CHAT_ID è configurato."""
    if settings.admin_chat_id is None:
        return
    try:
        await bot.send_message(chat_id=settings.admin_chat_id, text=text)
    except TelegramError as e:
        logger.error(f"Failed to notify admin: {e}")


async def notify_registration(bot: Bot, kind: str, update: Update) -> None:
    """Notifica all'owner il primo uso da parte di un nuovo utente o gruppo."""
    if settings.admin_chat_id is None:
        return

    if kind == "user":
        user = update.effective_user
        if user is None:
            return
        who = f"@{user.username}" if user.username else user.full_name
        text = f"🆕 New user: {who} (id {user.id})"
    elif kind == "group":
        chat = update.effective_chat
        if chat is None:
            return
        text = f"🆕 New group: {chat.title} (id {chat.id})"
    else:
        return

    await notify_admin(bot, text)


async def notify_error(bot: Bot, update: object, error: BaseException | None) -> None:
    """Inoltra all'owner un riassunto dell'eccezione, con la chat anonimizzata."""
    if settings.admin_chat_id is None:
        return

    chat_type = "unknown"
    if isinstance(update, Update) and update.effective_chat is not None:
        chat_type = update.effective_chat.type

    text = (
        "⚠️ Error in Calliope\n"
        f"Type: {type(error).__name__}\n"
        f"Chat type: {chat_type}\n"
        f"Detail: {str(error)[:500]}"
    )
    await notify_admin(bot, text)
