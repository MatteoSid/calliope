"""Comandi riservati all'owner del bot (protetti da ADMIN_CHAT_ID).

Gli utenti non autorizzati vengono ignorati senza risposta. Espone:
- ``/admin stats``   → statistiche globali dal DB
- ``/admin status``  → uptime, modello e device in uso
- ``/admin broadcast <messaggio>`` → invio a tutti gli utenti/gruppi con
  conferma, throttling e report finale
- un error handler globale che notifica l'owner e risponde in modo generico.
"""

import asyncio
from datetime import datetime, timedelta

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from calliope.transcription.whisper import WhisperInferenceModel
from calliope.notifier import is_admin, notify_error
from calliope.storage.mongo import calliope_db_init
from calliope.transcription.formatting import format_timedelta

calliope_db = calliope_db_init()

# ~20 msg/s: sotto il limite complessivo dell'API Bot (~30 msg/s).
BROADCAST_THROTTLE_S = 0.05

ADMIN_HELP = (
    "🛠 Admin commands:\n"
    "/admin stats — global usage statistics\n"
    "/admin status — uptime, model, device\n"
    "/admin broadcast <message> — send a message to all users and groups"
)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point del comando /admin. Ignora chi non è l'owner."""
    user = update.effective_user
    if not is_admin(user.id if user else None):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(ADMIN_HELP)
        return

    subcommand = args[0].lower()
    if subcommand == "stats":
        await _admin_stats(update, context)
    elif subcommand == "status":
        await _admin_status(update, context)
    elif subcommand == "broadcast":
        await _admin_broadcast(update, context)
    else:
        await update.message.reply_text(ADMIN_HELP)


async def _admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = calliope_db.global_stats()
    if not stats:
        await update.message.reply_text("Stats unavailable (database not reachable).")
        return

    speech = format_timedelta(timedelta(seconds=stats["total_speech_seconds"]))
    await update.message.reply_text(
        "📊 Global stats\n\n"
        f"Users: {stats['total_users']}\n"
        f"Groups: {stats['total_groups']}\n"
        f"Transcriptions: {stats['total_transcriptions']}\n"
        f"Speech processed: {speech}"
    )


async def _admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = context.bot_data.get("start_time")
    uptime = format_timedelta(datetime.now() - start_time) if start_time else "unknown"

    whisper = WhisperInferenceModel()  # singleton già caricato all'avvio
    await update.message.reply_text(
        "🩺 Status\n\n"
        f"Uptime: {uptime}\n"
        f"Model: {whisper.model_name}\n"
        f"Device: {whisper.device}"
    )


async def _admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    message = " ".join(args[1:]).strip()
    if not message:
        await update.message.reply_text("Usage: /admin broadcast <message>")
        return

    users, groups = calliope_db.get_all_chat_ids()
    total = len(users) + len(groups)
    if total == 0:
        await update.message.reply_text("No recipients registered yet.")
        return

    # Memorizza il messaggio in attesa di conferma (dati dell'owner).
    context.user_data["pending_broadcast"] = message
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Send", callback_data="broadcast:confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="broadcast:cancel"),
            ]
        ]
    )
    await update.message.reply_text(
        f"Broadcast preview — {total} recipients:\n\n{message}\n\nSend it?",
        reply_markup=keyboard,
    )


async def broadcast_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Gestisce la conferma/annullamento del broadcast."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    action = query.data.split(":", 1)[1]
    message = context.user_data.pop("pending_broadcast", None)

    if action == "cancel" or not message:
        await query.edit_message_text("Broadcast cancelled.")
        return

    await query.edit_message_text("📣 Broadcasting…")

    users, groups = calliope_db.get_all_chat_ids()
    sent, failed = 0, 0
    for chat_id in users + groups:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
            sent += 1
        except Forbidden:
            # utente/gruppo che ha bloccato o rimosso il bot: si continua
            failed += 1
        except TelegramError as e:
            failed += 1
            logger.warning(f"Broadcast to {chat_id} failed: {e}")
        await asyncio.sleep(BROADCAST_THROTTLE_S)

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"✅ Broadcast done. Sent: {sent}, Failed: {failed}",
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler globale degli errori: log completo, notifica all'owner e
    risposta generica all'utente (nessun dettaglio tecnico esposto)."""
    logger.opt(exception=context.error).error("Unhandled exception in handler")

    await notify_error(context.bot, update, context.error)

    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "Something went wrong, please try again."
            )
        except TelegramError:
            pass
