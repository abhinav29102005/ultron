"""
speech/stt_stream.py — Simple incremental STT streamer
=====================================================

Provides a lightweight streaming adapter over an existing Transcriber.
The implementation is intentionally conservative: it calls the existing
`Transcriber.transcribe` (or `transcribe_file`) to get the full text and
then emits incremental, timestamped transcript chunks. This scaffolding
lets the rest of the pipeline subscribe to partial transcripts for
early-retrieval experiments without requiring a low-level streaming
decoder integration right away.

The async generator `stream_from_audio` yields dicts of the form::

    {"timestamp_s": 0.5, "text": "partial transcript so far"}

The implementation is deterministic and synchronous in how it chunks the
final text; it does not perform real-time audio decoding or rely on
frame-level timing information. Replace with a proper streaming STT
decoder when available (Faster Whisper streaming API or other).
"""

from __future__ import annotations

from typing import AsyncIterator, Iterable
import math


class STTStreamer:
    """Stream text chunks built from a Transcriber instance.

    Args:
        transcriber: an object exposing `transcribe(audio)` and/or
            `transcribe_file(path)` that return the full transcript string.
    """

    def __init__(self, transcriber: object) -> None:
        self.transcriber = transcriber

    async def stream_from_audio(self, audio: object, *, chunk_words: int = 8) -> AsyncIterator[dict]:
        """Asynchronously yield timestamped transcript increments.

        This calls the underlying transcriber to obtain the full text and
        then yields cumulative partial transcripts in fixed word-sized
        increments. The timestamps are synthetic (chunk index * 0.5s) to
        provide a simple temporal ordering for consumers.

        Args:
            audio: audio buffer accepted by the underlying transcriber.
            chunk_words: approximate number of words per emitted chunk.

        Yields:
            dict with keys `timestamp_s` (float) and `text` (str).
        """
        # Get the full text using whatever the transcriber provides.
        # Support both numpy-array style interfaces and filepath ones.
        try:
            full = None
            if hasattr(self.transcriber, "transcribe"):
                full = self.transcriber.transcribe(audio)
            elif hasattr(self.transcriber, "transcribe_file"):
                full = self.transcriber.transcribe_file(audio)
            else:
                full = str(audio or "")
        except Exception:
            # If transcription fails, yield nothing.
            return

        if not full:
            return

        words = [w for w in full.split() if w]
        if not words:
            return

        total = len(words)
        chunks = max(1, math.ceil(total / float(chunk_words)))

        for i in range(1, chunks + 1):
            end = min(total, i * chunk_words)
            text = " ".join(words[:end]).strip()
            # synthetic timestamp: 0.5s per chunk index
            timestamp = round(i * 0.5, 3)
            yield {"timestamp_s": timestamp, "text": text}

    async def stream_from_file(self, file_path: str, **kwargs) -> AsyncIterator[dict]:
        """Convenience wrapper for file-based transcribers.
        """
        return self.stream_from_audio(file_path, **kwargs)
