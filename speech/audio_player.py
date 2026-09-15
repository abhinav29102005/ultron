"""
speech/audio_player.py – Audio File Playback
==============================================
Defines the interface for audio playback.
All methods raise NotImplementedError.

Team: Speech Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from pathlib import Path


class AudioPlayer:
    """
    Plays audio files or audio byte arrays.
    All methods raise NotImplementedError.
    """

    def __init__(self, volume: float = 1.0) -> None:
        """
        Initialise AudioPlayer.
        """
        raise NotImplementedError

    def play_file(self, path: Path) -> None:
        """
        Play audio file from path.
        TODO: Implement audio file player.
        """
        raise NotImplementedError

    def play_bytes(self, audio_bytes: bytes, sample_rate: int = 22050) -> None:
        """
        Play raw audio bytes.
        TODO: Implement audio bytes player.
        """
        raise NotImplementedError

    async def play_file_async(self, path: Path) -> None:
        """
        Asynchronously play audio file.
        TODO: Implement async audio file player.
        """
        raise NotImplementedError

    async def play_bytes_async(self, audio_bytes: bytes, sample_rate: int = 22050) -> None:
        """
        Asynchronously play audio bytes.
        TODO: Implement async audio bytes player.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """
        Stop any active playback.
        TODO: Implement playback cancellation.
        """
        raise NotImplementedError

    @property
    def volume(self) -> float:
        """
        Get current volume.
        TODO: Implement volume getter.
        """
        raise NotImplementedError

    @volume.setter
    def volume(self, value: float) -> None:
        """
        Set current volume.
        TODO: Implement volume setter.
        """
        raise NotImplementedError
