"""
speech/text_to_speech.py – Text-to-Speech (TTS) Service
=========================================================
Defines the speech synthesis interface.
All methods raise NotImplementedError.

Team: Speech Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings


class TextToSpeech:
    """
    Synthesises speech from text strings.
    All methods raise NotImplementedError.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialise TTS.
        """
        raise NotImplementedError

    def speak(self, text: str) -> None:
        """
        Synthesise text to system audio output.
        TODO: Implement TTS speech playback.
        """
        raise NotImplementedError

    async def speak_async(self, text: str) -> None:
        """
        Asynchronously speak text.
        TODO: Implement async speech playback.
        """
        raise NotImplementedError

    def synthesise_to_bytes(self, text: str) -> bytes:
        """
        Synthesise text to raw audio bytes.
        TODO: Implement TTS bytes synthesis.
        """
        raise NotImplementedError

    def set_rate(self, rate: int) -> None:
        """
        Set speech rate.
        TODO: Implement speech rate setter.
        """
        raise NotImplementedError

    def set_volume(self, volume: float) -> None:
        """
        Set speech volume.
        TODO: Implement speech volume setter.
        """
        raise NotImplementedError

    @property
    def engine_name(self) -> str:
        """
        Get engine name.
        TODO: Implement engine name getter.
        """
        raise NotImplementedError
