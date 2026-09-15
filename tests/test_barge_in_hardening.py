"""
tests/test_barge_in_hardening.py – Regressions from adversarial review
======================================================================
The first pass fixed the crash but left the microphone handover racy and the
interrupt incomplete. Every case here was reproduced before the fix; two of
them (S2, S4) were regressions introduced by the fix itself.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time

import numpy as np
import pytest


# --------------------------------------------------------------------- fakes
class FakeStream:
    def __init__(self, open_delay=0.0, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.aborted = False
        self.closing = False
        self.abort_during_close = False
        self._open_delay = open_delay

    def start(self):
        if self._open_delay:
            time.sleep(self._open_delay)

    def write(self, data):
        if self.aborted or self.closed:
            raise RuntimeError("stream is gone")
        time.sleep(0.002)

    def abort(self):
        if self.closing or self.closed:
            # Pa_AbortStream on a pointer Pa_CloseStream has already freed.
            self.abort_during_close = True
        self.aborted = True

    def stop(self):
        pass

    def close(self):
        self.closing = True
        time.sleep(0.003)  # Pa_CloseStream is not instantaneous
        self.closing = False
        self.closed = True


class FakeChunk:
    sample_rate = 22050
    sample_channels = 1

    def __init__(self):
        self.audio_float_array = np.zeros(64, dtype="float32")


class FakeSD:
    def __init__(self, open_delay=0.0):
        self.streams = []
        self._open_delay = open_delay

    def _make(self, **kwargs):
        stream = FakeStream(open_delay=self._open_delay, **kwargs)
        self.streams.append(stream)
        return stream

    OutputStream = _make
    InputStream = _make


@pytest.fixture(autouse=True)
def _release_mic():
    """No test may leave the shared microphone lock held."""
    yield
    from speech.audio_bus import MIC

    if MIC.owner is not None:
        MIC.release(force=True)


# ============================================== S3: abort during close
class TestAbortNeverRacesClose:
    """sounddevice's close() frees the PortAudio pointer before nulling it, so
    a concurrent abort() writes to freed memory — silently, with no Python
    exception."""

    def test_stop_never_aborts_a_stream_being_closed(self, monkeypatch):
        from speech.text_to_speech import player as player_module
        from speech.text_to_speech.player import Player

        fake = FakeSD()
        monkeypatch.setattr(player_module, "sd", fake)
        instance = Player()

        for _ in range(60):
            thread = threading.Thread(
                target=lambda: instance.play(iter([FakeChunk() for _ in range(20)])),
                daemon=True,
            )
            thread.start()
            time.sleep(0.004)
            instance.stop()
            thread.join(timeout=5)

        offenders = [s for s in fake.streams if s.abort_during_close]
        assert not offenders, (
            f"{len(offenders)} of {len(fake.streams)} streams were aborted while "
            "closing — a use-after-free in PortAudio"
        )


# ================================== S6: interrupt during synthesis
class TestInterruptDuringSynthesis:
    def test_an_interrupt_inside_generate_cancels_that_utterance(self, monkeypatch):
        """Synthesis takes seconds; a stop arriving inside it must count."""
        from speech.text_to_speech import player as player_module
        from speech.text_to_speech import tts_pipeline

        fake = FakeSD()
        monkeypatch.setattr(player_module, "sd", fake)

        player = tts_pipeline.get_player()
        generating = threading.Event()

        def _slow_generate(text):
            generating.set()
            time.sleep(0.3)  # piper doing its work
            return iter([FakeChunk() for _ in range(20)])

        monkeypatch.setattr(
            tts_pipeline,
            "_get_speaker",
            lambda: type("S", (), {"generate": staticmethod(_slow_generate)})(),
        )

        thread = threading.Thread(
            target=lambda: tts_pipeline.play_audio("a long answer"), daemon=True
        )
        thread.start()
        generating.wait(timeout=5)
        time.sleep(0.02)

        tts_pipeline.stop_audio()  # lands while generate() is still running
        thread.join(timeout=5)

        assert fake.streams == [], (
            "the cancelled utterance still opened an output stream and played"
        )


# ========================================= S1: the sticky wake-word stop
class TestWakeWordStopIsSticky:
    def _detector(self):
        from speech.wake_word.detector import WakeWordDetector

        detector = WakeWordDetector.__new__(WakeWordDetector)
        detector._porcupine = None
        detector._oww = None
        detector._audio_queue = queue.Queue(maxsize=64)
        detector._stop_event = threading.Event()
        detector._closed_event = threading.Event()
        detector._closed_event.set()
        detector._engine = "porcupine"
        return detector

    def test_a_stop_that_arrives_before_detect_is_not_swallowed(self):
        """detect() used to clear the stop flag on entry, erasing it."""
        detector = self._detector()
        detector._detect_porcupine = lambda: pytest.fail(
            "detect() opened the device despite a pending stop"
        )

        detector.stop()
        assert detector.detect() is False

    def test_the_stop_stays_in_force_until_resume(self):
        detector = self._detector()
        calls = []
        detector._detect_porcupine = lambda: calls.append(1) or False

        detector.stop()
        detector.detect()
        detector.detect()
        assert calls == [], "a stopped detector kept opening the microphone"

        detector.resume()
        detector.detect()
        assert calls == [1], "resume() did not lift the stop"

    def test_wait_closed_is_true_when_detect_declines_to_run(self):
        detector = self._detector()
        detector.stop()
        detector.detect()
        assert detector.wait_closed(timeout=0.1) is True


# ============================ S2: the pipeline must not own the mic
class TestSpeechPipelineDoesNotHoldTheMicrophone:
    def test_constructing_it_leaves_the_device_free(self, monkeypatch):
        """Holding the mic for the process lifetime made run.py's wake-word
        mode spin at 5 Hz and never hear anything."""
        import speech.speech_to_text.stt_pipeline as pipeline_module
        from speech.audio_bus import MIC

        started = []

        class FakeRecorder:
            def start(self):
                started.append(1)

            def stop(self):
                pass

        monkeypatch.setattr(pipeline_module, "Recorder", FakeRecorder)
        monkeypatch.setattr(pipeline_module, "Transcriber", lambda: object())

        pipeline_module.SpeechPipeline()

        assert started == [], "the pipeline opened the microphone in __init__"
        assert MIC.owner is None
        token = MIC.acquire("wake_word", timeout=0.5)
        MIC.release(token)


# ================================== S4: start/stop must not interleave
class TestRecorderStartStopRace:
    def test_a_stop_during_a_slow_start_never_strands_an_open_stream(
        self, monkeypatch
    ):
        """stop() used to see stream=None, skip the close, and release the
        microphone anyway — leaving an open stream nothing owned."""
        from speech.audio_bus import MIC
        from speech.speech_to_text import recorder as rec_module

        monkeypatch.setattr(rec_module, "VAD", lambda: object())
        fake = FakeSD(open_delay=0.05)
        monkeypatch.setattr(rec_module, "sd", fake)

        instance = rec_module.Recorder()

        for _ in range(15):
            starter = threading.Thread(target=instance.start, daemon=True)
            starter.start()
            time.sleep(0.01)  # inside the slow open
            instance.stop()
            starter.join(timeout=5)
            instance.stop()

            open_streams = [s for s in fake.streams if not s.closed]
            assert not open_streams or MIC.owner == "recorder", (
                "a stream is open but the microphone was released — two "
                "streams on one device is now possible"
            )
            if MIC.owner == "recorder":
                instance.stop()

        assert MIC.owner is None


# ============================== S5: listen() must not wait for ever
class TestListenTimesOut:
    def test_silence_returns_none_instead_of_hanging(self, monkeypatch):
        from speech.speech_to_text import recorder as rec_module

        monkeypatch.setattr(rec_module, "VAD", lambda: object())
        monkeypatch.setattr(rec_module, "sd", FakeSD())

        instance = rec_module.Recorder()

        began = time.time()
        result = instance.listen(timeout=0.3)
        elapsed = time.time() - began

        assert result is None
        assert elapsed < 3.0, f"listen() blocked for {elapsed:.1f}s on silence"

    def test_the_microphone_is_released_after_a_timeout(self, monkeypatch):
        from speech.audio_bus import MIC
        from speech.speech_to_text import recorder as rec_module

        monkeypatch.setattr(rec_module, "VAD", lambda: object())
        monkeypatch.setattr(rec_module, "sd", FakeSD())

        instance = rec_module.Recorder()
        instance.start()
        try:
            assert instance.listen(timeout=0.2) is None
        finally:
            instance.stop()

        assert MIC.owner is None, "a silent capture kept the device for ever"


# ======================================= S8: unowned release is refused
class TestMicLockOwnership:
    def test_a_release_from_a_foreign_thread_is_ignored(self):
        """threading.Lock is not owner-checked; an unowned release would hand
        the device away while the real owner still has a stream open."""
        from speech.audio_bus import MicLock

        lock = MicLock()
        acquired = threading.Event()
        done = threading.Event()

        def _own():
            token = lock.acquire("wake_word", timeout=2.0)
            acquired.set()
            done.wait(timeout=5)
            lock.release(token)

        thread = threading.Thread(target=_own, daemon=True)
        thread.start()
        acquired.wait(timeout=5)

        lock.release()  # a stray release, with no token to show for it

        assert lock.owner == "wake_word", "a stray release gave the device away"

        done.set()
        thread.join(timeout=5)
        assert lock.owner is None


# ========================= S6/S7/S12: interrupt, state, and speech tasks
class TestInterruptAndState:
    def _assistant(self, monkeypatch):
        from core.assistant import Assistant
        from core.state import AssistantState

        assistant = Assistant.__new__(Assistant)
        assistant._current_turn = None
        assistant._speech_tasks = set()
        assistant._memory_tasks = set()
        monkeypatch.setattr(
            "speech.text_to_speech.tts_pipeline.stop_audio", lambda: None
        )
        return assistant, AssistantState

    @pytest.mark.asyncio
    async def test_interrupt_cancels_speech_already_dispatched(self, monkeypatch):
        """Speech outlives its turn, so cancelling the turn is not enough."""
        assistant, _ = self._assistant(monkeypatch)

        spoke = []

        async def _speaking():
            await asyncio.sleep(5)
            spoke.append("too late")

        task = asyncio.ensure_future(_speaking())
        assistant._speech_tasks.add(task)

        assistant.interrupt()
        await asyncio.sleep(0)
        await asyncio.gather(task, return_exceptions=True)

        assert task.cancelled()
        assert spoke == []

    @pytest.mark.asyncio
    async def test_a_superseded_turn_does_not_publish_idle_over_the_new_one(
        self, monkeypatch
    ):
        """The orb sat on IDLE for the whole duration of the real work."""
        from core.event_bus import UserInputEvent

        assistant, AssistantState = self._assistant(monkeypatch)
        states = []

        async def _record(state):
            states.append(state)

        assistant._set_state = _record

        first_started = asyncio.Event()

        async def _turn(event):
            await _record(AssistantState.THINKING)
            if event.text == "first":
                first_started.set()
                await asyncio.sleep(30)

        assistant._process_turn = _turn

        first = asyncio.ensure_future(
            assistant._handle_user_input(UserInputEvent(text="first", source="voice"))
        )
        await asyncio.wait_for(first_started.wait(), timeout=5)

        await assistant._handle_user_input(
            UserInputEvent(text="second", source="voice")
        )
        await asyncio.wait_for(first, timeout=5)

        assert states[-1] != AssistantState.IDLE or states.count(
            AssistantState.IDLE
        ) <= 1, f"a stale IDLE landed after the new turn: {states}"
