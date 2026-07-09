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
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # None = auto: float16 su GPU, int8 su CPU (override es. "int8_float16").
    whisper_compute_type: str | None = None
    default_language: str | None = None  # None = auto-detect

    # --- Limiti / runtime ---
    silence_threshold: int = 70  # predisposta per lo step 2.7 (detect_silence)
    max_media_duration_s: int = 1800  # media più lunghi vengono rifiutati (3.3)
    # Allowlist di chat abilitate (vuota = bot pubblico). Utile a chi self-hosta
    # su GPU propria. In ``.env``: ``ALLOWED_CHAT_IDS=123,456`` (interi separati
    # da virgola). NoDecode evita il parsing JSON automatico di pydantic-settings.
    allowed_chat_ids: Annotated[list[int], NoDecode] = []
    log_level: str = "INFO"
    # Percorso di un file di log opzionale (oltre a stdout). Se impostato, il
    # sink file ruota ogni giorno con retention 14 giorni e compressione zip.
    log_file: str | None = None

    @field_validator("admin_chat_id", "default_language", "log_file", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        """Tratta una variabile opzionale lasciata vuota (es. ``ADMIN_CHAT_ID=``)
        come non impostata, invece di far fallire il parsing."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def _parse_id_list(cls, v: object) -> object:
        """Parsa la lista di chat ID da stringa comma-separated (o la lascia
        invariata se già una lista)."""
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return []
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    def chat_allowed(self, chat_id: int) -> bool:
        """True se la chat può usare il bot (allowlist vuota = tutte)."""
        return not self.allowed_chat_ids or chat_id in self.allowed_chat_ids


settings = Settings()  # type: ignore[call-arg]  # i campi sono caricati dall'ambiente
