"""
speech/speech_to_text/recorder.py – Microphone capture with VAD segmentation

The PortAudio callback runs whether or not anyone is listening. It used to
push into an unbounded queue that only ``listen()`` drained, so every second
FRIDAY spent thinking or speaking added roughly sixteen stale blocks. The next
``listen()`` then ran the Silero VAD once per stale block before it reached
live audio, which is what made the assistant appear to hang after an interrupt.

The queue is now bounded and drops its oldest block when full, and ``listen()``
flushes before it starts, so a capture always begins on live audio no matter
how long the stream sat idle.
"""

from collections import deque
import os
import queue
import threading
import time

import numpy as np
import sounddevice as sd

from config.logging_config import get_logger
from speech.audio_bus import MIC
from speech.speechconfig import (
    SAMPLE_RATE,
    CHANNELS,
    BLOCK_SIZE,
    INPUT_DEVICE,
    SILENCE_TIMEOUT,
)
from speech.speech_to_text.vad import VAD
from utils.cli import CLI

logger = get_logger("stt.recorder")

#: Roughly four seconds at 16 kHz / 1024-sample blocks. Large enough that a
#: brief scheduling hiccup loses nothing, small enough that a backlog can
#: never grow into the multi-second VAD stall described above.
MAX_QUEUED_BLOCKS = int(os.getenv("STT_MAX_QUEUED_BLOCKS", "64"))

#: How long listen() waits for speech to *begin* before giving up. Once the
#: user starts talking, SILENCE_TIMEOUT decides when they have finished, and
#: this no longer applies — a long answer is not a timeout.
SILENCE_LISTEN_TIMEOUT = float(os.getenv("STT_LISTEN_TIMEOUT", "15.0"))


class Recorder:
    def __init__(self):
        self.audio_queue = queue.Queue(maxsize=MAX_QUEUED_BLOCKS)
        self.stream = None
        self.vad = VAD()
        rolling_maxlen = int(os.getenv("STT_ROLLING_BUFFER_BLOCKS", "5"))
        self.rolling_buffer = deque(maxlen=rolling_maxlen)
        self.speech_buffer = []
        self.is_recording = False
        self.last_speech_time = None
        self.silence_timeout = SILENCE_TIMEOUT
        self._dropped_blocks = 0
        self._mic_held = False
        self._mic_token = None
        # Guards stream/_mic_held as one unit. start() and stop() are called
        # from different threads (Qt worker, pynput listener, wake-word loop).
        self._state_lock = threading.RLock()

    def _callback(self, indata, frames, time, status):
        if status:
            # Overflow here means we were too slow to drain, which the bounded
            # queue below handles. Logged rather than printed so it cannot
            # spam a user-facing console mid-conversation.
            logger.debug("Input stream status: {}", status)
        try:
            self.audio_queue.put_nowait(indata.copy())
        except queue.Full:
            # Drop the oldest block, not the newest: the user's most recent
            # speech matters more than what they said four seconds ago.
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(indata.copy())
            except (queue.Empty, queue.Full):
                pass
            self._dropped_blocks += 1

    def flush(self):
        """Discard everything captured so far and reset segmentation state."""
        while True:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.rolling_buffer.clear()
        self.speech_buffer.clear()
        self.is_recording = False
        self.last_speech_time = None

    def start(self):
        """Open the input stream. Safe to call when already open."""
        # Serialised against stop(): opening the device takes long enough that
        # a stop arriving mid-way used to see stream=None, skip the close, and
        # release the microphone anyway — leaving an open stream that nothing
        # owned, which is precisely the two-streams-on-one-device condition.
        with self._state_lock:
            if self.stream is not None:
                return

            self._mic_token = MIC.acquire("recorder")
            self._mic_held = True
            try:
                stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    blocksize=BLOCK_SIZE,
                    device=INPUT_DEVICE,
                    callback=self._callback,
                    dtype="float32",
                )
                stream.start()
            except Exception:
                self._mic_held = False
                MIC.release(self._mic_token)
                self._mic_token = None
                raise
            self.stream = stream

    def stop(self):
        """Close the input stream. Safe to call when already closed."""
        with self._state_lock:
            stream, self.stream = self.stream, None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:
                    logger.debug("Closing input stream: {}", exc)

            if self._dropped_blocks:
                logger.debug("Dropped {} stale audio blocks.", self._dropped_blocks)
                self._dropped_blocks = 0

            if self._mic_held:
                self._mic_held = False
                MIC.release(self._mic_token)
                self._mic_token = None

    def listen(self, timeout: float | None = None):
        """Capture one utterance. Returns None if nobody speaks in time.

        The timeout is not optional in practice. Without it a wake-word false
        positive, a muted microphone or a dead device parks this call for
        ever — holding the microphone lock, leaving the orb stuck on
        LISTENING, and taking the assistant permanently deaf with no way back
        but a restart.
        """
        if timeout is None:
            timeout = SILENCE_LISTEN_TIMEOUT

        # Start from live audio. Anything queued while FRIDAY was thinking or
        # speaking is stale by definition and only costs VAD time.
        self.flush()

        deadline = time.time() + timeout

        while True:
            if not self.is_recording and time.time() > deadline:
                logger.debug("Nothing was said within %.1fs; giving up.", timeout)
                return None

            try:
                chunk = self.audio_queue.get(timeout=0.25).flatten()
            except queue.Empty:
                continue

            self.rolling_buffer.append(chunk)
            if len(self.rolling_buffer) < self.rolling_buffer.maxlen:
                continue

            audio = np.concatenate(self.rolling_buffer)
            speech = self.vad.has_speech(audio)

            if speech:
                self.last_speech_time = time.time()
                if not self.is_recording:
                    CLI.print_listening()
                    self.is_recording = True
                    # Save the audio that happened BEFORE detection
                    self.speech_buffer = list(self.rolling_buffer)
                else:
                    self.speech_buffer.append(chunk)

            elif self.is_recording:
                self.speech_buffer.append(chunk)
                if time.time() - self.last_speech_time > self.silence_timeout:
                    CLI.print_processing()
                    audio = np.concatenate(self.speech_buffer)
                    self.speech_buffer.clear()
                    self.rolling_buffer.clear()
                    self.is_recording = False
                    return audio
