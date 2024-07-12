from telegram import Update
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_markdown_v2(
        "This bot converts any voice/video message into a text message\."
        + "\n\nAll you have to do is add the bot to a group or forward any voice/video message to the bot and you will immediately receive the corresponding transcription\."
        + "\nThe processing time is proportional to the duration of the voice message\."
        + "\n\n🚧BETA FEATURE: Choose the language you want to transcribe with the /lang command\."
        + "\nFor example: `/lang es` for spanish or `/lang it` for italian\."
        + "\n\n⚠️IMPORTANT: this bot is a beta version so it might not work as expected\."
    )
