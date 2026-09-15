"""
tests/test_barge_in.py – Interrupting ULTRON mid-sentence
=========================================================
Covers the five defects that together made a barge-in print a PortAudio input
overflow, hang the assistant for seconds, and then kill it. See
docs/superpowers/specs/2026-08-23-barge-in-vision-file-control-design.md.

sounddevice is faked throughout: the point is the ownership rules around the
streams, not PortAudio itself.
"""

from __future__ import annotations

import queue
import threading
import time

import numpy as np
import pytest


# --------------------------------------------------------------------- fakes
class FakeStream:
    """Records the thread that opened it and the thread that closed it."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.closed = False
        self.aborted = False
        self.opened_by = threading.get_ident()
        self.closed_by: int | None = None
        self.writes: list = []
        self.write_delay = 0.0

    def start(self):
        self.started = True

    def write(self, data):
        if self.aborted:
            raise RuntimeError("stream aborted")
        if self.closed:
            raise RuntimeError("write to a closed stream")
        if self.write_delay:
            time.sleep(self.write_delay)
        self.writes.append(data)

    def abort(self):
        self.aborted = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True
        self.closed_by = threading.get_ident()


class FakeChunk:
    sample_rate = 22050
    sample_channels = 1

    def __init__(self, value: float = 0.0):
        self.audio_float_array = np.full(64, value, dtype="float32")


class FakeSD:
    def __init__(self):
        self.streams: list[FakeStream] = []

    def OutputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream

    def InputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


@pytest.fixture
def fake_sd(monkeypatch):
    from speech.text_to_speech import player as player_module

    fake = FakeSD()
    monkeypatch.setattr(player_module, "sd", fake)
    return fake


# ============================================================ C1 + C2: player
class TestPlayerBargeIn:
    """A stream must only ever be closed by the thread that opened it.

    Closing one while another thread is blocked inside write() is undefined
    behaviour in PortAudio, and was the hard crash on interrupt.
    """

    def test_stop_does_not_close_the_stream_itself(self, fake_sd):
        from speech.text_to_speech.player import Player

        player = Player()
        chunks = [FakeChunk() for _ in range(4)]

        done = threading.Event()

        def _play():
            player.play(iter(chunks))
            done.set()

        thread = threading.Thread(target=_play)
        thread.start()

        # Let playback open its stream, then interrupt from this thread.
        for _ in range(200):
            if fake_sd.streams:
                break
            time.sleep(0.005)

        assert fake_sd.streams, "playback never opened a stream"
        stream = fake_sd.streams[0]

        player.stop()
        assert done.wait(timeout=5), "play() did not return after stop()"
        thread.join(timeout=5)

        assert stream.closed, "the playing thread must close its own stream"
        assert stream.closed_by == thread.ident, (
            "the stream was closed by the interrupting thread, which is the "
            "crash this fix exists to prevent"
        )

    def test_stop_aborts_so_the_buffered_tail_is_not_heard(self, fake_sd):
        from speech.text_to_speech.player import Player

        player = Player()
        started = threading.Event()

        def _chunks():
            # Paced so playback is genuinely still in flight when the
            # interrupt lands; an unpaced generator finishes instantly and
            # the test would prove nothing.
            for i in range(200):
                started.set()
                time.sleep(0.002)
                yield FakeChunk(i)

        thread = threading.Thread(target=lambda: player.play(_chunks()), daemon=True)
        thread.start()
        started.wait(timeout=5)
        time.sleep(0.02)

        assert player.is_playing, "playback finished before the interrupt landed"
        player.stop()
        thread.join(timeout=5)

        assert not thread.is_alive()
        assert fake_sd.streams[0].aborted, "stop() must abort the driver buffer"
        assert len(fake_sd.streams[0].writes) < 200, "playback ran to completion"

    def test_play_returns_promptly_after_stop(self, fake_sd):
        from speech.text_to_speech.player import Player

        player = Player()
        # Long chunks: a stop that only flipped a flag checked between whole
        # utterances would blow this deadline.
        chunks = [FakeChunk() for _ in range(200)]

        thread = threading.Thread(target=lambda: player.play(iter(chunks)))
        thread.start()
        time.sleep(0.02)

        began = time.time()
        player.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert time.time() - began < 2.0

    def test_is_playing_is_false_after_stop(self, fake_sd):
        from speech.text_to_speech.player import Player

        player = Player()
        thread = threading.Thread(
            target=lambda: player.play(iter([FakeChunk() for _ in range(100)]))
        )
        thread.start()
        time.sleep(0.02)
        player.stop()
        thread.join(timeout=5)
        assert player.is_playing is False
        assert player.stream is None

    def test_repeated_interrupts_leave_no_stream_open(self, fake_sd):
        """The real usage pattern: speak, interrupt, speak, interrupt..."""
        from speech.text_to_speech.player import Player

        player = Player()
        for _ in range(25):
            thread = threading.Thread(
                target=lambda: player.play(iter([FakeChunk() for _ in range(40)]))
            )
            thread.start()
            time.sleep(0.002)
            player.stop()
            thread.join(timeout=5)
            assert not thread.is_alive()

        assert all(s.closed for s in fake_sd.streams), "a stream was leaked"
        assert player.stream is None

    def test_stop_before_any_play_is_harmless(self, fake_sd):
        from speech.text_to_speech.player import Player

        player = Player()
        player.stop()
        player.stop()
        assert player.is_playing is False

    def test_stop_with_no_chunks_opens_no_stream(self, fake_sd):
        from speech.text_to_speech.player import Player

        player = Player()
        player.play(iter([]))
        assert fake_sd.streams == []
        assert player.is_playing is False


class TestTTSPipelineKeepsOnePlayer:
    """Rebinding the global player made stop_audio() silently ineffective."""

    def test_player_identity_is_stable_across_calls(self, monkeypatch):
        from speech.text_to_speech import tts_pipeline

        before = tts_pipeline.get_player()
        tts_pipeline.stop_audio()
        assert tts_pipeline.get_player() is before

        monkeypatch.setattr(
            tts_pipeline, "_get_speaker", lambda: type("S", (), {"generate": staticmethod(lambda t: iter([]))})()
        )
        tts_pipeline.play_audio("hello")
        assert tts_pipeline.get_player() is before, (
            "play_audio rebound the shared player; a later stop_audio would "
            "act on an object the speaking thread no longer uses"
        )


# ================================================================ C3 + C4: recorder
class FakeVAD:
    def __init__(self, speech=False):
        self.speech = speech
        self.calls = 0

    def has_speech(self, audio):
        self.calls += 1
        return self.speech


@pytest.fixture
def recorder(monkeypatch):
    """A Recorder with the VAD and sounddevice stubbed out."""
    from speech.speech_to_text import recorder as rec_module

    monkeypatch.setattr(rec_module, "VAD", lambda: FakeVAD())
    fake = FakeSD()
    monkeypatch.setattr(rec_module, "sd", fake)
    instance = rec_module.Recorder()
    instance._fake_sd = fake
    yield instance
    instance.stop()


class TestRecorderQueueIsBounded:
    """An unbounded queue meant every idle second added stale VAD work."""

    def test_queue_never_exceeds_the_cap(self, recorder):
        from speech.speech_to_text.recorder import MAX_QUEUED_BLOCKS

        block = np.zeros((1024, 1), dtype="float32")
        for _ in range(MAX_QUEUED_BLOCKS * 5):
            recorder._callback(block, 1024, None, None)

        assert recorder.audio_queue.qsize() <= MAX_QUEUED_BLOCKS

    def test_oldest_block_is_dropped_not_the_newest(self, recorder):
        from speech.speech_to_text.recorder import MAX_QUEUED_BLOCKS

        for i in range(MAX_QUEUED_BLOCKS + 10):
            recorder._callback(np.full((4, 1), i, dtype="float32"), 4, None, None)

        newest = None
        while True:
            try:
                newest = recorder.audio_queue.get_nowait()
            except queue.Empty:
                break

        assert newest is not None
        assert float(newest[0][0]) == float(MAX_QUEUED_BLOCKS + 9), (
            "the newest speech was dropped; the user's latest words matter most"
        )

    def test_flush_empties_queue_and_resets_segmentation(self, recorder):
        for _ in range(10):
            recorder._callback(np.zeros((4, 1), dtype="float32"), 4, None, None)
        recorder.rolling_buffer.append(np.zeros(4, dtype="float32"))
        recorder.speech_buffer.append(np.zeros(4, dtype="float32"))
        recorder.is_recording = True

        recorder.flush()

        assert recorder.audio_queue.empty()
        assert len(recorder.rolling_buffer) == 0
        assert recorder.speech_buffer == []
        assert recorder.is_recording is False

    def test_listen_flushes_stale_audio_before_running_the_vad(self, recorder, monkeypatch):
        """The backlog must never reach the VAD: that was the multi-second lag."""
        vad = FakeVAD(speech=False)
        recorder.vad = vad

        for _ in range(60):
            recorder._callback(np.zeros((1024, 1), dtype="float32"), 1024, None, None)

        result: list = []

        def _listen():
            # Nothing more is ever queued, so listen() blocks on an empty
            # queue -- which is exactly the proof that it discarded the stale
            # blocks instead of grinding the VAD over them.
            try:
                result.append(recorder.listen())
            except Exception:
                pass

        thread = threading.Thread(target=_listen, daemon=True)
        thread.start()
        time.sleep(0.3)

        assert vad.calls == 0, f"VAD ran {vad.calls} times over stale audio"
        assert result == []


class TestRecorderStreamLifecycle:
    def test_start_twice_opens_one_stream(self, recorder):
        recorder.start()
        recorder.start()
        assert len(recorder._fake_sd.streams) == 1

    def test_stop_twice_does_not_raise(self, recorder):
        recorder.start()
        recorder.stop()
        recorder.stop()
        assert recorder.stream is None

    def test_stop_clears_the_handle(self, recorder):
        recorder.start()
        stream = recorder.stream
        recorder.stop()
        assert stream.closed
        assert recorder.stream is None

    def test_restart_after_stop_works(self, recorder):
        recorder.start()
        recorder.stop()
        recorder.start()
        assert recorder.stream is not None
        assert len(recorder._fake_sd.streams) == 2

    def test_failed_start_releases_the_microphone(self, recorder, monkeypatch):
        from speech.audio_bus import MIC
        from speech.speech_to_text import recorder as rec_module

        def _boom(**kwargs):
            raise RuntimeError("device busy")

        monkeypatch.setattr(rec_module.sd, "InputStream", _boom)

        with pytest.raises(RuntimeError):
            recorder.start()

        # A start that raised while holding the lock would deadlock every
        # later listen.
        assert MIC.owner is None
        token = MIC.acquire("test", timeout=0.5)
        MIC.release(token)


# =============================================================== C5: mic handover
class TestMicLock:
    def test_second_owner_is_refused_rather_than_opening_a_stream(self):
        from speech.audio_bus import MicBusy, MicLock

        lock = MicLock()
        acquired = threading.Event()
        release = threading.Event()

        def _hold():
            with lock.hold("first"):
                acquired.set()
                release.wait(timeout=5)

        thread = threading.Thread(target=_hold)
        thread.start()
        acquired.wait(timeout=5)

        with pytest.raises(MicBusy):
            lock.acquire("second", timeout=0.2)

        release.set()
        thread.join(timeout=5)

        token = lock.acquire("second", timeout=1.0)
        assert lock.owner == "second"
        lock.release(token)

    def test_hold_releases_on_exception(self):
        from speech.audio_bus import MicLock

        lock = MicLock()
        with pytest.raises(ValueError):
            with lock.hold("first"):
                raise ValueError("boom")
        assert lock.owner is None
        token = lock.acquire("second", timeout=0.5)
        lock.release(token)


class TestWakeWordHandover:
    """stop() returns before the stream closes; wait_closed() is the handshake."""

    def _detector(self):
        from speech.wake_word.detector import WakeWordDetector

        detector = WakeWordDetector.__new__(WakeWordDetector)
        detector._porcupine = None
        detector._oww = None
        detector._audio_queue = queue.Queue(maxsize=64)
        detector._stop_event = threading.Event()
        detector._closed_event = threading.Event()
        detector._closed_event.set()
        detector._engine = "none"
        return detector

    def test_wait_closed_blocks_until_detect_finishes(self):
        detector = self._detector()
        detector._engine = "porcupine"

        in_loop = threading.Event()
        may_finish = threading.Event()

        def _fake_detect_porcupine():
            in_loop.set()
            may_finish.wait(timeout=5)
            return False

        detector._detect_porcupine = _fake_detect_porcupine

        thread = threading.Thread(target=detector.detect)
        thread.start()
        in_loop.wait(timeout=5)

        assert detector.wait_closed(timeout=0.2) is False, (
            "wait_closed returned while the detector still held the device"
        )

        detector.stop()
        may_finish.set()
        assert detector.wait_closed(timeout=5) is True
        thread.join(timeout=5)

    def test_detect_stands_down_when_the_recorder_holds_the_mic(self):
        from speech.audio_bus import MIC

        detector = self._detector()
        detector._engine = "porcupine"
        detector._detect_porcupine = lambda: pytest.fail(
            "opened a second input stream while the recorder held the device"
        )

        token = MIC.acquire("recorder", timeout=1.0)
        try:
            assert detector.detect() is False
        finally:
            MIC.release(token)

    def test_callback_drops_oldest_when_full(self):
        detector = self._detector()
        for i in range(200):
            detector._callback(np.full((4, 1), i, dtype="int16"), 4, None, None)
        assert detector._audio_queue.qsize() <= 64


# ============================================================ turn cancellation
class TestTurnCancellation:
    """An interrupted question must not answer itself five seconds later."""

    @pytest.mark.asyncio
    async def test_interrupt_cancels_the_in_flight_turn(self, monkeypatch):
        import asyncio

        from core.assistant import Assistant
        from core.event_bus import UserInputEvent

        assistant = Assistant.__new__(Assistant)
        assistant._current_turn = None
        assistant._speech_tasks = set()
        assistant._memory_tasks = set()

        spoke: list[str] = []
        started = asyncio.Event()

        async def _slow_turn(event):
            started.set()
            await asyncio.sleep(30)
            spoke.append("too late")

        assistant._process_turn = _slow_turn
        assistant._set_state = lambda state: asyncio.sleep(0)

        monkeypatch.setattr(
            "speech.text_to_speech.tts_pipeline.stop_audio", lambda: None
        )

        handler = asyncio.ensure_future(
            assistant._handle_user_input(UserInputEvent(text="hi", source="voice"))
        )
        await asyncio.wait_for(started.wait(), timeout=5)

        assistant.interrupt()
        await asyncio.wait_for(handler, timeout=5)

        assert spoke == [], "the abandoned turn still produced a response"
        assert assistant._current_turn is None

    @pytest.mark.asyncio
    async def test_cancellation_does_not_escape_into_the_event_bus(self, monkeypatch):
        """Other subscribers must survive one turn being abandoned."""
        import asyncio

        from core.assistant import Assistant
        from core.event_bus import UserInputEvent

        assistant = Assistant.__new__(Assistant)
        assistant._current_turn = None
        assistant._speech_tasks = set()
        assistant._memory_tasks = set()

        async def _turn(event):
            raise asyncio.CancelledError

        assistant._process_turn = _turn
        assistant._set_state = lambda state: asyncio.sleep(0)
        monkeypatch.setattr(
            "speech.text_to_speech.tts_pipeline.stop_audio", lambda: None
        )

        # Must return normally rather than propagating CancelledError.
        await assistant._handle_user_input(UserInputEvent(text="hi", source="voice"))

    @pytest.mark.asyncio
    async def test_new_input_supersedes_the_previous_turn(self, monkeypatch):
        import asyncio

        from core.assistant import Assistant
        from core.event_bus import UserInputEvent

        assistant = Assistant.__new__(Assistant)
        assistant._current_turn = None
        assistant._speech_tasks = set()
        assistant._memory_tasks = set()

        finished: list[str] = []
        first_started = asyncio.Event()

        async def _turn(event):
            if event.text == "first":
                first_started.set()
                await asyncio.sleep(30)
            finished.append(event.text)

        assistant._process_turn = _turn
        assistant._set_state = lambda state: asyncio.sleep(0)
        monkeypatch.setattr(
            "speech.text_to_speech.tts_pipeline.stop_audio", lambda: None
        )

        first = asyncio.ensure_future(
            assistant._handle_user_input(UserInputEvent(text="first", source="voice"))
        )
        await asyncio.wait_for(first_started.wait(), timeout=5)

        await assistant._handle_user_input(
            UserInputEvent(text="second", source="voice")
        )
        await asyncio.wait_for(first, timeout=5)

        assert finished == ["second"]
