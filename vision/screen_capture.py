"""
vision/screen_capture.py – Grab the screen for a vision model
=============================================================
The image goes to a 3B vision model running on the CPU, so size is the whole
game: a raw 4K PNG costs seconds of encode time and thousands of image tokens
without telling the model anything a 1280px JPEG does not.

Capture targets the monitor under the mouse pointer, which is the one the user
is looking at. ULTRON's own window never appears in the result — not because
this module filters it, but because ``screen_hider`` marks it excluded from
capture at the OS level, which applies to us exactly as it applies to Zoom.
"""

from __future__ import annotations

import asyncio
import io
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from config.logging_config import get_logger

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

logger = get_logger("vision.capture")

#: Longest edge of the image handed to the model.
#:
#: Every pixel above this is decode time, not detail. A 3B VLM tiles the image
#: into 28px patches, so 1280px costs roughly twice the vision tokens of 896px
#: and reads the same UI text either way — on a CPU that difference is seconds.
#: Override per-call, or through ``VISION_MAX_EDGE``.
MAX_EDGE = 896

#: JPEG quality. 75 is the point where UI text stays readable and the payload
#: stops shrinking usefully.
JPEG_QUALITY = 75


class CaptureError(RuntimeError):
    """Raised when the screen could not be captured."""


@dataclass(frozen=True)
class Capture:
    """One screenshot, ready to send."""

    jpeg: bytes
    width: int
    height: int
    monitor_index: int

    def __len__(self) -> int:
        return len(self.jpeg)


def _cursor_position() -> tuple[int, int] | None:
    """The pointer's position in *physical* pixels, or None if unknown.

    This has to match the coordinate space ``mss`` reports monitors in, which
    is physical. Qt's ``QCursor.pos()`` is in logical pixels, so at 125%
    scaling it returns 1600 for a cursor physically at 2000 — which lands in
    the first monitor's range and captures the wrong screen entirely.

    Win32 ``GetCursorPos`` is already physical (the process is per-monitor DPI
    aware under Qt6), so it is preferred where available.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            point = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return int(point.x), int(point.y)
        except Exception as exc:
            logger.debug("GetCursorPos unavailable: {}", exc)

    try:
        from PyQt6.QtGui import QCursor, QGuiApplication

        # Without a QApplication, QCursor.pos() does not raise — it returns a
        # sentinel far outside any real desktop. The headless entry point
        # (run.py) has no Qt application at all, so this is a live path.
        if QGuiApplication.instance() is None:
            return None

        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen is not None else 1.0
        return int(pos.x() * ratio), int(pos.y() * ratio)
    except Exception as exc:
        logger.debug("Cursor position unavailable: {}", exc)
        return None


def _monitor_under_cursor(sct) -> tuple[int, dict]:
    """The monitor the pointer is on, falling back to the primary one.

    ``sct.monitors[0]`` is the union of every display. Sending that on a
    multi-monitor setup gives the model a very wide, very short image in which
    nothing is legible, so a specific monitor is always chosen.
    """
    monitors = sct.monitors
    # With one entry there is no separate union to avoid; index 0 is the only
    # display there is.
    primary = (1, monitors[1]) if len(monitors) > 1 else (0, monitors[0])

    position = _cursor_position()
    if position is None:
        return primary
    x, y = position

    for index, monitor in enumerate(monitors):
        if index == 0:
            continue  # the union, never a real display
        if (
            monitor["left"] <= x < monitor["left"] + monitor["width"]
            and monitor["top"] <= y < monitor["top"] + monitor["height"]
        ):
            return index, monitor

    return primary


def _downscale(image: PILImage, max_edge: int) -> PILImage:
    """Shrink ``image`` so its longest edge is ``max_edge``, cheaply.

    One LANCZOS pass over a 4K frame measured ~110 ms here, and it runs on the
    thread the assistant is waiting on. ``reduce()`` is an integer box filter —
    a proper area average, and the fast path — so it does the bulk of the
    shrink, leaving only the fractional remainder for a real resampler. Same
    output size, measured at 8-17 ms, with no loss visible on UI text.
    """
    from PIL import Image

    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image

    factor = int(longest // max_edge)
    if factor >= 2:
        image = image.reduce(factor)
        width, height = image.size
        longest = max(width, height)

    if longest <= max_edge:
        return image

    scale = max_edge / longest
    return image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.BICUBIC,
    )


def capture_screen(max_edge: int = MAX_EDGE, quality: int = JPEG_QUALITY) -> Capture:
    """Capture the active monitor as a downscaled JPEG.

    Raises :class:`CaptureError` when the screen cannot be read, so callers
    can say something useful instead of showing a traceback.

    This blocks — the grab, the resize and the encode are all CPU work. Async
    callers want :func:`capture_screen_async` instead.
    """
    try:
        import mss
    except ImportError as exc:
        raise CaptureError(
            "Screen capture needs the 'mss' package. Install it with: pip install mss"
        ) from exc

    try:
        from PIL import Image
    except ImportError as exc:
        raise CaptureError(
            "Screen capture needs Pillow. Install it with: pip install Pillow"
        ) from exc

    # mss 10 renamed the factory and deprecated the old spelling; the old name
    # still works but warns on every capture, which would fill the log.
    factory = getattr(mss, "MSS", None) or mss.mss

    try:
        with factory() as sct:
            index, monitor = _monitor_under_cursor(sct)
            raw = sct.grab(monitor)
            image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    except CaptureError:
        raise
    except Exception as exc:
        raise CaptureError(f"Could not read the screen: {exc}") from exc

    image = _downscale(image, max_edge)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    jpeg = buffer.getvalue()

    logger.debug(
        "Captured monitor %d at %dx%d (%d KB).",
        index,
        image.width,
        image.height,
        len(jpeg) // 1024,
    )
    return Capture(
        jpeg=jpeg,
        width=image.width,
        height=image.height,
        monitor_index=index,
    )


def encode_image(
    data: bytes,
    max_edge: int = MAX_EDGE,
    quality: int = JPEG_QUALITY,
) -> Capture:
    """Put an image the user supplied through the same pipeline as a capture.

    A screenshot pasted into the chat panel arrives as full-resolution PNG,
    which is the right form for OCR and the wrong one for the vision model —
    exactly the size problem this module exists to solve. Reusing
    :func:`_downscale` and the same JPEG settings means the VLM sees one kind
    of image whatever the source, so its behaviour does not depend on where
    the picture came from.

    ``monitor_index`` is -1: nothing was captured, and pretending a pasted
    image came from a display would be a lie a caller might act on.

    Raises :class:`CaptureError` for bytes Pillow cannot open, so callers can
    reuse the handling they already have for a failed grab.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise CaptureError(
            "Reading a pasted image needs Pillow. Install it with: pip install Pillow"
        ) from exc

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise CaptureError(f"I couldn't read that image: {exc}") from exc

    image = _downscale(image, max_edge)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)

    return Capture(
        jpeg=buffer.getvalue(),
        width=image.width,
        height=image.height,
        monitor_index=-1,
    )


async def capture_screen_async(
    max_edge: int = MAX_EDGE,
    quality: int = JPEG_QUALITY,
) -> Capture:
    """:func:`capture_screen`, off the event loop.

    The grab, the downscale and the JPEG encode are tens of milliseconds of
    straight CPU work. Run from a coroutine they stall the whole loop, which
    here means speech recognition, playback and the orb all freeze mid-answer.
    ``to_thread`` costs nothing by comparison: PIL and mss both release the GIL
    for the expensive parts.

    :class:`CaptureError` propagates unchanged.
    """
    return await asyncio.to_thread(capture_screen, max_edge, quality)
