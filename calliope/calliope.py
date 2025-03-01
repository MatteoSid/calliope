import os

from loguru import logger
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from calliope.src.utils.utils import title

title()

from calliope.src.commands.change_language import change_language
from calliope.src.commands.help import help_command
from calliope.src.commands.start import start
from calliope.src.commands.stt import stt
from calliope.src.commands.timestamp import timestamp
from calliope.src.utils.logger_setter import logger_setter
from calliope.src.utils.MongoClient import calliope_db_init

logger_setter()

calliope_db = calliope_db_init()

logger.info("Starting Calliope")


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = (
        Application.builder()
        .token(os.getenv("TELEGRAM_TOKEN"))
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )
    logger.info("Application is running")

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    # application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("lang", change_language))

    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, stt))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, stt))
    application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND, timestamp))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
