"""
tests/test_vision_hardening.py – Regressions from adversarial review
=====================================================================
The window is excluded from capture, but three things were still visible to a
screen share: the tray context menu, the orb's tooltip, and the tray tooltip —
the last two of which announced what FRIDAY was doing.
"""

from __future__ import annotations

import sys
import types

import pytest


# ------------------------------------------------------- cursor coordinates
class TestCursorCoordinateSpace:
    """mss reports monitors in physical pixels; Qt reports the cursor in
    logical ones. At 125% scaling the mismatch picks the wrong monitor."""

    def test_prefers_the_win32_physical_reading(self, monkeypatch):
        from vision import screen_capture

        monkeypatch.setattr(screen_capture.sys, "platform", "win32")

        class FakeUser32:
            def GetCursorPos(self, ref):
                ref._obj.x, ref._obj.y = 878, 434
                return 1

        fake_ctypes = types.ModuleType("ctypes")
        fake_ctypes.windll = types.SimpleNamespace(user32=FakeUser32())
        fake_ctypes.byref = lambda o: types.SimpleNamespace(_obj=o)
        fake_wintypes = types.ModuleType("ctypes.wintypes")
        fake_wintypes.POINT = lambda: types.SimpleNamespace(x=0, y=0)
        fake_ctypes.wintypes = fake_wintypes
        monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
        monkeypatch.setitem(sys.modules, "ctypes.wintypes", fake_wintypes)

        assert screen_capture._cursor_position() == (878, 434)

    def test_qt_reading_is_scaled_by_device_pixel_ratio(self, monkeypatch):
        """The fallback path must not hand back logical pixels."""
        from vision import screen_capture

        monkeypatch.setattr(screen_capture.sys, "platform", "linux")

        fake_qtgui = types.ModuleType("PyQt6.QtGui")
        screen = types.SimpleNamespace(devicePixelRatio=lambda: 1.25)
        fake_qtgui.QCursor = types.SimpleNamespace(
            pos=lambda: types.SimpleNamespace(x=lambda: 702, y=lambda: 347)
        )
        fake_qtgui.QGuiApplication = types.SimpleNamespace(
            instance=lambda: object(),
            screenAt=lambda pos: screen,
            primaryScreen=lambda: screen,
        )
        monkeypatch.setitem(sys.modules, "PyQt6.QtGui", fake_qtgui)

        assert screen_capture._cursor_position() == (877, 433)

    def test_no_qapplication_returns_none_not_a_sentinel(self, monkeypatch):
        """QCursor.pos() without a QApplication returns (8388608, 8388608).

        It does not raise, so the old except-guard never fired and the sentinel
        was silently compared against every monitor rect. run.py has no Qt
        application at all, so this is a live path.
        """
        from vision import screen_capture

        monkeypatch.setattr(screen_capture.sys, "platform", "linux")

        fake_qtgui = types.ModuleType("PyQt6.QtGui")
        fake_qtgui.QCursor = types.SimpleNamespace(
            pos=lambda: types.SimpleNamespace(
                x=lambda: 8388608, y=lambda: 8388608
            )
        )
        fake_qtgui.QGuiApplication = types.SimpleNamespace(instance=lambda: None)
        monkeypatch.setitem(sys.modules, "PyQt6.QtGui", fake_qtgui)

        assert screen_capture._cursor_position() is None

    def test_unknown_cursor_falls_back_to_a_real_display(self, monkeypatch):
        from vision import screen_capture

        monkeypatch.setattr(screen_capture, "_cursor_position", lambda: None)

        sct = types.SimpleNamespace(
            monitors=[
                {"left": 0, "top": 0, "width": 3840, "height": 1080},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": 1920, "top": 0, "width": 1920, "height": 1080},
            ]
        )
        index, monitor = screen_capture._monitor_under_cursor(sct)
        assert index == 1
        assert monitor["width"] == 1920


# ------------------------------------------------------------- popup leaks
class TestPopupsDoNotLeak:
    def test_tray_menu_is_hidden_when_it_is_about_to_show(self, monkeypatch):
        """The tray menu is the one that actually appears in practice.

        The orb's own fallback menu is only wired up when there is *no* tray,
        so hiding only that one left the real menu visible to a screen share.
        """
        import ui.tray as tray_module

        hidden = []
        monkeypatch.setattr(
            "vision.screen_hider.hide_from_capture",
            lambda w: hidden.append(w) or True,
        )

        controller = tray_module.TrayController.__new__(tray_module.TrayController)
        controller._menu = types.SimpleNamespace(winId=lambda: 4242)
        controller._hide_menu_from_capture()

        assert hidden == [controller._menu]

    def test_hiding_the_menu_never_raises(self, monkeypatch):
        import ui.tray as tray_module

        def _boom(widget):
            raise OSError("no native handle")

        monkeypatch.setattr("vision.screen_hider.hide_from_capture", _boom)

        controller = tray_module.TrayController.__new__(tray_module.TrayController)
        controller._menu = types.SimpleNamespace(winId=lambda: 0)
        controller._hide_menu_from_capture()  # must not raise

    def test_no_menu_is_a_no_op(self):
        import ui.tray as tray_module

        controller = tray_module.TrayController.__new__(tray_module.TrayController)
        controller._menu = None
        controller._hide_menu_from_capture()


class TestTooltipsDoNotAnnounceState:
    """A tooltip renders in its own native window and does not inherit the
    exclusion, so "FRIDAY — Listening" hovered over an invisible orb."""

    def test_tray_tooltip_carries_no_state(self, monkeypatch):
        import ui.tray as tray_module

        # Building a real icon needs a QApplication, which would abort the
        # test process rather than fail a test.
        monkeypatch.setattr(tray_module, "make_orb_icon", lambda state: object())

        captured = []
        controller = tray_module.TrayController.__new__(tray_module.TrayController)
        controller._tray = types.SimpleNamespace(
            setIcon=lambda icon: None,
            setToolTip=captured.append,
        )
        controller.set_state("LISTENING")

        assert captured == ["FRIDAY"]
        assert "Listening" not in captured[0]

    # The property getter is called unbound: instantiating a QWidget without a
    # QApplication aborts the Qt runtime and takes the test process with it.
    def test_hidden_from_capture_reports_the_applied_state(self):
        from ui.main_window import MainWindow

        getter = MainWindow.hidden_from_capture.fget
        assert getter(types.SimpleNamespace(_hidden_from_capture=True)) is True

    def test_hidden_from_capture_defaults_to_false(self):
        from ui.main_window import MainWindow

        getter = MainWindow.hidden_from_capture.fget
        assert getter(types.SimpleNamespace()) is False, (
            "must default to False so a machine that cannot hide still shows "
            "its tooltips"
        )


# --------------------------------------------------------- error reporting
class TestErrorsAreSpeakable:
    @pytest.mark.asyncio
    async def test_text_only_model_does_not_read_json_aloud(self):
        """A text-only model returns a 400 whose body is raw JSON."""
        from skills.vision_skill import VisionSkill

        skill = VisionSkill(container=None)
        message = skill._explain_failure(
            Exception(
                '{"error":{"code":400,"message":"Multimodal data provided, but '
                'model does not support multimodal requests.",'
                '"type":"invalid_request_error"}} (status code: 400)'
            ),
            "qwen2.5:3b",
        )

        assert "{" not in message and "}" not in message
        assert "text-only" in message
        assert "VISION_MODEL" in message
