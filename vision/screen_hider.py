"""
vision/screen_hider.py – Screen-share privacy and recording control
===================================================================
On Windows, SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE removes
a window from every capture path the OS offers (OBS, Game Bar, Meet, Zoom,
Teams, Snipping Tool, BitBlt, DWM duplication) while leaving it fully visible
on the physical display.

When recording ULTRON (via OBS, Windows Game Bar, or scripts), capture exclusion
MUST be disabled so the orb is visible in the recording.

We support:
- hide_from_capture(widget): applies WDA_EXCLUDEFROMCAPTURE (0x11)
- allow_capture(widget): explicitly restores WDA_NONE (0x00) so recording works
- Environment variable ULTRON_ALLOW_CAPTURE=1 or ULTRON_RECORDING=1 to disable hiding
"""

from __future__ import annotations

import os
import platform
import sys

from config.logging_config import get_logger

logger = get_logger("vision.hider")

#: Window is visible to all screen capture (standard Windows behavior).
WDA_NONE = 0x00000000

#: Excluded from capture entirely; the window is absent, not blacked out.
WDA_EXCLUDEFROMCAPTURE = 0x00000011

#: First Windows build with WDA_EXCLUDEFROMCAPTURE (Windows 10 2004).
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


def is_capture_allowed_env() -> bool:
    """Check if screen capture has been explicitly permitted via env."""
    val = os.getenv("ULTRON_ALLOW_CAPTURE", "").lower()
    rec = os.getenv("ULTRON_RECORDING", "").lower()
    return val in ("1", "true", "yes", "on") or rec in ("1", "true", "yes", "on")


def allow_capture(widget) -> bool:
    """Explicitly re-enable screen capture for this window on Windows."""
    if sys.platform != "win32":
        return True

    try:
        import ctypes

        handle = int(widget.winId())
        if not handle:
            return False

        user32 = ctypes.windll.user32
        ok = bool(
            user32.SetWindowDisplayAffinity(
                ctypes.c_void_p(handle),
                ctypes.c_uint(WDA_NONE),
            )
        )
        if ok:
            logger.debug("Window {} capture enabled (WDA_NONE applied).", handle)
        return ok
    except Exception as exc:
        logger.warning("Failed to set WDA_NONE on window: {}", exc)
        return False


def hide_from_capture(widget) -> bool:
    """Exclude a Qt widget's window from screen capture.

    Returns True when the exclusion was applied. Never raises: failing to hide
    is a downgrade in privacy, not a reason to refuse to start.

    If ULTRON_ALLOW_CAPTURE or ULTRON_RECORDING is set, capture exclusion is
    skipped and allow_capture is called instead so the orb can be recorded.
    """
    if is_capture_allowed_env() or getattr(widget, "_allow_capture", False):
        logger.info("Screen recording active/allowed: skipping capture exclusion.")
        allow_capture(widget)
        return False

    if not is_hiding_supported():
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
