"""
tests/test_vision.py – Screen capture, capture exclusion, and the vision skill
==============================================================================
The interesting behaviour is what happens when things are missing: no mss, no
vision model, no Ollama, wrong Windows build. Every one of those has to
degrade into something the user can act on rather than a traceback.
"""

from __future__ import annotations

import sys
import types

import pytest


# ------------------------------------------------------------------- capture
class FakeShot:
    def __init__(self, width, height):
        self.size = (width, height)
        # BGRX: four bytes per pixel, which is what mss hands back.
        self.bgra = bytes([20, 40, 60, 255]) * (width * height)


class FakeSCT:
    def __init__(self, monitors):
        self.monitors = monitors
        self.grabbed = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, monitor):
        self.grabbed = monitor
        return FakeShot(monitor["width"], monitor["height"])


def _install_fake_mss(monkeypatch, monitors):
    holder = {}

    def _factory():
        sct = FakeSCT(monitors)
        holder["sct"] = sct
        return sct

    module = types.ModuleType("mss")
    module.mss = _factory
    monkeypatch.setitem(sys.modules, "mss", module)
    return holder


ONE_MONITOR = [
    {"left": 0, "top": 0, "width": 1920, "height": 1080},
    {"left": 0, "top": 0, "width": 1920, "height": 1080},
]


class TestCaptureScreen:
    def test_returns_jpeg_bytes(self, monkeypatch):
        from vision.screen_capture import capture_screen

        _install_fake_mss(monkeypatch, ONE_MONITOR)
        shot = capture_screen()

        assert isinstance(shot.jpeg, bytes)
        assert len(shot.jpeg) > 0
        # JPEG magic. A PNG here would mean the encode format regressed and
        # payload size quietly tripled.
        assert shot.jpeg[:2] == b"\xff\xd8"

    def test_downscales_to_the_edge_cap(self, monkeypatch):
        from vision.screen_capture import capture_screen

        _install_fake_mss(monkeypatch, ONE_MONITOR)
        shot = capture_screen(max_edge=640)

        assert max(shot.width, shot.height) == 640
        assert shot.width == 640 and shot.height == 360, "aspect ratio was not kept"

    def test_small_screen_is_not_upscaled(self, monkeypatch):
        from vision.screen_capture import capture_screen

        _install_fake_mss(
            monkeypatch,
            [
                {"left": 0, "top": 0, "width": 800, "height": 600},
                {"left": 0, "top": 0, "width": 800, "height": 600},
            ],
        )
        shot = capture_screen(max_edge=1280)
        assert (shot.width, shot.height) == (800, 600)

    def test_never_grabs_the_union_of_all_monitors(self, monkeypatch):
        """monitors[0] spans every display; nothing on it is legible."""
        from vision.screen_capture import capture_screen

        monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},  # the union
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]
        holder = _install_fake_mss(monkeypatch, monitors)
        shot = capture_screen()

        assert shot.monitor_index != 0
        assert holder["sct"].grabbed["width"] == 1920

    def test_missing_mss_explains_the_install(self, monkeypatch):
        from vision.screen_capture import CaptureError, capture_screen

        # Block the import the way an uninstalled package would.
        monkeypatch.setitem(sys.modules, "mss", None)

        with pytest.raises(CaptureError) as excinfo:
            capture_screen()
        assert "pip install mss" in str(excinfo.value)

    def test_grab_failure_becomes_capture_error(self, monkeypatch):
        from vision.screen_capture import CaptureError, capture_screen

        module = types.ModuleType("mss")

        def _boom():
            raise RuntimeError("no display")

        module.mss = _boom
        monkeypatch.setitem(sys.modules, "mss", module)

        with pytest.raises(CaptureError):
            capture_screen()


# -------------------------------------------------------------------- hider
class FakeWidget:
    def __init__(self, handle=12345):
        self._handle = handle

    def winId(self):
        return self._handle


class TestScreenHider:
    def test_uses_exclude_from_capture_not_monitor(self):
        """WDA_MONITOR blacks the window out, which is more conspicuous."""
        from vision.screen_hider import WDA_EXCLUDEFROMCAPTURE

        assert WDA_EXCLUDEFROMCAPTURE == 0x11

    def test_no_op_off_windows(self, monkeypatch):
        from vision import screen_hider

        monkeypatch.setattr(screen_hider.sys, "platform", "linux")
        assert screen_hider.is_hiding_supported() is False
        # Must not raise: a missing privacy feature never blocks startup.
        assert screen_hider.hide_from_capture(FakeWidget()) is False

    def test_refuses_on_windows_older_than_2004(self, monkeypatch):
        from vision import screen_hider

        monkeypatch.setattr(screen_hider.sys, "platform", "win32")
        monkeypatch.setattr(screen_hider, "_windows_build", lambda: 18363)
        assert screen_hider.is_hiding_supported() is False
        assert screen_hider.hide_from_capture(FakeWidget()) is False

    def test_supported_on_windows_2004_and_newer(self, monkeypatch):
        from vision import screen_hider

        monkeypatch.setattr(screen_hider.sys, "platform", "win32")
        monkeypatch.setattr(screen_hider, "_windows_build", lambda: 19041)
        assert screen_hider.is_hiding_supported() is True

    def test_calls_the_api_with_the_window_handle(self, monkeypatch):
        from vision import screen_hider

        monkeypatch.setattr(screen_hider, "is_hiding_supported", lambda: True)

        calls = []

        class FakeUser32:
            def SetWindowDisplayAffinity(self, handle, affinity):
                calls.append((handle.value, affinity.value))
                return 1

        fake_ctypes = types.ModuleType("ctypes")
        fake_ctypes.windll = types.SimpleNamespace(user32=FakeUser32())
        fake_ctypes.c_void_p = lambda v: types.SimpleNamespace(value=v)
        fake_ctypes.c_uint = lambda v: types.SimpleNamespace(value=v)
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)

        assert screen_hider.hide_from_capture(FakeWidget(999)) is True
        assert calls == [(999, 0x11)]

    def test_widget_without_a_native_handle_is_skipped(self, monkeypatch):
        from vision import screen_hider

        monkeypatch.setattr(screen_hider, "is_hiding_supported", lambda: True)
        assert screen_hider.hide_from_capture(FakeWidget(0)) is False

    def test_api_failure_is_reported_not_raised(self, monkeypatch):
        from vision import screen_hider

        monkeypatch.setattr(screen_hider, "is_hiding_supported", lambda: True)

        class FakeUser32:
            def SetWindowDisplayAffinity(self, handle, affinity):
                raise OSError("access denied")

        fake_ctypes = types.ModuleType("ctypes")
        fake_ctypes.windll = types.SimpleNamespace(user32=FakeUser32())
        fake_ctypes.c_void_p = lambda v: types.SimpleNamespace(value=v)
        fake_ctypes.c_uint = lambda v: types.SimpleNamespace(value=v)
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)

        assert screen_hider.hide_from_capture(FakeWidget()) is False


# --------------------------------------------------------------- vision skill
class FakeTask:
    def __init__(self, intent="screen_query", parameters=None, metadata=None):
        self.intent = intent
        self.parameters = parameters or {}
        self.metadata = metadata or {}


def _fake_ollama(monkeypatch, *, reply=None, error=None):
    """Install a fake ollama module and return the recorded call."""
    recorded = {}

    class FakeAsyncClient:
        def __init__(self, host=None):
            recorded["host"] = host

        async def chat(self, **kwargs):
            recorded.update(kwargs)
            if error is not None:
                raise error
            return types.SimpleNamespace(
                message=types.SimpleNamespace(content=reply)
            )

    module = types.ModuleType("ollama")
    module.AsyncClient = FakeAsyncClient
    monkeypatch.setitem(sys.modules, "ollama", module)
    return recorded


@pytest.fixture
def skill(monkeypatch):
    from skills.vision_skill import VisionSkill
    from vision import screen_capture

    _install_fake_mss(monkeypatch, ONE_MONITOR)

    container = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            vision_model="testvision:3b",
            ollama_base_url="http://localhost:11434",
        )
    )
    return VisionSkill(container=container)


class TestVisionSkill:
    @pytest.mark.asyncio
    async def test_sends_the_image_with_the_question(self, skill, monkeypatch):
        recorded = _fake_ollama(monkeypatch, reply="A code editor with an error.")

        result = await skill.execute(
            FakeTask(parameters={"question": "what does this error mean"})
        )

        assert result == "A code editor with an error."
        assert recorded["model"] == "testvision:3b"

        user_message = recorded["messages"][-1]
        assert user_message["content"] == "what does this error mean"
        assert len(user_message["images"]) == 1
        assert user_message["images"][0][:2] == b"\xff\xd8", "no JPEG was attached"

    @pytest.mark.asyncio
    async def test_falls_back_to_the_raw_utterance(self, skill, monkeypatch):
        recorded = _fake_ollama(monkeypatch, reply="ok")

        await skill.execute(
            FakeTask(metadata={"raw_utterance": "help me with what I'm looking at"})
        )
        assert (
            recorded["messages"][-1]["content"]
            == "help me with what I'm looking at"
        )

    @pytest.mark.asyncio
    async def test_screen_read_asks_for_the_text_itself(self, skill, monkeypatch):
        recorded = _fake_ollama(monkeypatch, reply="ok")

        await skill.execute(FakeTask(intent="screen_read"))
        assert "Read the text" in recorded["messages"][-1]["content"]

    @pytest.mark.asyncio
    async def test_missing_model_returns_the_pull_command(self, skill, monkeypatch):
        _fake_ollama(monkeypatch, error=Exception('model "testvision:3b" not found'))

        result = await skill.execute(FakeTask(parameters={"question": "what's this"}))

        assert "ollama pull testvision:3b" in result
        assert "Traceback" not in result

    @pytest.mark.asyncio
    async def test_ollama_down_is_explained_plainly(self, skill, monkeypatch):
        _fake_ollama(monkeypatch, error=Exception("connection refused"))

        result = await skill.execute(FakeTask(parameters={"question": "hi"}))
        assert "Ollama" in result and "running" in result

    @pytest.mark.asyncio
    async def test_capture_failure_is_spoken_not_raised(self, skill, monkeypatch):
        from vision.screen_capture import CaptureError

        async def _boom(**kwargs):
            raise CaptureError("no screen here")

        monkeypatch.setattr("skills.vision_skill.capture_screen_async", _boom)
        result = await skill.execute(FakeTask())
        assert result == "no screen here"

    @pytest.mark.asyncio
    async def test_empty_answer_is_not_silence(self, skill, monkeypatch):
        _fake_ollama(monkeypatch, reply="   ")
        result = await skill.execute(FakeTask(parameters={"question": "hi"}))
        assert result.strip()

    @pytest.mark.asyncio
    async def test_default_model_when_settings_are_absent(self, monkeypatch):
        from skills.vision_skill import DEFAULT_VISION_MODEL, VisionSkill

        _install_fake_mss(monkeypatch, ONE_MONITOR)
        recorded = _fake_ollama(monkeypatch, reply="ok")

        await VisionSkill(container=None).execute(FakeTask())
        assert recorded["model"] == DEFAULT_VISION_MODEL


class TestVisionRouting:
    def test_screen_intents_reach_the_vision_skill(self):
        from intelligence.router import TaskRouter
        from skills.vision_skill import VisionSkill

        assert TaskRouter.ROUTING_TABLE["screen_query"] is VisionSkill
        assert TaskRouter.ROUTING_TABLE["screen_read"] is VisionSkill

    def test_screenshot_still_saves_a_file(self):
        """The two must not be confused: one answers, one writes a PNG."""
        from intelligence.router import TaskRouter
        from skills.system_skills import ScreenshotSkill

        assert TaskRouter.ROUTING_TABLE["screenshot"] is ScreenshotSkill

    def test_intents_are_accepted_by_the_detector(self):
        from intelligence.intent_detector import IntentDetector

        assert "screen_query" in IntentDetector.VALID_INTENTS
        assert "screen_read" in IntentDetector.VALID_INTENTS
