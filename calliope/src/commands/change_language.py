from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from calliope.src.utils.MongoClient import calliope_db_init

calliope_db = calliope_db_init()


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):

    language = update.message.text.split(" ")[1]
    calliope_db.change_language(update=update, language=language)

    logger.info(f"{update.message.from_user.username}: set language to {language}")

    await update.message.reply_text(
        f"Language set to {language}",
        disable_notification=True,
    )
