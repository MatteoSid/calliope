from telegram import Update
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "This bot converts any voice/video message into a text message."
        + "\nAll you have to do is add the bot to a group or forward any voice/video message to the bot and you will immediately receive the corresponding transcription."
        + "\nThe processing time is proportional to the duration of the voice message."
        + "\n\n⚠️IMPORTANT⚠️: this bot is a beta version so it might not work as expected"
        # + "\nYou can also have the stats of your use with the /stats command. It works both in the private chat and in the groups"
    )
