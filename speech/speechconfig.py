import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Read from environment with sensible defaults so .env settings apply
# Transcriber
MODEL_NAME = os.getenv("STT_MODEL", "base")
DEVICE = os.getenv("STT_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "int8")
BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "3"))
_stt_lang = os.getenv("STT_LANGUAGE", "en").strip()
STT_LANGUAGE = None if _stt_lang.lower() in ("auto", "none", "") else _stt_lang

# Recorder
SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))
BLOCK_SIZE = int(os.getenv("AUDIO_CHUNK_SIZE", "1024"))
INPUT_DEVICE = None
OUTPUT_DEVICE = None
# How long a pause ends your turn. At 1.0s a normal mid-sentence breath
# cut long utterances off. Raise SILENCE_TIMEOUT in .env if you speak slowly.
SILENCE_TIMEOUT = float(os.getenv("SILENCE_TIMEOUT", "2.0"))

# VAD
VAD_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))

# TTS - Default to deep male Bryce model for Avengers Ultron persona, fallback to Lessac
bryce_onnx = BASE_DIR / "text_to_speech" / "models" / "en_US-bryce-medium.onnx"
bryce_json = BASE_DIR / "text_to_speech" / "models" / "en_US-bryce-medium.onnx.json"
lessac_onnx = BASE_DIR / "text_to_speech" / "models" / "en_US-lessac-medium.onnx"

default_tts = str(bryce_onnx) if (bryce_onnx.exists() and bryce_json.exists()) else str(lessac_onnx)

TTS_MODEL_PATH = os.getenv("TTS_MODEL_PATH", default_tts)
TTS_DEVICE = os.getenv("TTS_DEVICE", "cpu")
ULTRON_VOICE_EFFECT = os.getenv("ULTRON_VOICE_EFFECT", "true").lower() in ("true", "1", "yes", "on")
