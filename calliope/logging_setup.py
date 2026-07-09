import sys

from loguru import logger

from calliope.settings import Settings

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging(settings: Settings) -> None:
    """Configura loguru con un sink su stdout (catturato da Docker).

    Sostituisce il fragile ``logger.remove(0)`` con ``logger.remove()``. La
    rotation/retention su file e l'audit di privacy sono nello step 4.2.
    """
    logger.remove()
    logger.add(
        sys.stdout,
        format=LOG_FORMAT,
        level=settings.log_level.upper(),
        colorize=True,
    )
