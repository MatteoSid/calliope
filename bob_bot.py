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
from typing import List

import librosa
import numpy as np
import torch
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from rich.progress import track
from scipy.signal import resample
from bob_telegram_tools.utils import TelegramTqdm
from bob_telegram_tools.bot import TelegramBot
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
import time


Path("voice_msgs").mkdir(parents=True, exist_ok=True)

# Enable logging
logging.basicConfig(
    format="%(asctime)s-%(name)s-%(levelname)s-%(message)s", level=logging.INFO
)

TOKEN = Path("TOKEN.txt").read_text()
logger = logging.getLogger(__name__)


def split_string(string: str) -> List[str]:
    """
    Split a string into a list of strings of length < 4096.
    :param string: the string to split
    :return: a list of strings
    """
    if len(string) < 4096:
        return [string]
    else:
        words = string.split()
        result = []
        current_string = ""
        for word in words:
            if len(current_string) + len(word) + 1 > 4096:
                result.append(current_string)
                current_string = word
            else:
                current_string += " " + word
        result.append(current_string)
        return result


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

        model_name = "openai/whisper-large-v2"
        processor = WhisperProcessor.from_pretrained(model_name)

        message = await update.message.reply_text("Loading model...")
        model = WhisperForConditionalGeneration.from_pretrained(model_name).to(device)

        model.config.forced_decoder_ids = processor.get_decoder_prompt_ids(
            language="it",
            task="transcribe",
        )

        audio, sr = librosa.load(file_name)
        # Define the new sample rate.
        new_sr = 16000

        # Calculate the number of samples in the resampled signal.
        num_samples = int(len(audio) * new_sr / sr)

        # Resample the audio signal.
        resampled_audio = resample(audio, num_samples)
        # Calculate the number of samples per chunk.
        samples_per_chunk = 20 * new_sr

        # Calculate the number of chunks.
        num_chunks = int(np.ceil(len(resampled_audio) / samples_per_chunk))

        # Split the resampled audio into chunks.
        chunks = np.array_split(resampled_audio, num_chunks)

        decoded_message: str = ""
        # Create a progress bar
        current_percentage = 0
        await context.bot.edit_message_text(
            text=f"Processing data: {current_percentage}%",
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        for i, chunk in enumerate(track(chunks, description="[green]Processing data")):
            input_features = processor(
                chunk, return_tensors="pt", sampling_rate=new_sr
            ).input_features
            predicted_ids = model.generate(
                input_features.to(device),
                is_multilingual=True,
                max_length=10000,
            )
            transcription = processor.batch_decode(
                predicted_ids, skip_special_tokens=True
            )

            decoded_message += transcription[0]

            # Update the progress bar
            current_percentage = int((i + 1) / num_chunks * 100)
            text = f"Processing data: {current_percentage}%"
            await context.bot.edit_message_text(
                text=text,
                chat_id=message.chat_id,
                message_id=message.message_id,
            )

        # Delete the progress bar
        await context.bot.delete_message(
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        msgs_list = split_string(decoded_message)
        for msg in msgs_list:
            logger.info(f"Transcription: {msg}")
            await update.message.reply_text(msg)

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))

    del model
    torch.cuda.empty_cache()


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
