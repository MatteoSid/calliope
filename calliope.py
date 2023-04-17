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


import argparse
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import librosa
import pandas as pd
from loguru import logger
from moviepy.editor import VideoFileClip
from rich.progress import track
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from inference_model import whisper_inference_model
from utils.save_users import save_user
from utils.utils import format_timedelta, split_string

parser = argparse.ArgumentParser()
parser.add_argument(
    "-v",
    "--verbose",
    type=bool,
    default=False,
    help="Set it to True to enable verbose mode",
)
args = parser.parse_args()

if args.verbose:
    logger.configure(
        handlers=[
            {
                "sink": sys.stdout,
                "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> |"
                " <level>{level: <8}</level> |"
                " <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> -"
                " <level>{message}</level>",
                "colorize": True,
            },
        ]
    )
else:
    logger.remove(0)
    logger.add(
        "out.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

logger.info("Starting Calliope")

# Get the TOKEN for logging in the bot
token_path = Path("TOKEN.txt")
if os.path.exists(token_path):
    TOKEN = Path(token_path).read_text()
else:
    with open(token_path, "w") as f:
        TOKEN = input("Insert your bot token: ")
        f.write(TOKEN)

logger.info("Loading model...")
whisper = whisper_inference_model(new_sample_rate=16000, seconds_per_chunk=20)
logger.info("Model loaded")


# Define a few command handlers. These usually take the two arguments update and context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    logger.info(f"{update.message.from_user.username}: Start command")
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}, this bot converts any voice message into text.\n\nSend or forward any voice message here and you will immediately receive the transcription.\n\nYou can also add the bot to a group and by setting it as an administrator it will convert all the audio sent in the group.\n\nHave fun!!",
        # reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "This bot converts any voice message into a text message. All you have to do is forward any voice message to the bot and you will immediately receive the corresponding text message."
        + "The processing time is proportional to the duration of the voice message.\n\nYou can also add the bot to a group and by setting it as an administrator it will convert all the audio sent in the group."
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /stats is issued."""
    logger.info(f"{update.message.from_user.username}: Stats command")
    file_path = "stast.json"

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        await update.message.reply_text("Stats not found")
        logger.error("Stats not found")

    # check if is a single user or a group
    if str(update.message.chat.type) == "private":
        # check if there is stats for the user
        if update.message.chat.username in data["single_users"]:
            total_speech_time = timedelta(
                seconds=data["single_users"][update.message.chat.username][
                    "total_speech_time"
                ]
            )
            await update.message.reply_text(
                f"Time speech converted:\n{format_timedelta(total_speech_time)}"
            )
            logger.success("Stats sent")
        else:
            await update.message.reply_text("Stats not found")
            logger.error("Stats not found")

    elif str(update.message.chat.type) in ["group", "supergroup"]:
        # check if there is stats for the group
        if str(update.message.chat.id) in data["groups"]:
            # load user stats in a dataframe
            members_stats = data["groups"][str(update.message.chat.id)]["members_stats"]
            data_tmp = pd.DataFrame.from_dict(
                members_stats, orient="index", columns=["total_speech_time"]
            )
            data_tmp.sort_values(by="total_speech_time", ascending=False, inplace=True)

            result = ""
            for index, row in data_tmp.iterrows():
                total_speech_time = timedelta(seconds=int(row["total_speech_time"]))
                result += f"@{index}: {format_timedelta(total_speech_time)}\n"

            await update.message.reply_text(result)
        else:
            await update.message.reply_text("Stats not found")


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Request from: {update.message.from_user.username}")
    # Save the user
    save_user(update)

    try:
        file_id = update.message.video_note.file_id

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                logger.info(temp_dir)

                new_file = await context.bot.get_file(file_id)
                file_video_path = os.path.join(temp_dir, "temp_video.mp4")
                await new_file.download_to_drive(file_video_path)
                video = VideoFileClip(file_video_path)
        except Exception as e:
            # if os.path.exists(temp_dir):
            #     shutil.rmtree(temp_dir)
            # TODO: handle this exception.
            # The code work even there is this error.
            logger.warning(
                "⚠️ TODO: handle this exception: error with temporary directory ⚠️"
            )

        audio = video.audio

        with tempfile.TemporaryDirectory() as temp_dir:
            file_audio_path = os.path.join(temp_dir, "temp_audio.ogg")
            audio.write_audiofile(file_audio_path, verbose=False, logger=None)

            audio, sr = librosa.load(file_audio_path)

    except AttributeError as e:
        file_id = update.message.voice.file_id

        new_file = await context.bot.get_file(file_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "temp_audio")
            await new_file.download_to_drive(file_path)
            audio, sr = librosa.load(file_path)

    except Exception as e:
        logger.error(f"Problema con il caricamento del file:\n{e}")

    try:
        chunks, num_chunks = whisper.get_chunks(audio, sr)

        decoded_message: str = ""

        # Create a progress bar
        current_percentage = 0
        message = await update.message.reply_text(
            text=f"Processing data: {current_percentage}%",
            disable_notification=True,
        )
        for i, chunk in enumerate(track(chunks, description="[green]Processing data")):
            # Transcribe the chunk
            input_features = whisper.processor(
                chunk, return_tensors="pt", sampling_rate=whisper.new_sr
            ).input_features

            # Generate the transcription
            predicted_ids = whisper.model.generate(
                input_features.to(whisper.device),
                is_multilingual=True,
                max_length=10000,
            )

            # Decode the transcription
            transcription = whisper.processor.batch_decode(
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
            logger.info(f"{update.message.from_user.username}: {msg}")
            if msg.strip() not in [
                "Sottotitoli e revisione a cura di QTSS",
                "Sottotitoli creati dalla comunità Amara.org",
            ]:
                try:
                    await update.message.reply_text(
                        msg,
                        disable_notification=True,
                    )
                    logger.success("Message sent")
                except Exception as e:
                    logger.error(e)
                    await update.message.reply_text(
                        "error",
                        disable_notification=True,
                    )
            else:
                await update.message.reply_text(
                    "...",
                    disable_notification=True,
                )
                logger.success(f"{update.message.from_user.username}: sent '...'")

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()
    logger.info("Application is running")

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))

    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, stt))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, stt))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
