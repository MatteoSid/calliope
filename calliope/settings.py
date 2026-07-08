"""Configurazione centralizzata di Calliope.

Unico punto in cui si legge l'ambiente: ogni altro modulo importa l'istanza
``settings`` da qui invece di usare ``os.getenv``/``os.environ``.

Il file ``.env`` da caricare è selezionabile tramite la variabile d'ambiente
``CALLIOPE_ENV_FILE`` (default ``.env``): in sviluppo si usa ``.env.dev``, in
produzione ``.env``. Le variabili già presenti nell'ambiente hanno comunque la
precedenza sul file (comportamento standard di pydantic-settings), così in
Docker basta l'iniezione via ``env_file:`` del compose.
"""

import os
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurazione dell'applicazione, validata all'avvio."""

    model_config = SettingsConfigDict(
        env_file=os.getenv("CALLIOPE_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    telegram_token: SecretStr
    admin_chat_id: int | None = None

    # --- MongoDB ---
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "calliope"
    mongo_users_collection: str = "users_db"
    mongo_groups_collection: str = "groups_db"

    # --- Modello / trascrizione ---
    whisper_model: str = "deepdml/faster-whisper-large-v3-turbo-ct2"
    device: Literal["auto", "cuda", "cpu"] = "auto"
    device_index: int = 0
    default_language: str | None = None  # None = auto-detect

    # --- Limiti / runtime ---
    silence_threshold: int = 70  # predisposta per lo step 2.7 (detect_silence)
    max_media_duration_s: int = 1800  # predisposta per lo step 3.3
    log_level: str = "INFO"

    @field_validator("admin_chat_id", "default_language", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        """Tratta una variabile opzionale lasciata vuota (es. ``ADMIN_CHAT_ID=``)
        come non impostata, invece di far fallire il parsing."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


settings = Settings()
