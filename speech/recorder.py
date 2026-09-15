"""
speech/recorder.py – Audio Recorder
=====================================
Defines the voice recording interface.
All methods raise NotImplementedError.

Team: Speech Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings
    from speech.microphone import Microphone


class Recorder:
    """
    Captures voice audio using VAD or thresholding.
    All methods raise NotImplementedError.
    """

    def __init__(self, microphone: Microphone, settings: Settings) -> None:
        """
        Initialise Recorder.
        """
        raise NotImplementedError

    def record(self) -> bytes:
        """
        Record until silence is detected.
        TODO: Implement voice activity recording.
        """
        raise NotImplementedError

    async def record_async(self) -> bytes:
        """
        Asynchronously record.
        TODO: Implement async voice activity recording.
        """
        raise NotImplementedError
