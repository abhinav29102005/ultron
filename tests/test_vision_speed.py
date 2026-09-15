"""
tests/test_vision_speed.py – The reasons looking at the screen was slow
=======================================================================
Not one of these is about the answer being wrong. They are all about the wait
before it, and each pins a specific cause that was measured:

* the model was reloaded from disk on every question, because nothing set
  ``keep_alive`` and nothing warmed it at startup;
* the capture ran on the event loop, so speech and the UI froze along with it;
* the downscale and the decode budget were both sized for a machine that was
  not going to be doing this on a CPU.

The warm-up in particular has to be unfailingly quiet: Ollama not running is
the normal state on a fresh machine, and it must cost a feature, not a launch.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import types

import pytest


# --------------------------------------------------------------- fake ollama
def _fake_ollama(monkeypatch, *, reply="ok", error=None, delay=0.0):
    """Install a fake ollama module and return the recorded call."""
    recorded = {}

    class FakeAsyncClient:
        def __init__(self, host=None):
            recorded["host"] = host

        async def chat(self, **kwargs):
            recorded.update(kwargs)
            recorded["calls"] = recorded.get("calls", 0) + 1
            if delay:
                await asyncio.sleep(delay)
            if error is not None:
                raise error
            return types.SimpleNamespace(
                message=types.SimpleNamespace(content=reply)
            )

    module = types.ModuleType("ollama")
    module.AsyncClient = FakeAsyncClient
    monkeypatch.setitem(sys.modules, "ollama", module)
    return recorded


IMAGE_MESSAGES = [
    {"role": "system", "content": "look at this"},
    {"role": "user", "content": "what is this", "images": [b"\xff\xd8jpeg"]},
]


# ------------------------------------------------------------------- preload
class TestPreload:
    """The single biggest cost was a cold load on every question."""

    @pytest.mark.asyncio
    async def test_loads_the_model_without_asking_it_anything(self, monkeypatch):
        from vision.vision_client import preload

        recorded = _fake_ollama(monkeypatch)

        assert await preload("testvision:3b", "http://localhost:11434") is True
        assert recorded["model"] == "testvision:3b"
        assert recorded["messages"] == [], (
            "the warm-up must not generate anything — it only loads weights"
        )

    @pytest.mark.asyncio
    async def test_holds_the_model_in_memory(self, monkeypatch):
        from vision.vision_client import preload

        recorded = _fake_ollama(monkeypatch)

        await preload("testvision:3b", "http://x", keep_alive="45m")
        assert recorded["keep_alive"] == "45m", (
            "without keep_alive the warm-up expires before the first question"
        )

    @pytest.mark.asyncio
    async def test_ollama_down_never_raises(self, monkeypatch):
        """Startup calls this. A machine with no Ollama must still boot."""
        from vision.vision_client import preload

        _fake_ollama(monkeypatch, error=ConnectionError("connection refused"))

        assert await preload("testvision:3b", "http://localhost:11434") is False

    @pytest.mark.asyncio
    async def test_missing_model_never_raises(self, monkeypatch):
        from vision.vision_client import preload

        _fake_ollama(monkeypatch, error=Exception('model "testvision:3b" not found'))

        assert await preload("testvision:3b", "http://x") is False

    @pytest.mark.asyncio
    async def test_ollama_not_installed_never_raises(self, monkeypatch):
        from vision.vision_client import preload

        # Block the import the way an uninstalled package would.
        monkeypatch.setitem(sys.modules, "ollama", None)

        assert await preload("testvision:3b", "http://x") is False


# ---------------------------------------------------------------- ask_vision
class TestAskVision:
    @pytest.mark.asyncio
    async def test_keeps_the_model_resident_for_the_next_question(
        self, monkeypatch
    ):
        from vision.vision_client import ask_vision

        recorded = _fake_ollama(monkeypatch, reply="a code editor")

        answer = await ask_vision(
            model="testvision:3b",
            host="http://localhost:11434",
            messages=IMAGE_MESSAGES,
            keep_alive="30m",
        )

        assert answer == "a code editor"
        # Top level, not inside options: Ollama ignores it there, silently.
        assert recorded["keep_alive"] == "30m"
        assert "keep_alive" not in recorded["options"]

    @pytest.mark.asyncio
    async def test_decode_budget_is_sized_for_a_spoken_answer(self, monkeypatch):
        from vision.vision_client import ask_vision

        recorded = _fake_ollama(monkeypatch)

        await ask_vision(
            model="testvision:3b",
            host="http://x",
            messages=IMAGE_MESSAGES,
            num_predict=96,
        )
        assert recorded["options"]["num_predict"] == 96

    @pytest.mark.asyncio
    async def test_defaults_are_the_fast_ones(self, monkeypatch):
        from vision import vision_client

        recorded = _fake_ollama(monkeypatch)

        await vision_client.ask_vision(
            model="testvision:3b", host="http://x", messages=IMAGE_MESSAGES
        )
        assert recorded["keep_alive"] == vision_client.DEFAULT_KEEP_ALIVE
        assert (
            recorded["options"]["num_predict"] == vision_client.DEFAULT_NUM_PREDICT
        )
        assert vision_client.DEFAULT_NUM_PREDICT < 300, (
            "300 tokens for a three-sentence spoken answer is wasted decode time"
        )

    @pytest.mark.asyncio
    async def test_errors_reach_the_caller_intact(self, monkeypatch):
        """The skill turns these into something the user can act on.

        Catching them here would flatten "model not pulled", "text-only model"
        and "Ollama is not running" into one useless shrug.
        """
        from vision.vision_client import ask_vision

        _fake_ollama(monkeypatch, error=Exception('model "x" not found'))

        with pytest.raises(Exception, match="not found"):
            await ask_vision(
                model="testvision:3b", host="http://x", messages=IMAGE_MESSAGES
            )

    @pytest.mark.asyncio
    async def test_a_stall_is_not_a_hang(self, monkeypatch):
        from vision.vision_client import ask_vision

        _fake_ollama(monkeypatch, delay=5)

        with pytest.raises(TimeoutError) as excinfo:
            await ask_vision(
                model="testvision:3b",
                host="http://x",
                messages=IMAGE_MESSAGES,
                timeout=0.05,
            )
        # asyncio raises this with an empty message; spoken aloud that is
        # "I couldn't read the screen just now:" and then nothing.
        assert str(excinfo.value).strip()
        assert "testvision:3b" in str(excinfo.value)


# ------------------------------------------------------------ capture offload
class TestCaptureIsOffTheEventLoop:
    """The grab, the resize and the encode are ~100 ms of straight CPU.

    Run on the loop they stall speech recognition, playback and the orb —
    which is why the assistant looked frozen while it was 'thinking'.
    """

    @pytest.mark.asyncio
    async def test_capture_runs_on_a_worker_thread(self, monkeypatch):
        from vision import screen_capture

        seen = {}

        def _fake_capture(max_edge, quality):
            seen["thread"] = threading.get_ident()
            seen["args"] = (max_edge, quality)
            return "capture"

        monkeypatch.setattr(screen_capture, "capture_screen", _fake_capture)

        result = await screen_capture.capture_screen_async(max_edge=640, quality=60)

        assert result == "capture"
        assert seen["args"] == (640, 60)
        assert seen["thread"] != threading.get_ident(), (
            "capture ran on the event loop thread and blocked everything on it"
        )

    @pytest.mark.asyncio
    async def test_the_loop_keeps_running_during_a_capture(self, monkeypatch):
        from vision import screen_capture

        started = threading.Event()
        release = threading.Event()

        def _slow_capture(max_edge, quality):
            started.set()
            release.wait(5)
            return "capture"

        monkeypatch.setattr(screen_capture, "capture_screen", _slow_capture)

        task = asyncio.ensure_future(screen_capture.capture_screen_async())
        await asyncio.to_thread(started.wait, 5)

        # If the capture held the loop, this would not get a turn until it
        # finished — and it cannot finish until we release it.
        await asyncio.sleep(0)
        release.set()

        assert await task == "capture"

    @pytest.mark.asyncio
    async def test_capture_errors_survive_the_offload(self, monkeypatch):
        from vision import screen_capture
        from vision.screen_capture import CaptureError

        def _boom(max_edge, quality):
            raise CaptureError("no screen here")

        monkeypatch.setattr(screen_capture, "capture_screen", _boom)

        with pytest.raises(CaptureError, match="no screen here"):
            await screen_capture.capture_screen_async()

    def test_the_client_re_exports_the_offloaded_capture(self):
        """One import for the skill: the client owns the whole path."""
        from vision.screen_capture import capture_screen_async
        from vision.vision_client import capture_screen_async as exported

        assert exported is capture_screen_async


# ------------------------------------------------------------------ downscale
class FakeShot:
    def __init__(self, width, height):
        self.size = (width, height)
        # BGRX: four bytes per pixel, which is what mss hands back.
        self.bgra = bytes([20, 40, 60, 255]) * (width * height)


class FakeSCT:
    def __init__(self, monitors):
        self.monitors = monitors

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, monitor):
        return FakeShot(monitor["width"], monitor["height"])


def _install_fake_mss(monkeypatch, monitors):
    module = types.ModuleType("mss")
    module.mss = lambda: FakeSCT(monitors)
    monkeypatch.setitem(sys.modules, "mss", module)


def _monitors(width, height):
    return [
        {"left": 0, "top": 0, "width": width, "height": height},
        {"left": 0, "top": 0, "width": width, "height": height},
    ]


class TestDownscale:
    """The two-step reduce has to land on exactly the size LANCZOS did."""

    @pytest.mark.parametrize(
        ("source", "max_edge", "expected"),
        [
            ((3840, 2160), 896, (896, 504)),   # integer reduce, then a resize
            ((3840, 2160), 1280, (1280, 720)),  # an exact factor of three
            ((2560, 1440), 640, (640, 360)),
            ((1920, 1080), 480, (480, 270)),
            ((1080, 1920), 540, (304, 540)),    # portrait: the tall edge caps
        ],
    )
    def test_respects_a_custom_max_edge(
        self, monkeypatch, source, max_edge, expected
    ):
        from vision.screen_capture import capture_screen

        _install_fake_mss(monkeypatch, _monitors(*source))
        shot = capture_screen(max_edge=max_edge)

        assert (shot.width, shot.height) == expected
        assert max(shot.width, shot.height) == max_edge

    def test_a_screen_under_the_cap_is_left_alone(self, monkeypatch):
        """reduce() on an already-small image would throw away real detail."""
        from vision.screen_capture import capture_screen

        _install_fake_mss(monkeypatch, _monitors(800, 600))
        shot = capture_screen(max_edge=1280)

        assert (shot.width, shot.height) == (800, 600)

    def test_the_default_cap_is_sized_for_a_cpu_model(self):
        from vision import screen_capture

        assert screen_capture.MAX_EDGE <= 1024, (
            "a 1280px frame is roughly twice the vision tokens of 896px and "
            "reads the same UI text"
        )

    def test_settings_defaults_match_the_module(self):
        """A stray .env key is the usual way tuning silently stops applying."""
        from config.settings import Settings
        from vision import screen_capture, vision_client

        fields = Settings.model_fields
        assert fields["vision_max_edge"].default == screen_capture.MAX_EDGE
        assert fields["vision_jpeg_quality"].default == screen_capture.JPEG_QUALITY
        assert fields["vision_keep_alive"].default == vision_client.DEFAULT_KEEP_ALIVE
        assert (
            fields["vision_num_predict"].default == vision_client.DEFAULT_NUM_PREDICT
        )
        assert fields["vision_preload"].default is True
