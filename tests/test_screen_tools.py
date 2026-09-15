"""
Tests for the tools that let FRIDAY read the machine precisely:

  * skills/screen_text_skill.py – OCR, the exact characters on screen
  * skills/window_skill.py      – which window the user is actually in
  * skills/clipboard_skill.py   – what they have copied

Why OCR at all, when there is already a vision model: qwen2.5vl:3b answers
"what am I looking at" well and cannot be trusted to transcribe a stack trace.
It paraphrases, and it reads a downscaled JPEG. An error message quoted
approximately is worse than useless -- you cannot search for it, and you
certainly cannot patch code from it. OCR returns the characters.

No test here captures a real screen or loads a real OCR model.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from intelligence.task import Task, TaskStatus


def _task(intent: str, **params) -> Task:
    return Task(
        task_id="t1",
        skill_name="",
        intent=intent,
        parameters=params,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


class TestScreenText:
    @pytest.fixture
    def skill(self, monkeypatch):
        from skills import screen_text_skill

        monkeypatch.setattr(
            screen_text_skill, "_capture_png", lambda: b"fake-png-bytes"
        )
        return screen_text_skill

    @pytest.mark.asyncio
    async def test_recognised_lines_are_returned_verbatim(self, skill, monkeypatch):
        monkeypatch.setattr(
            skill,
            "_run_ocr",
            lambda _: ["Traceback (most recent call last):", "  File \"app.py\", line 7"],
        )

        out = await skill.ScreenTextSkill().execute(_task("screen_text"))

        assert "Traceback (most recent call last):" in out
        assert 'File "app.py", line 7' in out

    @pytest.mark.asyncio
    async def test_an_empty_screen_says_so_rather_than_returning_nothing(
        self, skill, monkeypatch
    ):
        """An empty string would read to the model as a successful call that
        found nothing worth mentioning, and it would carry on inventing."""
        monkeypatch.setattr(skill, "_run_ocr", lambda _: [])

        out = await skill.ScreenTextSkill().execute(_task("screen_text"))

        assert "no text" in out.lower()

    @pytest.mark.asyncio
    async def test_a_missing_ocr_package_explains_the_install(self, skill, monkeypatch):
        def unavailable(_):
            raise ImportError("No module named 'rapidocr_onnxruntime'")

        monkeypatch.setattr(skill, "_run_ocr", unavailable)

        out = await skill.ScreenTextSkill().execute(_task("screen_text"))

        assert "pip install" in out.lower()

    @pytest.mark.asyncio
    async def test_a_capture_failure_is_reported_not_raised(self, skill, monkeypatch):
        from vision.screen_capture import CaptureError

        def broken():
            raise CaptureError("no display")

        monkeypatch.setattr(skill, "_capture_png", broken)

        out = await skill.ScreenTextSkill().execute(_task("screen_text"))

        assert "couldn't" in out.lower() or "could not" in out.lower()


class TestActiveWindow:
    @pytest.mark.asyncio
    async def test_the_window_title_is_reported(self, monkeypatch):
        from skills import window_skill

        monkeypatch.setattr(window_skill, "_active_title", lambda: "app.py - VS Code")

        out = await window_skill.WindowSkill().execute(_task("active_window"))

        assert "app.py - VS Code" in out

    @pytest.mark.asyncio
    async def test_no_focused_window_is_reported_plainly(self, monkeypatch):
        from skills import window_skill

        monkeypatch.setattr(window_skill, "_active_title", lambda: None)

        out = await window_skill.WindowSkill().execute(_task("active_window"))

        assert "couldn't" in out.lower() or "no " in out.lower()


class TestClipboard:
    @pytest.mark.asyncio
    async def test_reading_returns_the_clipboard_text(self, monkeypatch):
        from skills import clipboard_skill

        monkeypatch.setattr(clipboard_skill, "_paste", lambda: "ValueError: bad input")

        out = await clipboard_skill.ClipboardSkill().execute(
            _task("clipboard", action="read")
        )

        assert "ValueError: bad input" in out

    @pytest.mark.asyncio
    async def test_an_empty_clipboard_says_so(self, monkeypatch):
        from skills import clipboard_skill

        monkeypatch.setattr(clipboard_skill, "_paste", lambda: "")

        out = await clipboard_skill.ClipboardSkill().execute(
            _task("clipboard", action="read")
        )

        assert "empty" in out.lower()

    @pytest.mark.asyncio
    async def test_writing_copies_the_text(self, monkeypatch):
        from skills import clipboard_skill

        copied = []
        monkeypatch.setattr(clipboard_skill, "_copy", copied.append)

        await clipboard_skill.ClipboardSkill().execute(
            _task("clipboard", action="write", text="hello")
        )

        assert copied == ["hello"]

    @pytest.mark.asyncio
    async def test_writing_without_text_is_refused(self, monkeypatch):
        from skills import clipboard_skill

        copied = []
        monkeypatch.setattr(clipboard_skill, "_copy", copied.append)

        out = await clipboard_skill.ClipboardSkill().execute(
            _task("clipboard", action="write")
        )

        assert copied == []
        assert "text" in out.lower()
