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
        self.ultron_effect = ULTRON_VOICE_EFFECT
        self.voice_type = "piper"
        self.voice = self.load_model()

    def load_model(self):
        """
        Load the Piper voice model with Ultron cadence tuning, auto-downloading if missing.
        """
        if not os.path.exists(TTS_MODEL_PATH):
            logger.info("Piper voice model not found at {}. Attempting auto-download...", TTS_MODEL_PATH)
            try:
                os.makedirs(os.path.dirname(TTS_MODEL_PATH), exist_ok=True)
                model_name = os.path.basename(TTS_MODEL_PATH)
                if "bryce" in model_name:
                    url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/bryce/medium/en_US-bryce-medium.onnx"
                else:
                    url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
                import urllib.request
                urllib.request.urlretrieve(url, TTS_MODEL_PATH)
                logger.info("Successfully downloaded Piper voice model to {}", TTS_MODEL_PATH)
            except Exception as e:
                logger.warning("Failed to download Piper voice model: {}", e)

        if os.path.exists(TTS_MODEL_PATH):
            try:
                from piper import PiperVoice
                voice = PiperVoice.load(
                    model_path=TTS_MODEL_PATH,
                    use_cuda=(TTS_DEVICE == "cuda")
                )
                # Ultron speaks with deliberate, theatrical James Spader pacing
                if hasattr(voice, "config") and hasattr(voice.config, "length_scale"):
                    voice.config.length_scale = 1.12
                self.voice_type = "piper"
                return voice
            except Exception as e:
                logger.warning("Failed to initialize Piper voice engine: {}", e)

        # Fallback to SAPI5 via pyttsx3 if Piper is unavailable
        try:
            import pyttsx3
            engine = pyttsx3.init()
            self.voice_type = "pyttsx3"
            logger.info("Using pyttsx3 SAPI5 fallback for voice output.")
            return engine
        except Exception as e:
            logger.warning("No voice output engine available: {}", e)
            return None

    def generate(self, text: str):
        """
        Yield AudioChunks processed with the Avengers Ultron voice DSP effect.
        """
        if self.voice is None:
            return

        if self.voice_type == "piper":
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
                logger.warning("Synthesis error during audio generation: {}", e)
        elif self.voice_type == "pyttsx3":
            try:
                import tempfile
                import wave
                import numpy as np
                tmp = os.path.join(tempfile.gettempdir(), f"ultron_tts_{os.getpid()}.wav")
                try:
                    self.voice.save_to_file(text, tmp)
                    self.voice.runAndWait()
                    if os.path.exists(tmp):
                        with wave.open(tmp, "rb") as f:
                            sr = f.getframerate()
                            n = f.getnframes()
                            channels = f.getnchannels()
                            buf = f.readframes(n)
                        data = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
                        if channels > 1:
                            data = data.reshape(-1, channels)
                        if self.ultron_effect and channels == 1:
                            transformed = apply_ultron_voice_effect(data, sample_rate=sr)
                            yield UltronAudioChunk(audio_float_array=transformed, sample_rate=sr, sample_channels=1)
                        else:
                            yield UltronAudioChunk(audio_float_array=data, sample_rate=sr, sample_channels=channels)
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("pyttsx3 synthesis error: {}", e)

