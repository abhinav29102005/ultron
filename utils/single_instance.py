"""
utils/single_instance.py – One FRIDAY at a time
================================================
Four copies of ``main_gui.py`` were found running at once. Nothing stopped a
second launch, and closing the orb hides it to the tray rather than quitting
-- so every "let me just start it again" quietly stacked another instance.
Each one then answered every wake word: "open youtube" opened a tab per
instance and every reply came back in chorus. The user reported that as two
bugs ("it opens tabs twice", "two voices are speaking"); this module is the
fix for both.

A named kernel mutex rather than a lockfile, deliberately. The stale
instances were cleaned up with Stop-Process, and a lockfile survives its
holder's death -- the next launch would find the file, conclude FRIDAY is
already running, and refuse to start until someone hunts the file down. A
kernel object is released by the OS the moment the holding process dies, no
matter how it dies.

Off Windows there is no CreateMutex; the guard degrades to always-acquired
rather than importing a POSIX equivalent nobody runs. FRIDAY's GUI is a
Windows app.
"""

from __future__ import annotations

import ctypes
import sys

from config.logging_config import get_logger

logger = get_logger("single_instance")

#: The GUI's mutex name. ``Local\`` scopes it to this login session: two
#: different users on one machine may each run their own FRIDAY.
GUI_LOCK_NAME = "friday-agent-gui"

_ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Holds a named mutex for the life of the process.

    ``acquired`` is the whole interface: True means this is the only holder
    and the caller should start normally; False means another FRIDAY already
    owns the name and the caller should say so and exit.
    """

    def __init__(self, name: str = GUI_LOCK_NAME) -> None:
        self._handle = None
        self._acquired = False

        if sys.platform != "win32":
            self._acquired = True
            return

        kernel32 = ctypes.windll.kernel32
        # CreateMutexW returns a handle even when the mutex already exists;
        # the already-exists fact arrives via GetLastError. Both must be read
        # before anything else touches the error state.
        handle = kernel32.CreateMutexW(None, False, f"Local\\{name}")
        already_exists = kernel32.GetLastError() == _ERROR_ALREADY_EXISTS

        if not handle:
            # Could not even create the object. Refusing to start over a
            # bookkeeping failure would be worse than the duplicate it
            # guards against, so fail open and log it.
            logger.warning("Could not create the single-instance mutex; not guarding.")
            self._acquired = True
            return

        if already_exists:
            # Someone else holds the name. Release our reference to it: we
            # are about to exit, and keeping a handle to another process's
            # mutex serves nothing.
            kernel32.CloseHandle(handle)
            return

        self._handle = handle
        self._acquired = True

    @property
    def acquired(self) -> bool:
        return self._acquired

    def release(self) -> None:
        """Let go explicitly. Idempotent; the OS does this on exit anyway."""
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        self._acquired = False
