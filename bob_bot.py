#!/usr/bin/env python
# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""


import logging
from datetime import datetime
from pathlib import Path

import torch
import whisper
from telegram import Bot, File, ForceReply, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

Path("voice_msgs").mkdir(parents=True, exist_ok=True)

# Enable logging
logging.basicConfig(
    format="%(asctime)s-%(name)s-%(levelname)s-%(message)s", level=logging.INFO
)

TOKEN = Path("TOKEN.txt").read_text()
logger = logging.getLogger(__name__)


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}, this bot converts any voice message into text.\n\nSend or forward any voice message here and you will immediately receive the transcription.\n\nHave fun!!",
        # reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "This bot converts any voice message into a text message. All you have to do is forward any voice message to the bot and you will immediately receive the corresponding text message."
        + "The processing time is proportional to the duration of the voice message.\n\nNote: for the moment only messages shorter than four minutes are supported."
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update)


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"stt called from {update.message.chat.username}")

    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)

    try:
        file_name = rf'voice_msgs\{update.message.chat.username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.wav'
    except:
        file_name = (
            rf'voice_msgs\new_file_{datetime.now().strftime("%Y%m%d_%H%M%S")}.wav'
        )

    await new_file.download_to_drive(file_name)

    try:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        model = whisper.load_model("large").to(device)
        result = model.transcribe(file_name)

        logger.info(result["text"])
        await update.message.reply_text(result["text"])
    except Exception as e:
        await update.message.reply_text(e.message)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, stt))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
