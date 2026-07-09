import sys
from datetime import datetime

from loguru import logger

from calliope.settings import settings


def logger_setter() -> None:
    level = settings.log_level.upper()
    if level == "DEBUG":
        logger.configure(
            handlers=[
                {
                    "sink": sys.stdout,
                    "format": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> |"
                    " <level>{level: <8}</level> |"
                    " <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> -"
                    " <level>{message}</level>",
                    "colorize": True,
                    "level": "DEBUG",
                },
            ]
        )
    else:
        logger.remove(0)
        logger.add(
            f"logs/{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level=level,
        )
