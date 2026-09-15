import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Read from environment with sensible defaults so .env settings apply
# Transcriber
MODEL_NAME = os.getenv("STT_MODEL", "base")
DEVICE = os.getenv("STT_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "int8")
BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "3"))

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

# TTS
TTS_MODEL_PATH = str(BASE_DIR / "text_to_speech" / "models" / "en_US-lessac-medium.onnx")
TTS_DEVICE = "cpu"
