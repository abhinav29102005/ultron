"""
speech/mic_guard.py – Keep the microphone from hearing our own output
=====================================================================
The recorder opens the default input device, which on a laptop picks up the
speakers. While music is playing, the VAD sees continuous "speech" and the
transcriber gets the song instead of the user.

This module silences our own output for the duration of a listen:

  * FRIDAY's own TTS is stopped outright (``stop_audio``).
  * External playback (Spotify) is *paused* and then resumed, but only if it
    was actually playing. Toggling blindly would start music that was never
    playing in the first place.

Usage::

    with listening_quiet():
        audio = recorder.listen()

Everything here is best-effort. Failing to pause music is never a reason to
refuse to listen, so every branch degrades to "carry on".
"""

from __future__ import annotations

import contextlib
import time
from typing import Iterator

from config.logging_config import get_logger

logger = get_logger("mic_guard")


def _stop_our_own_speech() -> None:
    """Cut any in-progress TTS. Harmless when nothing is speaking."""
    try:
        from speech.text_to_speech.tts_pipeline import stop_audio

        stop_audio()
    except Exception as exc:
        logger.debug(f"Could not stop TTS: {exc}")


def _pause_external_playback() -> bool:
    """Pause Spotify if it is playing. Returns True only if we paused it."""
    try:
        from skills.media_skill import MediaSkill, VK_MEDIA_PLAY_PAUSE, send_media_key

        skill = MediaSkill()
        if not skill.is_playing():
            return False
        send_media_key(VK_MEDIA_PLAY_PAUSE)
        # The media key is asynchronous; give the client a moment to actually
        # go quiet before we start sampling the microphone.
        time.sleep(0.25)
        logger.debug("Paused external playback for listening.")
        return True
    except Exception as exc:
        logger.debug(f"Could not pause playback: {exc}")
        return False


def _resume_external_playback() -> None:
    try:
        from skills.media_skill import VK_MEDIA_PLAY_PAUSE, send_media_key

        send_media_key(VK_MEDIA_PLAY_PAUSE)
        logger.debug("Resumed external playback.")
    except Exception as exc:
        logger.debug(f"Could not resume playback: {exc}")


@contextlib.contextmanager
def listening_quiet(resume: bool = True) -> Iterator[None]:
    """Silence our own audio output for the duration of the block.

    ``resume=False`` leaves playback paused, which is what you want when the
    command itself is going to change what is playing.
    """
    _stop_our_own_speech()
    paused = _pause_external_playback()
    try:
        yield
    finally:
        if paused and resume:
            _resume_external_playback()
