from datetime import datetime, timedelta

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from calliope.transcription.formatting import format_timedelta


def _display_name(member: dict) -> str:
    """Nome da mostrare per un membro: @username, altrimenti nome, altrimenti id."""
    username = member.get("username")
    if username:
        return f"@{username}"
    return member.get("first_name") or str(member.get("user_id", "unknown"))


def _fmt_date(value) -> str:
    """Formatta una data (datetime o stringa legacy) per la visualizzazione."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value) if value else "—"


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra le statistiche d'uso leggendo da MongoDB.

    In chat privata: statistiche personali dell'utente.
    Nei gruppi: statistiche del gruppo + classifica dei membri per tempo di
    parlato trascritto.
    """
    logger.info(f"{update.message.from_user.username}: Stats command")
    storage = context.bot_data["storage"]
    chat_type = str(update.message.chat.type)

    if chat_type == "private":
        document = storage.get_user_stats(update)
        if not document or not document.get("times_used"):
            await update.message.reply_text(
                "You haven't used Calliope yet. Send me a voice or video "
                "message and check back!"
            )
            return

        times_used = document.get("times_used", 0)
        total_speech_time = timedelta(seconds=document.get("total_speech_time", 0))
        await update.message.reply_text(
            "📊 Your Calliope stats\n\n"
            f"Transcriptions: {times_used}\n"
            f"Total speech transcribed: {format_timedelta(total_speech_time)}\n"
            f"First use: {_fmt_date(document.get('first_use'))}\n"
            f"Last use: {_fmt_date(document.get('last_use'))}"
        )
        return

    if chat_type in ("group", "supergroup"):
        document = storage.get_group_stats(update)
        members = document.get("members_stats", []) if document else []
        if not document or not members:
            await update.message.reply_text(
                "No stats for this group yet. Send a voice or video message "
                "and check back!"
            )
            return

        ranking = sorted(
            members,
            key=lambda member: member.get("total_speech_time", 0),
            reverse=True,
        )

        lines = [
            "📊 Group stats\n",
            f"Total transcriptions: {document.get('times_used', 0)}",
            "",
            "🏆 Leaderboard by speech time:",
        ]
        for position, member in enumerate(ranking, start=1):
            speech_time = timedelta(seconds=member.get("total_speech_time", 0))
            lines.append(
                f"{position}. {_display_name(member)}: {format_timedelta(speech_time)}"
            )
        await update.message.reply_text("\n".join(lines))
        return

    await update.message.reply_text(
        "Stats are available only in private chats and groups."
    )
