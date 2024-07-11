import os

import numpy as np
import torch
from scipy.signal import resample
from transformers import WhisperForConditionalGeneration, WhisperProcessor

if torch.cuda.is_available():
    if os.getenv("WHICH_GPU"):
        device = torch.device(f"cuda:{os.getenv('WHICH_GPU')}")
    else:
        device = torch.device("cuda:0")
else:
    device = torch.device("cpu")


class whisper_inference_model:
    def __init__(self, new_sample_rate, seconds_per_chunk):
        self.new_sr = new_sample_rate
        self.samples_per_chunk = seconds_per_chunk * self.new_sr
        self.model_name = "openai/whisper-large-v3"
        self.device = device
        self.model = WhisperForConditionalGeneration.from_pretrained(
            self.model_name
        ).to(self.device)
        self.processor = WhisperProcessor.from_pretrained(self.model_name)
        self.language = "it"
        self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
            language=self.language,
            task="translate",
        )

    def get_chunks(self, audio, sr, language: str = ""):

        # if provided language is different from the model language set it
        if language != self.language:
            self.model.config.forced_decoder_ids = (
                self.processor.get_decoder_prompt_ids(
                    language=language,
                    task="translate",
                )
            )
            self.language = language

        # Calculate the number of samples in the resampled signal.
        num_samples = int(len(audio) * self.new_sr / sr)

        # Resample the audio signal.
        resampled_audio = resample(audio, num_samples)

        # Calculate the number of chunks.
        num_chunks = int(np.ceil(len(resampled_audio) / self.samples_per_chunk))

        # Split the resampled audio into chunks.
        chunks = np.array_split(resampled_audio, num_chunks)

        return chunks, num_chunks

    def change_language(self, language):
        self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
            language=language,
            task="transcribe",
        )

    def get_transcription(self, audio, sr, language: str = ""):
        chunks, num_chunks = self.get_chunks(audio, sr, language)
        results = []
        for i, chunk in enumerate(chunks):
            inputs = self.processor