"""
This is where I would convert the speech received to text using faster-whisper
"""

from faster_whisper import WhisperModel
import numpy as np
from speech.speechconfig import (
    MODEL_NAME,
    DEVICE,
    COMPUTE_TYPE,
    BEAM_SIZE,
    STT_LANGUAGE,
)


import re
from collections import Counter


def _filter_repetitions(text: str) -> str:
    """Filter out runaway Whisper hallucination loops (e.g. 'tullut tullut tullut' or 'thank you thank you')."""
    words = text.split()
    if not words:
        return ""

    cleaned_words = [re.sub(r"[^\w]", "", w).lower() for w in words]

    # Check for consecutive identical word loops (3+ times in a row)
    consecutive_run = 1
    max_consecutive = 1
    for i in range(1, len(cleaned_words)):
        if cleaned_words[i] and cleaned_words[i] == cleaned_words[i - 1]:
            consecutive_run += 1
            max_consecutive = max(max_consecutive, consecutive_run)
        else:
            consecutive_run = 1

    if max_consecutive >= 3:
        # Runaway repetition hallucination loop: discard
        return ""

    # Also check if a single word dominates (>50% of the utterance)
    non_empty = [w for w in cleaned_words if w]
    if len(non_empty) >= 3:
        counts = Counter(non_empty)
        _, top_count = counts.most_common(1)[0]
        if (top_count / len(non_empty)) >= 0.5 and top_count >= 3:
            return ""

    # Deduplicate adjacent double words (e.g. "turn turn on" -> "turn on")
    deduped = []
    for i, w in enumerate(words):
        c_w = cleaned_words[i]
        if not deduped or not c_w or c_w != cleaned_words[i - 1]:
            deduped.append(w)

    return " ".join(deduped).strip()


class Transcriber:
    def __init__(self):
        self.model = WhisperModel(
            MODEL_NAME,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) == 0:
            return ""

        # Pre-flight audio energy check: discard dead silence / room noise floor
        try:
            arr = np.asarray(audio, dtype=np.float32)
            rms = float(np.sqrt(np.mean(np.square(arr))))
            if rms < 0.005:  # Silence / noise floor
                return ""
        except Exception:
            pass

        transcribe_kwargs = {
            "beam_size": BEAM_SIZE,
            "vad_filter": True,
            "vad_parameters": dict(min_silence_duration_ms=500),
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "repetition_penalty": 1.2,
        }
        if STT_LANGUAGE:
            transcribe_kwargs["language"] = STT_LANGUAGE

        segments, info = self.model.transcribe(
            audio,
            **transcribe_kwargs,
        )

        text_parts = []
        for segment in segments:
            if getattr(segment, "no_speech_prob", 0.0) > 0.65:
                continue
            text_parts.append(segment.text)

        raw_text = " ".join(text_parts).strip()
        return _filter_repetitions(raw_text)

    def transcribe_file(self, file_path: str) -> str:
        transcribe_kwargs = {
            "beam_size": BEAM_SIZE,
            "vad_filter": True,
            "vad_parameters": dict(min_silence_duration_ms=500),
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "repetition_penalty": 1.2,
        }
        if STT_LANGUAGE:
            transcribe_kwargs["language"] = STT_LANGUAGE

        segments, info = self.model.transcribe(
            file_path,
            **transcribe_kwargs,
        )

        text_parts = []
        for segment in segments:
            if getattr(segment, "no_speech_prob", 0.0) > 0.65:
                continue
            text_parts.append(segment.text)

        raw_text = " ".join(text_parts).strip()
        return _filter_repetitions(raw_text) 