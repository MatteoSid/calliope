import os
import tempfile
import time

import librosa
import numpy as np
from faster_whisper import WhisperModel
from loguru import logger
from moviepy.editor import VideoFileClip
from telegram import Update
from telegram._files.videonote import VideoNote
from telegram._files.voice import Voice
from telegram.error import RetryAfter
from telegram.ext import ContextTypes


class WhisperTranscriber:
    """
    Classe per trascrivere audio usando il modello deepdml/faster-whisper-large-v3-turbo-ct2.
    La trascrizione è suddivisa in segmenti di 1 minuto con i relativi timestamp.
    """

    def __init__(
        self,
        model_path: str = "deepdml/faster-whisper-large-v3-turbo-ct2",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        """
        Inizializza il modello Whisper.
        - model_path: percorso o nome del modello (default: 'deepdml/faster-whisper-large-v3-turbo-ct2').
        - device: dispositivo su cui eseguire il modello ("cpu" o "cuda").
        - compute_type: precisione dei calcoli (es. "int8", "float16", "float32").
        """
        self.model = WhisperModel(model_path, device=device, compute_type=compute_type)

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


async def timestamp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(temp_dir)

        file = await context.bot.get_file(update.effective_message.video.file_id)
        file_video_path = os.path.join(temp_dir, "temp_video.mp4")
        await file.download_to_drive(file_video_path)
        video = VideoFileClip(file_video_path)
        audio = video.audio

        file_audio_path = os.path.join(temp_dir, "temp_audio.ogg")
        audio.write_audiofile(file_audio_path, verbose=False, logger=None)

        audio, sr = librosa.load(file_audio_path)

    # --- TRASCRIZIONE ---
    transcriber = WhisperTranscriber(
        model_path="deepdml/faster-whisper-large-v3-turbo-ct2",
        device="cuda",  # oppure 'cuda' se hai una GPU
        compute_type="int8",  # puoi usare float16, float32, ecc.
    )

    # Chiama il metodo che lavora direttamente con audio e sample rate
    result_str = transcriber.transcribe_with_timestamps(audio)

    # Scriviamo il risultato in un file di testo
    with tempfile.TemporaryDirectory() as temp_dir:
        transcript_path = os.path.join(temp_dir, "trascrizione.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(result_str)

        # Inviamo il file .txt di trascrizione all'utente
        await update.message.reply_document(document=open(transcript_path, "rb"), filename="trascrizione.txt")
