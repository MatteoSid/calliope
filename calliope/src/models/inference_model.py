from venv import logger

import torch
from faster_whisper import WhisperModel

# TODO: deve essere testato
if torch.cuda.is_available():
    device = "cuda"
    logger.info("Using GPU")
else:
    device = "cpu"
    logger.info("Using CPU")


class whisper_inference_model:
    def __init__(self):
        logger.info("Loading model...")

        self.model_name = "large-v3"
        self.device = device
        self.model = WhisperModel(self.model_name, device=self.device)
        self.language = "it"

        logger.info("Model loaded.")

    def transcrbe(self, file_audio):
        segments, info = self.model.transcribe(file_audio)
        return segments

    # #TODO: coming soon
    # def change_language(self, language):
    #     self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
    #         language=language,
    #         task="transcribe",
    #     )
