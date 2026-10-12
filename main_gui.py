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
from utils.gui_recorder import GuiRecorder
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


async def _demo_sequence(window: MainWindow, recorder: GuiRecorder, app: QApplication) -> None:
    logger.info("[DEMO] Initiating automated feature walkthrough sequence...")
    await asyncio.sleep(2.5)

    # 1. Standby floating Orb
    logger.info("[DEMO] State: IDLE (Mode: ORB)")
    window.collapse()
    window._apply_state("IDLE")
    await asyncio.sleep(2.0)

    # 2. Trigger listening waveform Pill
    logger.info("[DEMO] State: LISTENING (Mode: PILL with waveform)")
    window._apply_state("LISTENING")
    await asyncio.sleep(2.5)

    # 3. Expand to Card
    logger.info("[DEMO] Expanding to Card mode")
    window.expand()
    await asyncio.sleep(1.2)

    # 4. Hello Ultron
    logger.info("[DEMO] Submitting: Hello Ultron")
    window._on_message_submitted("Hello Ultron")
    await asyncio.sleep(5.0)

    # 5. Weather of Patiala
    logger.info("[DEMO] Submitting: What is the weather of Patiala?")
    window._on_message_submitted("What is the weather of Patiala?")
    await asyncio.sleep(6.0)

    # 6. MLSC TIET inquiry
    logger.info("[DEMO] Submitting: Tell me about MLSC TIET at Thapar University and share official links")
    window._on_message_submitted("Tell me about MLSC TIET at Thapar University and share official links")
    await asyncio.sleep(7.0)

    # 7. System volume control
    logger.info("[DEMO] Submitting: Set system volume to 80%")
    window._on_message_submitted("Set system volume to 80%")
    await asyncio.sleep(5.0)

    # 8. Collapse back to Orb
    logger.info("[DEMO] Collapsing back to standby Orb")
    window.collapse()
    window._apply_state("IDLE")
    await asyncio.sleep(2.5)

    # 9. Stop recording and exit
    logger.info("[DEMO] Demo complete! Finalizing recording and exiting.")
    recorder.stop()
    app.quit()


async def run(app: QApplication, record: bool = False, demo: bool = False, output_file: str = "ultron_gui_demo.mp4", fps: int = 25) -> None:
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

    gui_recorder = None
    if record or demo:
        os.environ["ULTRON_RECORDING"] = "1"
        os.environ["ULTRON_ALLOW_CAPTURE"] = "1"
        gui_recorder = GuiRecorder(window, output_path=output_file, fps=fps)
        gui_recorder.start()
        app.aboutToQuit.connect(gui_recorder.stop)
        if demo:
            asyncio.ensure_future(_demo_sequence(window, gui_recorder, app))

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

    import argparse
    parser = argparse.ArgumentParser(description="ULTRON Desktop GUI")
    parser.add_argument("--allow-capture", action="store_true", default=True, help="Allow the orb and UI to be visible to screen recorders (OBS, Game Bar) on Windows (default: True)")
    parser.add_argument("--hide-from-capture", action="store_true", help="Explicitly hide the orb from screen recording/screen sharing on Windows")
    parser.add_argument("--record", action="store_true", help="Record the GUI session to video")
    parser.add_argument("--demo", action="store_true", help="Run automated feature demonstration and record video")
    parser.add_argument("--output", default="ultron_gui_demo.mp4", help="Output video path (.mp4 / .webm)")
    parser.add_argument("--fps", type=int, default=25, help="Frame rate for recording (default: 25)")
    args, _ = parser.parse_known_args()

    if args.hide_from_capture:
        os.environ.pop("ULTRON_ALLOW_CAPTURE", None)
    elif args.allow_capture or args.record or args.demo:
        os.environ["ULTRON_ALLOW_CAPTURE"] = "1"

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
        loop.run_until_complete(run(app, record=args.record, demo=args.demo, output_file=args.output, fps=args.fps))


if __name__ == "__main__":
    main()