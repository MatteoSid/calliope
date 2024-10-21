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

        self.model_name = "deepdml/faster-whisper-large-v3-turbo-ct2"
        self.device = device
        self.model = WhisperModel(self.model_name, device=self.device, device_index=0)
        self.language = "it"

        logger.info("Model loaded.")

    def transcribe(self, file_audio):
        segments, info = self.model.transcribe(file_audio)
        return segments

    # #TODO: coming soon
    # def change_language(self, language):
    #     self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
    #         language=language,
    #         task="transcribe",
    #     )
