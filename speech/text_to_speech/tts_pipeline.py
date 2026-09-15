"""
speech/text_to_speech/tts_pipeline.py – Speak, and stop speaking
================================================================
One Player for the life of the process. The previous version rebound a module
global in both ``play_audio`` and ``stop_audio``, so after an interrupt the
worker thread went on writing into a Player nobody else referenced — the stop
had no effect on the audio you could actually hear.

``Player`` is now safe to share across threads, so there is no reason to swap
it out. See its docstring for how an interrupt reaches a blocking write.
"""

from speech.text_to_speech.player import Player
from speech.text_to_speech.speaker import Speaker

_player = Player()
_cached_speaker = None


def _get_speaker():
    global _cached_speaker
    if _cached_speaker is None:
        _cached_speaker = Speaker()
    return _cached_speaker


def get_player() -> Player:
    """The shared player. Exposed for tests and for state queries."""
    return _player


def play_audio(text):
    speaker = _get_speaker()

    # Anything already speaking is superseded by this call, not layered under
    # it. Without this, two overlapping responses fight over the output device.
    _player.stop()

    # Synthesis takes seconds. An interrupt arriving inside generate() has to
    # cancel this utterance, not the one before it — so the generation is
    # sampled now and handed to play(), which drops the audio if it moved.
    epoch = _player.epoch
    chunks = speaker.generate(text)
    _player.play(chunks, expect_epoch=epoch)


def stop_audio():
    _player.stop()


def is_speaking() -> bool:
    return _player.is_playing
