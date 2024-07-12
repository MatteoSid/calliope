from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from calliope.src.utils.MongoClient import calliope_db_init

calliope_db = calliope_db_init()


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        language = update.message.text.split(" ")[1]
        calliope_db.change_language(update=update, language=language)

        logger.info(f"{update.message.from_user.username}: set language to {language}")

        await update.message.reply_text(
            f"Language set to {language}",
            disable_notification=True,
        )
    except Exception as e:
        logger.info(
            f"User {update.message.from_user.username or update.message.from_user.id} tried to use /lang command without specifying language"
        )
        await update.message.reply_markdown_v2(
            "🚧BETA FEATURE: Choose the language you want to transcribe with the /lang command\."
            + "\nFor example: `/lang es` for spanish or `/lang it` for italian\.",
            disable_notification=True,
        )
