"""
vision – Looking at the screen, and staying out of screen shares
================================================================
Two independent pieces:

``screen_capture``
    Grabs the screen as a JPEG small enough for a local vision model.

``screen_hider``
    Marks FRIDAY's own windows as excluded from capture, so a screen share
    shows the user's desktop without the assistant on top of it.

Both degrade rather than raise: a missing dependency or an unsupported
platform costs one feature, not the assistant.
"""

from vision.screen_capture import CaptureError, capture_screen
from vision.screen_hider import hide_from_capture, is_hiding_supported

__all__ = [
    "CaptureError",
    "capture_screen",
    "hide_from_capture",
    "is_hiding_supported",
]
