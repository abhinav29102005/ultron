"""
utils/console.py – Console Encoding
====================================
One copy of the stdout/stderr UTF-8 fix that every entry point needs.

Why this module exists
----------------------
A redirected stream on Windows falls back to the legacy code page (cp1252
here) rather than UTF-8. Interactive consoles happen to work; piping to a file
or another process does not, and the text arrives mangled -- an em dash
becomes a replacement character, and on some Python builds the write raises
UnicodeEncodeError outright.

main.py and main_gui.py each carried their own copy of this function.
run.py -- the documented CLI launcher -- carried none, so `python run.py
--mode wakeword > log.txt` corrupted every non-ASCII character. That went
unnoticed while replies were short ASCII confirmations ("Chrome opened
successfully."); researched answers quote scraped web pages, so non-ASCII is
now the common case rather than the exception.
"""

from __future__ import annotations

import sys


def force_utf8_output() -> None:
    """Make stdout/stderr UTF-8 regardless of the active Windows code page.

    Safe to call more than once, and a no-op on streams that predate
    ``reconfigure`` or have been replaced by something without it (pytest's
    capture objects, for instance).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # A detached or already-closed stream is not a reason to stop the
            # program before it has started.
            continue
