"""
vision/screen_hider.py – Keep ULTRON out of screen shares
=========================================================
``SetWindowDisplayAffinity`` with ``WDA_EXCLUDEFROMCAPTURE`` removes a window
from every capture path the OS offers — Google Meet, Zoom, Teams, OBS, the
Snipping Tool, BitBlt, DWM duplication — while leaving it fully visible on the
physical display. That is exactly the asymmetry we want: the user sees the orb,
the meeting does not.

Two things follow from doing this at the OS level rather than by filtering our
own screenshots:

* it holds for capture software we have never heard of, and
* our own ``screen_capture`` cannot see ULTRON either, so the vision model is
  never shown a picture of the assistant asking about the picture.

Requires Windows 10 version 2004 (build 19041) or newer. The older
``WDA_MONITOR`` is deliberately *not* used as a fallback: it paints the window
black on the shared screen, which is more conspicuous than simply appearing.
Anywhere unsupported this is a logged no-op — vision still works, the window
is merely visible to a screen share.
"""

from __future__ import annotations

import platform
import sys

from config.logging_config import get_logger

logger = get_logger("vision.hider")

#: Excluded from capture entirely; the window is absent, not blacked out.
WDA_EXCLUDEFROMCAPTURE = 0x00000011

#: First Windows build with WDA_EXCLUDEFROMCAPTURE.
MIN_WINDOWS_BUILD = 19041

_warned = False


def _windows_build() -> int:
    """Current Windows build number, or 0 when it cannot be determined."""
    try:
        version = platform.version()  # e.g. "10.0.26200"
        return int(version.split(".")[2])
    except Exception:
        return 0


def is_hiding_supported() -> bool:
    """Whether this machine can exclude a window from capture."""
    if sys.platform != "win32":
        return False
    return _windows_build() >= MIN_WINDOWS_BUILD


def _explain_once() -> None:
    global _warned
    if _warned:
        return
    _warned = True
    if sys.platform != "win32":
        logger.info(
            "Screen-share hiding is Windows-only; the window will be visible "
            "to screen capture on this platform."
        )
    else:
        logger.warning(
            "Screen-share hiding needs Windows 10 build %d or newer (this is "
            "build %d); the window will be visible to screen capture.",
            MIN_WINDOWS_BUILD,
            _windows_build(),
        )


def hide_from_capture(widget) -> bool:
    """Exclude a Qt widget's window from screen capture.

    Returns True when the exclusion was applied. Never raises: failing to hide
    is a downgrade in privacy, not a reason to refuse to start.

    Call this after the window exists natively, and again from ``showEvent``:
    Qt destroys and recreates the native handle when window flags change, and
    the affinity is a property of the handle, not of the widget.
    """
    if not is_hiding_supported():
        _explain_once()
        return False

    try:
        import ctypes

        handle = int(widget.winId())
        if not handle:
            logger.debug("No native window handle yet; nothing to hide.")
            return False

        user32 = ctypes.windll.user32
        ok = bool(
            user32.SetWindowDisplayAffinity(
                ctypes.c_void_p(handle),
                ctypes.c_uint(WDA_EXCLUDEFROMCAPTURE),
            )
        )
        if ok:
            logger.debug("Window {} excluded from screen capture.", handle)
        else:
            error = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else "?"
            logger.warning(
                "SetWindowDisplayAffinity refused the window (error %s); it "
                "will be visible to screen capture.",
                error,
            )
        return ok
    except Exception as exc:
        logger.warning("Could not hide the window from screen capture: {}", exc)
        return False
