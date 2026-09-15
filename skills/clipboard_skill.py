"""
skills/clipboard_skill.py – Read and write the clipboard
=========================================================
``clipboard`` was one of three intents wired to ``DefaultSkill``: the router
recognised it and then nothing happened.

It earns its place beyond finishing that stub. When a user is stuck on an
error, they have very often already selected and copied it, and reading the
clipboard costs nothing next to a screenshot plus OCR plus a vision-model
turn. It is the cheapest way ULTRON has of finding out what the user is
looking at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.clipboard")

#: Clipboards hold whole documents. The model only needs enough to work with.
MAX_CHARS = 8_000

_INSTALL_HINT = "Clipboard access needs pyperclip. Install it with: pip install pyperclip"


def _paste() -> str:
    import pyperclip

    return pyperclip.paste() or ""


def _copy(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)


class ClipboardSkill(Skill):
    """Read what the user copied, or copy something for them."""

    name = "ClipboardSkill"
    description = "Reads and writes the system clipboard."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        action = str(task.parameters.get("action") or "read").lower()

        if action == "write":
            text = task.parameters.get("text")
            if not text:
                return "I need the text to copy."
            try:
                _copy(str(text))
            except ImportError:
                return _INSTALL_HINT
            except Exception as exc:
                return f"Couldn't copy that: {exc}"
            return "Copied to the clipboard."

        if action != "read":
            return f"I can read or write the clipboard, not '{action}'."

        try:
            content = _paste()
        except ImportError:
            return _INSTALL_HINT
        except Exception as exc:
            return f"Couldn't read the clipboard: {exc}"

        if not content.strip():
            return "The clipboard is empty."

        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS] + f"\n... (truncated at {MAX_CHARS} characters)"

        return f"Clipboard contents:\n{content}"
