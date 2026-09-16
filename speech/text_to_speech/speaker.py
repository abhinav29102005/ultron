import logging
import os
from speech.speechconfig import (
    TTS_MODEL_PATH,
    TTS_DEVICE,
    ULTRON_VOICE_EFFECT,
)
from speech.text_to_speech.ultron_dsp import apply_ultron_voice_effect, UltronAudioChunk

logger = logging.getLogger(__name__)


class Speaker:
    def __init__(self):
        self.voice = self.load_model()
        self.ultron_effect = ULTRON_VOICE_EFFECT

    def load_model(self):
        """
        Load the Piper voice model with Ultron cadence tuning.
        """
        if not os.path.exists(TTS_MODEL_PATH):
            logger.info("Piper voice model not found at %s. Spoken audio output disabled.", TTS_MODEL_PATH)
            return None
        try:
            from piper import PiperVoice
            voice = PiperVoice.load(
                model_path=TTS_MODEL_PATH,
                use_cuda=(TTS_DEVICE == "cuda")
            )
            # Ultron speaks with deliberate, theatrical James Spader pacing
            if hasattr(voice, "config") and hasattr(voice.config, "length_scale"):
                voice.config.length_scale = 1.12
            return voice
        except Exception as e:
            logger.warning("Failed to initialize Piper voice engine: %s", e)
            return None

    def generate(self, text: str):
        """
        Yield AudioChunks processed with the Avengers Ultron voice DSP effect.
        """
        if self.voice is None:
            return
        try:
            for chunk in self.voice.synthesize(text):
                if self.ultron_effect and hasattr(chunk, "audio_float_array"):
                    transformed = apply_ultron_voice_effect(
                        chunk.audio_float_array,
                        sample_rate=chunk.sample_rate,
                    )
                    yield UltronAudioChunk(
                        audio_float_array=transformed,
                        sample_rate=chunk.sample_rate,
                        sample_channels=getattr(chunk, "sample_channels", 1),
                    )
                else:
                    yield chunk
        except Exception as e:
            logger.warning("Synthesis error during audio generation: %s", e)
