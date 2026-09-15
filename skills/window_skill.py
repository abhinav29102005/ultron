"""
skills/window_skill.py – Which window the user is actually in
==============================================================
One cheap call that changes what every other tool should do.

"Fix this" means something different in VS Code than in Chrome than in a
terminal, and the agent has no way to tell them apart from the words alone.
The window title usually says outright which file is open and which project it
belongs to ("preflight.py - ULTRON-agent - Visual Studio Code"), which is
often enough to skip a screenshot entirely and go straight to reading the file.

Cheap on purpose: a title lookup costs a fraction of a millisecond, against a
second or more for a capture plus a vision-model turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.window")


def _active_title() -> str | None:
    """The foreground window's title, or None when there is not one.

    None is a normal answer, not a failure: the desktop can have focus, and a
    window can have an empty title.
    """
    try:
        import pygetwindow
    except ImportError:
        return None

    try:
        window = pygetwindow.getActiveWindow()
    except Exception:
        # pygetwindow raises rather than returning None on some Windows
        # states (a window closing mid-call, for instance).
        return None

    if window is None:
        return None

    title = getattr(window, "title", "") or ""
    return title.strip() or None


class WindowSkill(Skill):
    """Report the window the user is currently working in."""

    name = "WindowSkill"
    description = "Reports which window and program the user is currently using."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        title = _active_title()

        if not title:
            return "I couldn't tell which window is in focus right now."

        return f"The active window is: {title}"
