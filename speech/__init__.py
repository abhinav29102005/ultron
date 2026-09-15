"""
speech/__init__.py – Speech Package
=====================================
The ``speech`` package handles all audio I/O for ULTRON, including:

  - Microphone access and stream management
  - Audio recording with silence detection
  - Speech-to-text (STT) transcription
  - Text-to-speech (TTS) synthesis and playback
  - Audio file playback

Public surface:
    - :class:`~speech.speech_to_text.recorder.Recorder`
    - :class:`~speech.speech_to_text.transcriber.Transcriber`
    - :class:`~speech.text_to_speech.speaker.Speaker`
    - :class:`~speech.text_to_speech.player.Player`

Team: Speech Team
Phase: 0 (Scaffold) → Phase 1 (Implementation)
"""

from speech.speech_to_text import Transcriber, Recorder, SpeechPipeline
from speech.text_to_speech import Speaker, Player, play_audio

__all__: list[str] = [
    "Transcriber",
    "Recorder",
    "SpeechPipeline",
    "Speaker",
    "Player",
    "play_audio",
]
