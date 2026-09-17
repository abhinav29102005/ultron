"""
tests/test_audio_visualizer.py – Dynamic Audio Level Visualizer Tests
=====================================================================
Tests real-time microphone volume calculation, VU meter block generation,
and terminal integration during voice listening.
"""

from __future__ import annotations

import os
import queue
import numpy as np
import pytest

from utils.cli import CLI, calculate_audio_level


class TestCalculateAudioLevel:
    """Test normalized audio energy level calculation from chunks."""

    def test_none_and_empty(self):
        assert calculate_audio_level(None) == 0.0
        assert calculate_audio_level(np.array([], dtype=np.float32)) == 0.0
        assert calculate_audio_level([]) == 0.0

    def test_all_zeros(self):
        zeros = np.zeros(1024, dtype=np.float32)
        assert calculate_audio_level(zeros) == 0.0

    def test_nan_and_inf(self):
        bad_nan = np.full(1024, np.nan, dtype=np.float32)
        assert calculate_audio_level(bad_nan) == 0.0
        bad_inf = np.full(1024, np.inf, dtype=np.float32)
        assert calculate_audio_level(bad_inf) == 0.0

    def test_scaling_progression(self):
        # Silence / floor
        quiet = np.random.normal(0, 0.001, 1024).astype(np.float32)
        quiet_lvl = calculate_audio_level(quiet)
        assert quiet_lvl == 0.0

        # Whispered / soft speech
        soft = np.random.normal(0, 0.025, 1024).astype(np.float32)
        soft_lvl = calculate_audio_level(soft)
        assert 0.20 <= soft_lvl <= 0.60

        # Normal conversational speech
        normal = np.random.normal(0, 0.09, 1024).astype(np.float32)
        normal_lvl = calculate_audio_level(normal)
        assert 0.50 <= normal_lvl <= 0.85

        # Loud speech
        loud = np.random.normal(0, 0.35, 1024).astype(np.float32)
        loud_lvl = calculate_audio_level(loud)
        assert loud_lvl >= 0.90


class TestCLIListeningBar:
    """Test format, render, and clear behavior of the CLI visualizer bar."""

    def test_format_listening_bar_normal(self):
        CLI._last_level = 0.0
        markup, level = CLI.format_listening_bar(0.5, is_held=False, smooth=False)
        assert "● LISTENING" in markup
        assert "50%" in markup
        assert "Hearing voice..." in markup
        assert level == 0.5

    def test_format_listening_bar_push_to_talk(self):
        CLI._last_level = 0.0
        markup, level = CLI.format_listening_bar(0.0, is_held=True, smooth=False)
        assert "● PUSH-TO-TALK" in markup
        assert "0%" in markup
        assert "Key held, speak..." in markup

    def test_format_listening_bar_smoothing(self):
        CLI._last_level = 0.0
        # First jump up
        _, lvl1 = CLI.format_listening_bar(0.8, smooth=True)
        assert 0.5 <= lvl1 <= 0.8
        # Jump down (decays rather than dropping immediately)
        _, lvl2 = CLI.format_listening_bar(0.0, smooth=True)
        assert lvl2 > 0.0
        assert lvl2 < lvl1

    def test_render_and_clear(self, monkeypatch):
        # Verify render and clear don't crash
        CLI.render_listening_bar(0.5, smooth=False)
        assert CLI._last_level == 0.5
        CLI.clear_listening_bar()
        assert CLI._last_level == 0.0

    def test_env_var_suppression(self, monkeypatch):
        monkeypatch.setenv("ULTRON_AUDIO_BAR", "0")
        CLI._last_level = 0.0
        CLI.render_listening_bar(0.9, smooth=False)
        # Should return early without updating _last_level
        assert CLI._last_level == 0.0


class TestRecorderAudioBarIntegration:
    """Test that Recorder.listen() and HoldToTalkController call the visualizer."""

    def test_recorder_clears_on_timeout(self, monkeypatch):
        from speech.speech_to_text.recorder import Recorder

        cleared = False
        original_clear = CLI.clear_listening_bar

        def fake_clear():
            nonlocal cleared
            cleared = True
            original_clear()

        monkeypatch.setattr(CLI, "clear_listening_bar", fake_clear)

        recorder = Recorder()
        # Fake empty queue, timeout immediately
        res = recorder.listen(timeout=0.01)
        assert res is None
        assert cleared is True

    def test_recorder_renders_on_speech_chunk(self, monkeypatch):
        import threading
        import time
        from speech.speech_to_text.recorder import Recorder

        render_calls = []

        def fake_render(chunk, **kwargs):
            render_calls.append((chunk, kwargs))

        monkeypatch.setattr(CLI, "render_listening_bar", fake_render)

        recorder = Recorder()
        chunk = np.full(1024, 0.15, dtype=np.float32)

        class FakeVAD:
            def __init__(self):
                self.count = 0
            def has_speech(self, audio):
                self.count += 1
                return self.count <= 3

        recorder.vad = FakeVAD()
        recorder.silence_timeout = 0.05

        def _feeder():
            time.sleep(0.02)
            for _ in range(8):
                recorder.audio_queue.put(chunk)
                time.sleep(0.02)

        t = threading.Thread(target=_feeder, daemon=True)
        t.start()

        try:
            recorder.listen(timeout=0.4)
        finally:
            recorder.stop()
        t.join(timeout=0.6)

        assert len(render_calls) > 0
        assert any(kwargs.get("is_speech") is True for _, kwargs in render_calls)

    def test_hold_to_talk_renders_bar(self, monkeypatch):
        from speech.hold_to_talk import HoldToTalkController

        render_calls = []

        def fake_render(chunk, **kwargs):
            render_calls.append((chunk, kwargs))

        monkeypatch.setattr(CLI, "render_listening_bar", fake_render)

        controller = HoldToTalkController(key_name="right_shift")
        chunk = np.full(1024, 0.2, dtype=np.float32)

        held_count = 0

        def fake_is_held():
            nonlocal held_count
            held_count += 1
            if held_count == 1:
                return True  # first wait check
            elif held_count == 2:
                # flush has finished, queue audio chunk
                controller.recorder.audio_queue.put(chunk)
                return True
            return False

        monkeypatch.setattr(controller, "is_held", fake_is_held)

        try:
            res = controller.collect_while_held()
        finally:
            controller.stop_listening()

        assert res is not None
        assert len(render_calls) > 0
        assert all(kwargs.get("is_held") is True for _, kwargs in render_calls)


class TestWhisperAntiHallucination:
    """Test protection against runaway Whisper hallucinations on silence / noise."""

    def test_filter_repetitions_discards_runaway_loops(self):
        from speech.speech_to_text.transcriber import _filter_repetitions

        # The Finnish hallucination observed when microphone hears quiet room noise
        assert _filter_repetitions("Täällä muissa on tullut tullut tullut.") == ""
        # Repetitive English loops
        assert _filter_repetitions("thank you thank you thank you thank you") == ""
        assert _filter_repetitions("word word word") == ""

    def test_filter_repetitions_preserves_valid_speech(self):
        from speech.speech_to_text.transcriber import _filter_repetitions

        assert _filter_repetitions("What is the current system status?") == "What is the current system status?"
        assert _filter_repetitions("Open Chrome and search for Python") == "Open Chrome and search for Python"
        assert _filter_repetitions("") == ""
