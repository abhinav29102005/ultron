"""
speech/text_to_speech/tts_pipeline.py – Speak, and stop speaking
================================================================
One Player for the life of the process. Safe to share across threads.
Gracefully handles missing or uninitialized voice models.
"""
import re
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


def clean_for_speech(text: str) -> str:
    """Strip markdown formatting, citations, code blocks, and symbols for natural spoken speech."""
    if not text:
        return ""
    # Strip markdown code blocks: ```...```
    text = re.sub(r"```[\s\S]*?```", " [code omitted] ", text)
    # Strip inline code: `...`
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Strip bracketed citations like [Doc_01 §12] or [Doc_01] or [1]
    text = re.sub(r"\[(?:Doc[_\s\w\d§]+|[\d,\s§]+)\]", "", text)
    # Strip markdown links: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Strip URLs
    text = re.sub(r"https?://\S+", "", text)
    # Strip markdown headers (e.g. ### Header)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Strip markdown bold/italic (**word** or *word*)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    # Strip list bullets (- item, * item)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Normalize extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def play_audio(text):
    try:
        spoken_text = clean_for_speech(text)
        if not spoken_text:
            return

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
        chunks = speaker.generate(spoken_text)
        _player.play(chunks, expect_epoch=epoch)
    except Exception as e:
        logger.debug("play_audio skipped or failed: {}", e)


def stop_audio():
    _player.stop()


def is_speaking() -> bool:
    return _player.is_playing

