import sys

from loguru import logger


def logger_setter(verbose: bool) -> None:
    if verbose:
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
