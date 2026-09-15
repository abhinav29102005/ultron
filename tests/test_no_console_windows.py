"""
Console-window hygiene for every Windows subprocess ULTRON spawns.

Bug this covers: black console windows appeared on their own while ULTRON
was running. Any console program started from a process that has no console
of its own -- which is exactly what the PyQt entry point (main_gui.py) is --
gets a brand new, *visible* console allocated for it by Windows. The only
thing that suppresses that is CREATE_NO_WINDOW on the spawn.

The root cause of the startup burst lives in utils/preflight.py and is
covered by tests/test_preflight.py::TestServerLaunchFlags. These are the
remaining command-triggered spawns, which pop a window each time the user
asks for brightness or asks to close an app.

CREATE_NO_WINDOW must never be OR'd with DETACHED_PROCESS: Windows documents
it as ignored in that combination, which is the trap preflight fell into.
"""

from __future__ import annotations

import subprocess

import pytest  # noqa: F401  - fixtures

from skills.System import BrightnessSkill

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)


def _flags(call) -> int:
    return call.kwargs.get("creationflags", 0)


def _assert_hidden(call, what: str) -> None:
    flags = _flags(call)
    assert flags & NO_WINDOW, f"{what} spawns a visible console window"
    assert not flags & DETACHED, f"{what} combines DETACHED_PROCESS with CREATE_NO_WINDOW"


class TestBrightness:
    """Two spawns per 'brightness up': PowerShell is read, then written."""

    def test_reading_brightness_opens_no_window(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "skills.System.subprocess.run",
            lambda *a, **kw: _Result("50", calls, kw),
        )
        BrightnessSkill()._get_brightness_windows()
        _assert_hidden(_Call(calls[-1]), "reading brightness")

    def test_setting_brightness_opens_no_window(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "skills.System.subprocess.run",
            lambda *a, **kw: _Result("", calls, kw),
        )
        BrightnessSkill()._set_brightness_windows(40)
        _assert_hidden(_Call(calls[-1]), "setting brightness")


class TestCloseApplication:
    def test_taskkill_opens_no_window(self, monkeypatch):
        from skills.system_skills import ApplicationSkill

        calls = []
        monkeypatch.setattr(
            "skills.system_skills.subprocess.run",
            lambda *a, **kw: _Result("", calls, kw),
        )
        skill = ApplicationSkill()
        canonical = next(iter(skill.WINDOWS_APPS))
        skill._execute_windows("close_application", canonical, canonical)
        _assert_hidden(_Call(calls[-1]), "closing an application")


class _Result:
    """Minimal stand-in for CompletedProcess that records the kwargs used."""

    def __init__(self, stdout, sink, kwargs):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0
        sink.append(kwargs)


class _Call:
    def __init__(self, kwargs):
        self.kwargs = kwargs
