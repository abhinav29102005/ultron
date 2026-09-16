import logging
import os
from speech.speechconfig import (
    TTS_MODEL_PATH,
    TTS_DEVICE,
)

logger = logging.getLogger(__name__)


class Speaker:
    def __init__(self):
        self.voice = self.load_model()

    def load_model(self):
        """
        Load the Piper voice model if available.
        """
        if not os.path.exists(TTS_MODEL_PATH):
            logger.info("Piper voice model not found at %s. Spoken audio output disabled.", TTS_MODEL_PATH)
            return None
        try:
            from piper import PiperVoice
            return PiperVoice.load(
                model_path=TTS_MODEL_PATH,
                use_cuda=(TTS_DEVICE == "cuda")
            )
        except Exception as e:
            logger.warning("Failed to initialize Piper voice engine: %s", e)
            return None

    def generate(self, text: str):
        """
        Yield one AudioChunk at a time.
        """
        if self.voice is None:
            return
        try:
            yield from self.voice.synthesize(text)
        except Exception as e:
            logger.warning("Synthesis error during audio generation: %s", e)
