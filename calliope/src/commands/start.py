from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from calliope.src.utils.admin import notify_registration
from calliope.src.utils.MongoClient import calliope_db_init

calliope_db = calliope_db_init()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    logger.info(f"{update.message.from_user.username}: Start command")

    created = calliope_db.add_user(update)
    if created:
        await notify_registration(context.bot, "user", update)

    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}, I'm Calliope and I convert any voice or video message into text."
        + "\nAdd me to a group or forward any voice or video message to me and you will immediately receive the transcription."
        + "\n\nHave fun!!"
        + "\n\n⚠️IMPORTANT: this bot is a beta version so it might not work as expected. Use /help command for more info."
        # reply_markup=ForceReply(selective=True),
    )
