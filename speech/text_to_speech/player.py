"""
speech/text_to_speech/player.py – Speech playback with safe barge-in
====================================================================
Playback runs on a worker thread while the interrupt ("stop talking, listen to
me") arrives on the UI thread. The rule that keeps that safe is:

    the thread that opened a stream is the only thread that closes it.

Closing a PortAudio stream while another thread is blocked inside
``stream.write()`` is undefined behaviour, and it took the whole app down.
``stop()`` therefore never closes anything. It raises an epoch counter and
calls ``abort()``, which discards audio already queued in the driver so the
interrupt is heard immediately; the playing thread notices the epoch moved,
breaks out of its loop, and closes its own stream on the way out.
"""

from __future__ import annotations

import threading

import sounddevice as sd

from config.logging_config import get_logger
from speech.speechconfig import OUTPUT_DEVICE

logger = get_logger("tts.player")


class Player:
    def __init__(self) -> None:
        self.output_device = OUTPUT_DEVICE
        self.stream = None
        self.is_playing = False
        # Guards `stream`, `is_playing` and `_epoch` together. Playback holds
        # it only for brief bookkeeping, never across a blocking write, so an
        # interrupt is never left waiting on a chunk.
        self._lock = threading.RLock()
        # Bumped by stop(). A playing thread whose snapshot no longer matches
        # knows it has been superseded and bails out.
        self._epoch = 0

    @property
    def epoch(self) -> int:
        """The current generation. See :meth:`play`'s ``expect_epoch``."""
        with self._lock:
            return self._epoch

    def play(self, audio_chunks, expect_epoch: int | None = None) -> None:
        """Play a stream of chunks. Returns early when stop() is called.

        ``expect_epoch`` guards the gap between deciding to speak and having
        audio to speak: synthesis takes seconds, and an interrupt arriving
        during it would otherwise bump an epoch this call has not read yet,
        so the utterance the user just cancelled would play in full.
        """
        with self._lock:
            if expect_epoch is not None and self._epoch != expect_epoch:
                logger.debug("Playback superseded before it began.")
                return
            epoch = self._epoch
            self.is_playing = True

        stream = None
        try:
            for chunk in audio_chunks:
                with self._lock:
                    if self._epoch != epoch:
                        break
                    if stream is None:
                        stream = sd.OutputStream(
                            samplerate=chunk.sample_rate,
                            channels=chunk.sample_channels,
                            dtype="float32",
                            device=self.output_device,
                        )
                        stream.start()
                        # Publish it so stop() can abort the driver's buffer.
                        self.stream = stream

                # Deliberately outside the lock: this blocks for the length of
                # the chunk, and stop() must not have to wait for it.
                try:
                    stream.write(chunk.audio_float_array)
                except Exception as exc:
                    # An aborted stream raises on the next write. That is the
                    # expected shape of an interrupt, not a failure.
                    logger.debug("Playback write ended: {}", exc)
                    break
        finally:
            # Unpublish BEFORE closing, under the lock. sounddevice's close()
            # calls Pa_CloseStream and only afterwards nulls its pointer, so a
            # concurrent stop() that had already snapshotted this stream would
            # call Pa_AbortStream on memory PortAudio has freed — no Python
            # exception, silent corruption. Clearing first means stop() either
            # aborts a live stream or sees None.
            with self._lock:
                if self.stream is stream:
                    self.stream = None
                # Only clear shared state if we are still the current speaker.
                # A newer play() may already have taken over.
                if self._epoch == epoch:
                    self.is_playing = False

            if stream is not None:
                try:
                    stream.close()
                except Exception as exc:
                    logger.debug("Closing playback stream: {}", exc)

    def stop(self) -> None:
        """Cut playback now. Safe from any thread; never closes the stream."""
        # The abort happens under the lock, paired with play()'s clear-then-
        # close above: the two can no longer interleave onto a freed stream.
        with self._lock:
            self._epoch += 1
            self.is_playing = False
            stream = self.stream

            if stream is not None:
                try:
                    # abort() drops audio already handed to the driver, so
                    # speech stops mid-word rather than finishing the buffer.
                    stream.abort()
                except Exception as exc:
                    logger.debug("Aborting playback stream: {}", exc)
