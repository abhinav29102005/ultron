"""
speech/text_to_speech/tts_pipeline.py – Speak, and stop speaking
================================================================
One Player for the life of the process. Safe to share across threads.
Gracefully handles missing or uninitialized voice models.
"""
import logging
from speech.text_to_speech.player import Player
from speech.text_to_speech.speaker import Speaker

logger = logging.getLogger(__name__)

_player = Player()
_cached_speaker = None


def _get_speaker():
    global _cached_speaker
    if _cached_speaker is None:
        try:
            _cached_speaker = Speaker()
        except Exception as e:
            logger.debug("Could not instantiate Speaker: {}", e)
            return None
    return _cached_speaker


def get_player() -> Player:
    """The shared player. Exposed for tests and for state queries."""
    return _player


def play_audio(text):
    try:
        speaker = _get_speaker()
        if not speaker or getattr(speaker, "voice", None) is None:
            return

        # Anything already speaking is superseded by this call, not layered under
        # it. Without this, two overlapping responses fight over the output device.
        _player.stop()

        # Synthesis takes seconds. An interrupt arriving inside generate() has to
        # cancel this utterance, not the one before it — so the generation is
        # sampled now and handed to play(), which drops the audio if it moved.
        epoch = _player.epoch
        chunks = speaker.generate(text)
        _player.play(chunks, expect_epoch=epoch)
    except Exception as e:
        logger.debug("play_audio skipped or failed: {}", e)


def stop_audio():
    _player.stop()


def is_speaking() -> bool:
    return _player.is_playing
