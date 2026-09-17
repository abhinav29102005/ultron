"""
speech/hold_to_talk.py – Push-to-Talk Controller (Whisperflow style)
===============================================================
Listens to a configured keyboard key: records audio while held,
stops and returns audio when released.
"""

from __future__ import annotations

import threading
import time
from collections import deque

try:
    from pynput import keyboard
except ImportError:  # pragma: no cover
    keyboard = None

from speech.speechconfig import BLOCK_SIZE, SAMPLE_RATE
from speech.speech_to_text.recorder import Recorder


class HoldToTalkController:
    """Controls recording via a keyboard hold event."""

    def __init__(self, key_name: str = "right_shift") -> None:
        self.key_name = key_name.lower()
        self.recorder = Recorder()
        self._held = threading.Event()
        self._listener = None
        self._audio_buffer = []
        self._recording_active = False

    def _on_press(self, key) -> bool:
        try:
            key_str = str(key).lower()
            target = self.key_name
            # Match simple names like shift_r, alt, ctrl_l, space, f1
            if target == "right_shift":
                target = "shift_r"
            elif target == "left_shift":
                target = "shift_l"
            # Try to match by normalized name
            if (key_str == target or
                target in key_str or
                key_str in target):
                if not self._held.is_set():
                    self._held.set()
                    self._audio_buffer.clear()
                    self.recorder.rolling_buffer.clear()
                    self.recorder.speech_buffer.clear()
                    self.recorder.is_recording = False
                    self.recorder.start()
                    return True
        except Exception:
            pass
        return True  # keep listener alive

    def _on_release(self, key) -> bool:
        try:
            target = self.key_name
            key_str = str(key).lower()
            if target == "right_shift":
                target = "shift_r"
            elif target == "left_shift":
                target = "shift_l"
            if (key_str == target or target in key_str or key_str in target):
                if self._held.is_set():
                    self._held.clear()
        except Exception:
            pass
        return True

    def start_listening(self) -> None:
        if keyboard is None:
            raise ImportError("pynput is required for hold-to-talk mode.")
        self._held.clear()
        self.recorder.start()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.start()

    def stop_listening(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._held.clear()
        self.recorder.stop()

    def is_held(self) -> bool:
        return self._held.is_set()

    def collect_while_held(self) -> bytes | None:
        """Record audio chunks while the key is held, return concatenated array."""
        from utils.cli import CLI

        # Ensure listener is running (start only once)
        if self._listener is None:
            self.start_listening()
        try:
            # Wait briefly for press to register stream start
            while not self.is_held():
                time.sleep(0.01)
            # Drain pre-press audio. flush() drains through the queue's own
            # API; reaching into .queue mutates the underlying deque without
            # holding its mutex, racing the PortAudio callback.
            self.recorder.flush()
            # Collect chunks until released
            chunks = []
            max_duration = 30.0  # safety cap
            start_time = time.time()
            CLI.render_listening_bar(0.0, is_held=True, status="Key held, speak...")
            while self.is_held() and (time.time() - start_time) < max_duration:
                try:
                    chunk = self.recorder.audio_queue.get(timeout=0.05)
                    chunks.append(chunk.copy())
                    CLI.render_listening_bar(chunk.flatten(), is_held=True)
                except Exception:
                    continue
            CLI.clear_listening_bar()
            # After release, gather remaining speech via VAD/silence if any
            if chunks:
                import numpy as np
                audio = np.concatenate([c.flatten() for c in chunks])
                return audio
            return None
        finally:
            CLI.clear_listening_bar()
