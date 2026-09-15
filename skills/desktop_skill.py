"""
skills/desktop_skill.py – Driving the desktop itself
=====================================================
The browser tools cover web apps. This covers everything else: bringing a
window to the front, and sending keystrokes to it.

Deliberately small. The obvious version of "control my laptop" is a
screenshot-and-click loop over pixel coordinates, and on a voice assistant
that is a bad trade -- it is slow, it breaks on every theme and DPI change,
and when it misfires it clicks something arbitrary. Two narrow, reliable
primitives do most of what people actually ask for:

  * ``focus_window`` finds a window by part of its title and raises it. This is
    what "switch to VS Code" means, and it is what makes the keystroke tool
    aimable -- keys go to whatever has focus, so focusing first is how you
    choose the target;
  * ``press_keys`` sends a shortcut. Applications are already designed to be
    driven this way: ctrl+s, ctrl+shift+p, alt+tab. A keyboard shortcut is
    both more reliable than a click and more likely to be what the user meant.

pywinauto backs the window work rather than raw pixels: it reads the Windows
UI Automation tree, so it finds a window by its real title regardless of where
it sits on screen.

Everything here is confirmed with the user before it runs -- see ``confirm``
on the tool definitions. Keystrokes sent to the wrong window are not
recoverable, and the assistant cannot see what it is about to type into.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.desktop")

_INSTALL_HINT = (
    "Desktop control needs pywinauto and pyautogui. Install them with: "
    "pip install pywinauto pyautogui"
)

#: Keys accepted in a shortcut. An allowlist rather than free-form text: this
#: sends real input to a real window, and "type whatever the model produced"
#: is not something to do on someone's machine.
_ALLOWED_KEYS = frozenset(
    list("abcdefghijklmnopqrstuvwxyz0123456789")
    + [
        "ctrl", "control", "alt", "shift", "win", "cmd", "super",
        "enter", "return", "tab", "esc", "escape", "space", "backspace",
        "delete", "del", "home", "end", "pageup", "pagedown", "insert",
        "up", "down", "left", "right",
        *[f"f{n}" for n in range(1, 25)],
        ",", ".", "/", "\\", "-", "=", "[", "]", ";", "'", "`",
    ]
)

#: Normalised spellings, so "control" and "ctrl" both work.
_KEY_ALIASES = {
    "control": "ctrl",
    "return": "enter",
    "escape": "esc",
    "del": "delete",
    "super": "win",
    "cmd": "win",
}


def _focus(title_fragment: str) -> str | None:
    """Raise the first window whose title contains ``title_fragment``.

    Returns the matched title, or None when nothing matched.
    """
    from pywinauto import Desktop

    needle = title_fragment.strip().lower()

    for window in Desktop(backend="uia").windows():
        try:
            title = window.window_text()
        except Exception:
            continue

        if title and needle in title.lower():
            try:
                window.set_focus()
            except Exception as exc:
                # A minimised or elevated window can refuse focus; say which
                # one rather than pretending it worked.
                logger.info(f"Could not focus '{title}': {exc}")
                continue
            return title

    return None


def _press(keys: list[str]) -> None:
    import pyautogui

    pyautogui.hotkey(*keys)


def _type_text(text: str) -> None:
    import pyautogui

    pyautogui.typewrite(text, interval=0.01)


class DesktopSkill(Skill):
    """Focus a window and send it keystrokes."""

    name = "DesktopSkill"
    description = "Brings windows to the front and sends keyboard shortcuts."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        intent = task.intent
        params = task.parameters or {}

        try:
            if intent == "focus_window":
                return await self._focus_window(params)
            if intent == "press_keys":
                return await self._press_keys(params)
        except ImportError:
            return _INSTALL_HINT
        except Exception as exc:
            logger.exception(f"Desktop action {intent} failed")
            return f"That didn't work: {exc}"

        return f"DesktopSkill cannot handle intent: {intent}"

    async def _focus_window(self, params: dict) -> str:
        title = str(params.get("title") or params.get("application") or "").strip()
        if not title:
            return "Which window should I switch to?"

        # set_focus() blocks on the UI Automation tree; off the event loop it
        # would freeze audio and barge-in for its duration.
        matched = await asyncio.to_thread(_focus, title)

        if matched is None:
            return f"I couldn't find a window matching '{title}'."

        return f"Switched to {matched}."

    async def _press_keys(self, params: dict) -> str:
        text = str(params.get("text") or "").strip()
        raw_keys = str(params.get("keys") or "").strip()

        if text:
            await asyncio.to_thread(_type_text, text)
            return f"Typed '{text}' into the active window."

        if not raw_keys:
            return "Which keys should I press?"

        keys = self._normalise(raw_keys)
        if keys is None:
            return (
                f"I won't send '{raw_keys}' — I only send ordinary keys and "
                f"shortcuts like ctrl+s or alt+tab."
            )

        await asyncio.to_thread(_press, keys)
        return f"Pressed {'+'.join(keys)}."

    @staticmethod
    def _normalise(raw: str) -> list[str] | None:
        """Split "ctrl+shift+p" into validated key names, or None if refused.

        None rather than an exception because the agent loop hands the message
        back to the model, which can then choose a different approach.
        """
        parts = [
            _KEY_ALIASES.get(part.strip().lower(), part.strip().lower())
            for part in raw.replace(" ", "+").split("+")
            if part.strip()
        ]

        if not parts or any(part not in _ALLOWED_KEYS for part in parts):
            return None

        return parts
