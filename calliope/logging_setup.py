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
    """Configura loguru: sink su stdout (catturato da Docker) e, se configurato,
    un sink su file con rotation.

    I log non contengono testo di trascrizione né contenuto dei messaggi (solo
    metadati: user/chat id, durata, tempi, esito, lingua) — audit di privacy
    dello step 4.2. Se ``settings.log_file`` è impostato, si aggiunge un sink
    file che ruota ogni giorno, conserva 14 giorni e comprime in zip.
    """
    logger.remove()
    logger.add(
        sys.stdout,
        format=LOG_FORMAT,
        level=settings.log_level.upper(),
        colorize=True,
    )
    if settings.log_file:
        logger.add(
            settings.log_file,
            format=LOG_FORMAT,
            level=settings.log_level.upper(),
            colorize=False,
            rotation="1 day",
            retention="14 days",
            compression="zip",
            enqueue=True,  # scritture non bloccanti dall'event loop
        )
