"""
scripts/ultron_launcher.pyw – Boot-time GUI launcher for ultron
===============================================================
Started by the autostart registry entry written by :mod:`utils.autostart`::

    "<repo>\\.venv\\Scripts\\pythonw.exe" "<repo>\\scripts\\ultron_launcher.pyw"

It exists for two reasons that a direct ``pythonw.exe main_gui.py`` cannot cover:

1. **Working directory.** At login Windows starts the process in
   ``C:\\Windows\\system32``, not in the repository. Any relative path in the
   codebase would resolve against the wrong directory -- this project has
   already been bitten by exactly that (a relative memory path). This script
   chdir's to the repository root before importing anything from the app.

2. **Error visibility.** ``pythonw.exe`` has no console, so a traceback on
   startup would vanish silently and ultron would just "not come up" with no
   explanation. Anything that escapes is written to
   ``<repo>/logs/autostart_launcher.log`` instead.

Run it by hand to reproduce exactly what happens at boot::

    .venv\\Scripts\\pythonw.exe scripts\\ultron_launcher.pyw

To verify without the GUI subsystem swallowing output, use ``python.exe``:

    .venv\\Scripts\\python.exe scripts\\ultron_launcher.pyw
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "logs" / "autostart_launcher.log"


def _log_failure(exc: BaseException) -> None:
    """Record a startup failure where a user can actually find it."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== autostart failure {datetime.now().isoformat()} =====\n")
            handle.write(f"python : {sys.executable}\n")
            handle.write(f"cwd    : {os.getcwd()}\n")
            handle.write("".join(traceback.format_exception(exc)))
    except Exception:
        # Nothing useful left to do -- never let logging itself crash the boot.
        pass


def main() -> int:
    # 1. Make the repo the working directory so relative paths behave as they do
    #    when launched from a shell inside the project.
    os.chdir(REPO_ROOT)

    # 2. Make the repo importable. sys.path[0] is scripts/ when this file is the
    #    entry point, so the app's top-level packages would not otherwise resolve.
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from main_gui import main as gui_main  # noqa: PLC0415 - after path setup
        gui_main()
    except BaseException as exc:  # noqa: BLE001 - last line of defence at boot
        _log_failure(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
