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
import os
import tempfile
from pathlib import Path
from typing import List

import librosa
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

# Enable logging
logging.basicConfig(
    format="%(asctime)s-%(name)s-%(levelname)s-%(message)s", level=logging.INFO
)
from save_users import save_user

token_path = Path("TOKEN.txt")
if os.path.exists(token_path):
    TOKEN = Path(token_path).read_text()
else:
    with open(token_path, "w") as f:
        TOKEN = input("Insert your bot token: ")
        f.write(TOKEN)

logger = logging.getLogger(__name__)

whisper = whisper_inference_model(new_sample_rate=16000, seconds_per_chunk=20)


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
        f"Hi {user.mention_html()}, this bot converts any voice message into text.\n\nSend or forward any voice message here and you will immediately receive the transcription.\n\nYou can also add the bot to a group and by setting it as an administrator it will convert all the audio sent in the group.\n\nHave fun!!",
        # reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "This bot converts any voice message into a text message. All you have to do is forward any voice message to the bot and you will immediately receive the corresponding text message."
        + "The processing time is proportional to the duration of the voice message.\n\nYou can also add the bot to a group and by setting it as an administrator it will convert all the audio sent in the group."
    )


def extract_audio_from_video(video_path):
    """Extract the audio from a video file and save it as a .ogg file."""
    video = VideoFileClip(video_path)
    audio = video.audio
    new_audio_path = video_path.replace("temp_video", "temp_audio.ogg")
    audio.write_audiofile(video_path.replace("temp_video", "temp_audio.ogg"))
    return new_audio_path


async def stt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Save the user
    save_user(update)

    try:
        file_id = update.message.video_note.file_id

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                logger.info(temp_dir)

                new_file = await context.bot.get_file(file_id)
                file_video_path = os.path.join(temp_dir, "temp_video")
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
            audio.write_audiofile(file_audio_path)

            audio, sr = librosa.load(file_audio_path)

    except AttributeError as e:
        file_id = update.message.voice.file_id

        new_file = await context.bot.get_file(file_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "temp_audio")
            await new_file.download_to_drive(file_path)
            audio, sr = librosa.load(file_path)

    except Exception as e:
        logger.error(e)

    try:
        chunks, num_chunks = whisper.get_chunks(audio, sr)

        decoded_message: str = ""

        # Create a progress bar
        current_percentage = 0
        message = await update.message.reply_text(
            text=f"Processing data: {current_percentage}%"
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
            logger.info(f"Transcription: {msg}")
            if msg != "Sottotitoli e revisione a cura di QTSS":
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text("...")

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(str(e))


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, stt))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, stt))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()