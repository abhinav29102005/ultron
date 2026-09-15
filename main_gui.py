"""
main_gui.py – PyQt Desktop Entry Point for ULTRON
==================================================
Separate launcher from main.py. Boots the same ServiceContainer/Assistant,
but runs inside a Qt event loop (via qasync) and shows MainWindow instead
of listening on the terminal.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Auto-trampoline to .venv Python if invoked via system Python
_repo_root = Path(__file__).resolve().parent
_venv_python = _repo_root / ".venv" / "Scripts" / "python.exe"
if not _venv_python.exists():
    _venv_python = _repo_root / ".venv" / "bin" / "python"
if _venv_python.exists() and Path(sys.executable).resolve() != _venv_python.resolve():
    sys.exit(subprocess.call([str(_venv_python)] + sys.argv))

from PyQt6.QtWidgets import QApplication, QMessageBox
import qasync

from config.settings import Settings
from config.logging_config import configure_logging, get_logger
from core.container import ServiceContainer
from ui.main_window import MainWindow
from utils.console import force_utf8_output
from utils.env import load_env_file
from utils.single_instance import SingleInstance


# Shared with run.py and main.py; see utils/console.py for why this has to
# happen before anything writes to stdout.
force_utf8_output()

# Makes .env visible to the os.getenv readers (speech config, wake word).
# See utils/env.py -- pydantic parses .env privately and never exports it.
load_env_file()

logger = get_logger("boot_gui")


async def run(app: QApplication) -> None:
    # Printed before anything slow. Preflight only speaks up when something is
    # wrong and the rest of boot logs to file, so a healthy start used to
    # produce no console output at all -- leaving "it is working" and "it is
    # hung" looking identical from the terminal.
    print("[ULTRON] Starting…", flush=True)

    settings = Settings.load()
    configure_logging(settings)

    # Ollama serves both intent detection and the vision model, and when it is
    # not running neither fails loudly -- the assistant just starts answering
    # from its regex fallback. Start it here, before anything asks it a
    # question. The GUI does not exit on failure the way run.py does: a window
    # that vanishes tells the user nothing, so the problem is logged and the
    # app comes up degraded but visible.
    from utils.preflight import check_llm, report

    preflight = await asyncio.to_thread(check_llm, settings)
    report(preflight)
    if not preflight.ok:
        for problem in preflight.problems:
            logger.error(f"Preflight: {problem}")

    container = ServiceContainer(settings)
    await container.initialise()

    assistant = container.assistant
    assistant.initialize()

    # GUI mode: skip the terminal input() loop entirely
    await assistant.start(launch_listen_loop=False)

    # STT (Whisper) takes ~90s to build, and importing the wake-word detector
    # pulls in openWakeWord -> sklearn -> scipy, measured at 66-114s here.
    # Show the window FIRST, then build both on worker threads — doing either
    # before the first paint blocks the Qt event loop, and the app spends over
    # a minute with no window and nothing on stdout, which reads as "it does
    # not start" rather than "it is loading".
    window = MainWindow(container.event_bus, container.recorder, None, None, container)
    window.show()

    async def _load_wake_detector() -> None:
        def _build():
            # Imported inside the thread: the import is the slow part, not
            # the constructor.
            from speech.wake_word.detector import WakeWordDetector

            return WakeWordDetector()

        try:
            detector = await asyncio.to_thread(_build)
        except Exception as exc:  # wake word is optional: the mic button works
            logger.exception("Failed to load wake-word detector")
            window.set_wake_detector(None, error=str(exc))
            return
        window.set_wake_detector(detector)

    asyncio.ensure_future(_load_wake_detector())

    async def _load_stt() -> None:
        try:
            transcriber = await asyncio.to_thread(lambda: container.stt)
        except Exception as exc:  # STT is optional: typing must keep working
            logger.exception("Failed to load speech-to-text")
            window.set_stt(None, error=str(exc))
            return
        window.set_stt(transcriber)
        logger.info("Speech-to-text ready")

    asyncio.ensure_future(_load_stt())

    # The vision model is 3+ GB and Ollama evicts it after five minutes idle,
    # so without this the first screen question — and every one after a quiet
    # spell — pays a cold load from disk before it can look at anything.
    # Fire-and-forget for the same reason as STT: that load is tens of seconds
    # and awaiting it here would hold up the first paint.
    if getattr(container.settings, "vision_preload", False):
        from vision.vision_client import preload

        asyncio.ensure_future(
            preload(
                container.settings.vision_model,
                container.settings.ollama_base_url,
                container.settings.vision_keep_alive,
            )
        )

    # Keep this coroutine alive until the window/app closes
    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)
    await close_event.wait()

    await close_event.wait()

    os._exit(0)  # hard-kill: skip graceful shutdown for now, background threads won't block exit


#: Module-level, and that is load-bearing. The mutex lives exactly as long as
#: the object holding its handle: a local in main() would be collected on the
#: way out of the function and the guard would end while ULTRON was still
#: running. Nothing ever calls release() -- run() finishes with os._exit(0),
#: which skips finalizers, and the OS drops the mutex when the process dies
#: however it dies. That is the whole reason this is a kernel object rather
#: than a lockfile; see utils/single_instance.py.
_instance_lock: SingleInstance | None = None


def main() -> None:
    global _instance_lock

    app = QApplication(sys.argv)

    # After QApplication exists, so the dialog below can actually be shown.
    # The launcher runs under pythonw with no console at all, so a print on
    # its own would be invisible -- which is how four copies came to be
    # running at once in the first place.
    _instance_lock = SingleInstance()
    if not _instance_lock.acquired:
        print("[ULTRON] Already running - look for the orb or the tray icon.", flush=True)
        QMessageBox.information(
            None,
            "ULTRON",
            "ULTRON is already running.\n\nLook for the orb, or the tray icon.",
        )
        return

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        loop.run_until_complete(run(app))


if __name__ == "__main__":
    main()