import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel
from loguru import logger

from calliope.settings import Settings

# Sentinella: il thread produttore segnala la fine dello stream dei segmenti.
_STREAM_DONE = object()


class WhisperTranscriber:
    """Motore di trascrizione basato su faster-whisper.

    Va istanziato una sola volta all'avvio (in ``main``) e iniettato negli
    handler: l'``__init__`` sceglie il device e carica il modello (operazione
    costosa, nessun side effect a import-time).

    L'inferenza è CPU/GPU-bound e **bloccante**: viene eseguita in un
    ``ThreadPoolExecutor`` dedicato con un solo worker, così l'event loop resta
    libero (il bot risponde ad altri comandi/utenti durante una trascrizione) e
    le richieste si accodano una alla volta (una GPU = una trascrizione per
    volta). I metodi pubblici sono coroutine da attendere; il consumo del
    generatore lazy di faster-whisper avviene **dentro** il thread.
    """

    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.whisper_model
        self.device = self._resolve_device(settings)
        self.compute_type = self._resolve_compute_type(settings, self.device)
        logger.info(
            f"Loading model {self.model_name} "
            f"(device={self.device}, compute_type={self.compute_type})..."
        )
        self.model = WhisperModel(
            self.model_name,
            device=self.device,
            device_index=settings.device_index,
            compute_type=self.compute_type,
        )
        # max_workers=1: le trascrizioni si serializzano naturalmente (coda).
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
        logger.info("Model loaded.")

    def shutdown(self) -> None:
        """Arresta l'executor attendendo la trascrizione in corso (step 3.5)."""
        self._executor.shutdown(wait=True)

    @staticmethod
    def _resolve_device(settings: Settings) -> str:
        """Sceglie il device: se ``auto`` prova CUDA con fallback a CPU dichiarato."""
        if settings.device != "auto":
            return settings.device
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
        logger.info("No CUDA device detected, falling back to CPU")
        return "cpu"

    @staticmethod
    def _resolve_compute_type(settings: Settings, device: str) -> str:
        """compute_type esplicito: float16 su GPU, int8 su CPU (override da settings)."""
        if settings.whisper_compute_type:
            return settings.whisper_compute_type
        return "float16" if device == "cuda" else "int8"

    async def stream_segments(
        self, file_audio, language: str | None = None
    ) -> AsyncIterator[str]:
        """Trascrive l'audio producendo i testi dei segmenti man mano.

        L'inferenza (bloccante) gira nel thread executor; ogni segmento prodotto
        dal generatore lazy di faster-whisper viene inoltrato all'event loop via
        una coda thread-safe. Il consumer può così aggiornare Telegram in tempo
        reale senza che l'event loop venga mai bloccato.

        Args:
            file_audio: array/percorso audio accettato da faster-whisper.
            language: codice lingua ISO (es. ``"it"``); ``None`` = auto-detect.

        Yields:
            Il testo di ciascun segmento, nell'ordine di produzione.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _produce() -> None:
            try:
                segments, _info = self.model.transcribe(file_audio, language=language)
                for segment in segments:
                    loop.call_soon_threadsafe(queue.put_nowait, segment.text)
            except Exception as exc:  # inoltra l'errore al consumer
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, _STREAM_DONE)

        future = loop.run_in_executor(self._executor, _produce)
        try:
            while True:
                item = await queue.get()
                if item is _STREAM_DONE:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            await future  # assicura il completamento del thread produttore

    async def transcribe_with_timestamps(
        self,
        audio_data: np.ndarray,
        return_dict: bool = False,
        language: str | None = None,
    ):
        """Variante con timestamp, eseguita nel thread executor (vedi
        :meth:`_transcribe_with_timestamps`)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._transcribe_with_timestamps,
            audio_data,
            return_dict,
            language,
        )

    def _transcribe_with_timestamps(
        self,
        audio_data: np.ndarray,
        return_dict: bool = False,
        language: str | None = None,
    ):
        """
        Trascrive il contenuto di 'audio_data' (già caricato in memoria) e restituisce il testo
        suddiviso in intervalli di 1 minuto con i rispettivi timestamp.

        Parametri:
        - audio_data: array NumPy con i campioni dell'audio (float o int).
        - sample_rate: frequenza di campionamento dell'audio (es. 22050, 44100, 16000, ecc.).
        - return_dict: se True, restituisce un dizionario {intervalo: testo}; altrimenti una stringa.

        Ritorna:
        - Una stringa formattata con segmenti [HH:MM:SS - HH:MM:SS]: trascrizione
        oppure un dizionario { (start, end): "trascrizione" } a seconda di return_dict.
        """
        # Assicuriamoci che l'audio sia in float32 (richiesto spesso da modelli come Whisper)
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        # Esegui la trascrizione con timestamp a livello di parola
        segments, info = self.model.transcribe(
            audio=audio_data, word_timestamps=True, language=language
        )

        # Dizionario che accumula le parole per ciascun minuto
        minute_segments: dict[int, list[str]] = {}
        total_duration = 0.0

        for segment in segments:
            for word in segment.words:
                start_time = word.start
                end_time = word.end
                text = word.word

                # Minuto in cui cade la parola
                minute_index = int(start_time // 60)

                # Aggiorna la durata totale se necessario
                if end_time > total_duration:
                    total_duration = end_time

                # Aggiungi la parola al dizionario
                if minute_index not in minute_segments:
                    minute_segments[minute_index] = []
                minute_segments[minute_index].append(text)

        # Costruiamo un dict finale con chiave [HH:MM:SS - HH:MM:SS] e valore testo
        result_dict = {}
        # Numero totale di minuti trascritti (includendo l'eventuale ultimo parziale)
        num_minutes = int(total_duration // 60) + 1

        for i in range(num_minutes):
            start_interval = i * 60
            # L'ultimo minuto potrebbe non essere pieno
            end_interval = min((i + 1) * 60, total_duration)

            # Formattazione dei timestamp
            start_ts = f"{int(start_interval // 3600):02d}:{int((start_interval % 3600) // 60):02d}:{int(start_interval % 60):02d}"
            end_ts = f"{int(end_interval // 3600):02d}:{int((end_interval % 3600) // 60):02d}:{int(end_interval % 60):02d}"

            # Preleva le parole accumulate in questo minuto
            words = minute_segments.get(i, [])

            # Ricostruisce la frase (semplice concatenazione con spazi)
            if not words:
                text_segment = ""
            else:
                text_segment = words[0]
                for w in words[1:]:
                    # Se la parola inizia con un segno di punteggiatura comune, la attacchiamo direttamente
                    if w and (w[0].isalnum() or w[0] == "¿" or w[0] == "¡"):
                        text_segment += " " + w
                    else:
                        text_segment += w

            interval_label = f"[{start_ts} - {end_ts}]"
            result_dict[interval_label] = text_segment.strip()

        # Ritorno dei risultati nel formato desiderato
        if return_dict:
            return result_dict
        else:
            output_lines = [
                f"{interval_label}: {text}"
                for interval_label, text in result_dict.items()
            ]
            return "\n".join(output_lines)
