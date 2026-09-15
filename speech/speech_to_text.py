"""
speech/speech_to_text.py – Speech-to-Text (STT) Service
=========================================================
Defines the speech transcription interface.
All methods raise NotImplementedError.

Team: Speech Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings


class SpeechToText:
    """
    Transcribes audio bytes to text.
    All methods raise NotImplementedError.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialise STT.
        """
        raise NotImplementedError

    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text.
        TODO: Implement transcription logic.
        """
        raise NotImplementedError

    async def transcribe_async(self, audio_bytes: bytes) -> str:
        """
        Asynchronously transcribe audio bytes to text.
        TODO: Implement async transcription logic.
        """
        raise NotImplementedError

    @property
    def engine_name(self) -> str:
        """
        Get the name of the STT engine.
        TODO: Implement engine name retrieval.
        """
        raise NotImplementedError
