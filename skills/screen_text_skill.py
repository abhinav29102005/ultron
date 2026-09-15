"""
skills/screen_text_skill.py – Read the screen exactly, with OCR
================================================================
The vision model and this skill do different jobs, and the difference matters.

``VisionSkill`` asks qwen2.5vl:3b what the screen shows. It is good at "what
am I looking at" and it *paraphrases* — it is a language model describing a
downscaled JPEG. Ask it to transcribe a stack trace and you get something that
reads like the stack trace.

For an error message that is not good enough. An approximate exception name
cannot be searched for, and code recalled approximately cannot be patched. So
when precision is what matters, the characters are read by OCR instead.

Two consequences shape this module:

  * the capture is taken at full resolution. ``VisionSkill``'s 896px downscale
    is right for a model that looks at layout and wrong for one that reads
    12px text, where the downscale is exactly what destroys the glyphs;
  * the screenshot is PNG, not JPEG. JPEG's ringing artefacts around
    high-contrast edges are worst on small text, which is all this reads.

Privacy is unchanged from the rest of vision: nothing is captured unless an
utterance routes here, the image lives only for the length of the call, and it
is never written to disk or sent anywhere.
"""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from config.logging_config import get_logger
from skills.base import Skill

#: The engine lives in ``vision.ocr`` because the chat panel's screenshot
#: paste reads characters too, and UI code must not import a skill to do it.
#: Kept bound under the old private name: nothing outside should be able to
#: tell that the implementation moved.
from vision.ocr import ocr_lines as _run_ocr
from vision.screen_capture import CaptureError

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.screen_text")

#: Large enough that no ordinary monitor is downscaled. Text OCR wants the
#: real pixels; see the module docstring.
OCR_MAX_EDGE = 4096

#: Lines returned before the transcript is cut. A full IDE window is a few
#: hundred; a runaway log is not worth the context it would cost.
MAX_LINES = 400

_INSTALL_HINT = (
    "Reading screen text needs the OCR engine. Install it with: "
    "pip install rapidocr-onnxruntime"
)


def _capture_png() -> bytes:
    """A full-resolution PNG of the active monitor.

    Separate from ``vision.screen_capture.capture_screen`` because that one
    encodes JPEG at a size tuned for the vision model. Both grab the same
    monitor the same way; only the encoding differs.
    """
    try:
        import mss
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise CaptureError(
            "Screen capture needs 'mss' and 'Pillow'. "
            "Install them with: pip install mss Pillow"
        ) from exc

    from vision.screen_capture import _monitor_under_cursor

    with mss.mss() as sct:
        _, monitor = _monitor_under_cursor(sct)
        shot = sct.grab(monitor)

    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    # Only shrink a genuinely enormous virtual desktop; a normal 1080p or 4K
    # monitor passes through at native resolution.
    if max(image.size) > OCR_MAX_EDGE:
        scale = OCR_MAX_EDGE / max(image.size)
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.LANCZOS,
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ScreenTextSkill(Skill):
    """Return the exact text visible on the user's screen."""

    name = "ScreenTextSkill"
    description = "Reads the exact text on screen using OCR."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        try:
            png = await asyncio.to_thread(_capture_png)
        except CaptureError as exc:
            return f"I couldn't capture the screen: {exc}"

        try:
            lines = await asyncio.to_thread(_run_ocr, png)
        except ImportError:
            return _INSTALL_HINT
        except Exception as exc:
            logger.exception("OCR failed")
            return f"I couldn't read the screen text: {exc}"

        if not lines:
            return "There is no text I can read on the screen right now."

        truncated = len(lines) > MAX_LINES
        if truncated:
            lines = lines[:MAX_LINES]

        transcript = "\n".join(lines)
        if truncated:
            transcript += f"\n... (only the first {MAX_LINES} lines)"

        return f"Text on screen:\n{transcript}"
