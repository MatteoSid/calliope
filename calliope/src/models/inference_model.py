import os

import numpy as np
import torch
from faster_whisper import WhisperModel
from scipy.signal import resample

if torch.cuda.is_available():
    device = torch.device("cuda")
    # if os.getenv("WHICH_GPU"):
    #     device = torch.device(f"cuda:{os.getenv('WHICH_GPU')}")
    # else:
    #     device = torch.device("cuda:0")
else:
    device = torch.device("cpu")


class whisper_inference_model:
    def __init__(self):
        self.model_name = "large-v3"
        self.device = device
        self.model = WhisperModel(self.model_name, device="cuda")
        self.language = "it"

    def transcrbe(self, file_audio):
        segments, info = self.model.transcribe(file_audio)
        return segments

    # def change_language(self, language):
    #     self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
    #         language=language,
    #         task="transcribe",
    #     )
