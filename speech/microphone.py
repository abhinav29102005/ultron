"""
speech/microphone.py – Microphone Abstraction
===============================================
Defines the Microphone class interface.
All methods raise NotImplementedError.

Team: Speech Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config.settings import Settings


class Microphone:
    """
    Abstractions for the microphone hardware input.
    All methods raise NotImplementedError.
    """

    def __init__(self, settings: Settings, device_index: int | None = None) -> None:
        """
        Initialise Microphone.
        """
        raise NotImplementedError

    def __enter__(self) -> Microphone:
        """
        Open device stream.
        """
        raise NotImplementedError

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        Close device stream.
        """
        raise NotImplementedError

    def open(self) -> None:
        """
        Open input stream.
        TODO: Implement stream opening logic.
        """
        raise NotImplementedError

    def close(self) -> None:
        """
        Close input stream.
        TODO: Implement stream teardown.
        """
        raise NotImplementedError

    def read(self, num_frames: int | None = None) -> bytes:
        """
        Read raw frame bytes from the stream.
        TODO: Implement frame reading logic.
        """
        raise NotImplementedError

    @staticmethod
    def list_devices() -> list[dict[str, Any]]:
        """
        List available input devices.
        TODO: Implement device listing.
        """
        raise NotImplementedError

    @property
    def is_open(self) -> bool:
        """
        Check if stream is active.
        TODO: Implement status check.
        """
        raise NotImplementedError
