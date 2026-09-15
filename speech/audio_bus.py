"""
speech/audio_bus.py – Microphone ownership
==========================================
Two components want the microphone: the wake-word detector, which holds a
stream open continuously, and the recorder, which opens one to capture a
command. PortAudio reports an *input overflow* and takes the process down when
both hold a stream on the same device at once.

Stopping the detector is not enough on its own. ``WakeWordDetector.stop()``
only sets an event; the stream is closed later, on the detector's own thread,
in a ``finally``. A caller that stops the detector and immediately opens the
recorder is racing that ``finally``.

This module makes the handover explicit:

    with MIC.hold(owner="recorder"):
        ...  # nothing else may open an input stream in here

``hold`` blocks until the previous owner has actually closed its stream, and
raises :class:`MicBusy` rather than opening a second one if that never happens.
"""

from __future__ import annotations

import contextlib
import threading
from typing import Iterator

from config.logging_config import get_logger

logger = get_logger("audio_bus")

#: How long to wait for the previous owner to release before giving up.
DEFAULT_TIMEOUT = 3.0


class MicBusy(RuntimeError):
    """Raised when the microphone could not be acquired in time."""


class MicLock:
    """Serialises access to the input device across threads."""

    def __init__(self) -> None:
        # Deliberately not an RLock. The invariant is "one input stream on the
        # device", which is a property of the device, not of a thread: a
        # re-entrant lock would let a single thread open a second stream and
        # never notice.
        self._lock = threading.Lock()
        self._owner: str | None = None
        self._token: object | None = None

    @property
    def owner(self) -> str | None:
        """Name of the component currently holding the microphone."""
        return self._owner

    def acquire(self, owner: str, timeout: float = DEFAULT_TIMEOUT) -> object:
        """Take the microphone. Returns a token to hand back to release().

        The token, rather than the calling thread, is what identifies the
        holder: the recorder is legitimately started on one thread (the pynput
        listener, or a Qt worker) and stopped on another.
        """
        held_by = self._owner
        if not self._lock.acquire(timeout=timeout):
            raise MicBusy(
                f"{owner!r} could not get the microphone; {held_by!r} still holds it."
            )
        token = object()
        self._owner = owner
        self._token = token
        return token

    def release(self, token: object | None = None, force: bool = False) -> None:
        """Give the microphone back.

        threading.Lock is *not* owner-checked in CPython, so a stray release
        from something that never acquired would succeed and hand the device
        to the next caller while the real holder still has a stream open —
        two streams on one input, which is the whole failure this lock exists
        to prevent. A release must therefore present the token it was given.

        ``force`` is an escape hatch for teardown, where the goal is to get
        the device back regardless of who lost track of their token.
        """
        if not force and self._token is not None and token is not self._token:
            logger.warning(
                "Ignoring a microphone release without the owner's token "
                "(current owner: %s).",
                self._owner,
            )
            return

        self._owner = None
        self._token = None
        try:
            self._lock.release()
        except RuntimeError:
            # Already fully unlocked. A double release is a bug elsewhere, not
            # a reason to take the assistant down.
            logger.debug("MicLock released when it was not held.")

    @contextlib.contextmanager
    def hold(self, owner: str, timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
        """Own the microphone for the duration of the block."""
        token = self.acquire(owner, timeout=timeout)
        logger.debug("Microphone acquired by {}.", owner)
        try:
            yield
        finally:
            logger.debug("Microphone released by {}.", owner)
            self.release(token)


#: Process-wide instance. There is only one microphone.
MIC = MicLock()
