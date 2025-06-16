import threading
from venv import logger

import numpy as np
import torch
from faster_whisper import WhisperModel
from loguru import logger

# TODO: deve essere testato
if torch.cuda.is_available():
    device = "cuda"
    logger.info("Using GPU")
else:
    device = "cpu"
    logger.info("Using CPU")


class WhisperInferenceModel:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                logger.info("Loading model...")
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
                logger.info("Model loaded.")
        return cls._instance

    def _initialize(self):
        self.model_name = "deepdml/faster-whisper-large-v3-turbo-ct2"
        self.device = "cuda"  # Cambia in "cpu" se necessario
        self.model = WhisperModel(self.model_name, device=self.device, device_index=0)
        self.language = "it"

    def transcribe(self, file_audio, **kwargs):
        segments, info = self.model.transcribe(file_audio, **kwargs)
        return segments

    # #TODO: coming soon
    # def change_language(self, language):
    #     self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
    #         language=language,
    #         task="transcribe",
    #     )

    def transcribe_with_timestamps(
        self, audio_data: np.ndarray, return_dict: bool = False
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
        segments, info = self.model.transcribe(audio=audio_data, word_timestamps=True)

        # Dizionario che accumula le parole per ciascun minuto
        minute_segments = {}
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
            start_ts = f"{int(start_interval//3600):02d}:{int((start_interval%3600)//60):02d}:{int(start_interval%60):02d}"
            end_ts = f"{int(end_interval//3600):02d}:{int((end_interval%3600)//60):02d}:{int(end_interval%60):02d}"

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
