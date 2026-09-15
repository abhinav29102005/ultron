"""
main.py – ULTRON AI Desktop Assistant Bootstrapper
===================================================
Entry point for the application. Sets up DI container and boots the assistant.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import argparse
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

from config.settings import Settings
from config.logging_config import configure_logging, get_logger
from core.container import ServiceContainer
from utils.cli import CLI
from utils.console import force_utf8_output
from utils.env import load_env_file


# Shared with run.py and main_gui.py; see utils/console.py for why this has to
# happen before anything writes to stdout.
force_utf8_output()

# Makes .env visible to the os.getenv readers (speech config, wake word).
# See utils/env.py -- pydantic parses .env privately and never exports it.
load_env_file()

# Setup initial bootstrapped logger
logger = get_logger("boot")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="ultron",
        description="ULTRON – Autonomous AI Desktop Assistant & Streaming Live RAG",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a custom .env configuration file",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    """
    Bootstrap the application services and transition assistant to IDLE.
    """
    # 1. Print the startup banner
    CLI.print_startup()

    # Load configuration and configure logging
    settings = Settings.load(env_file=args.config)
    configure_logging(settings)

    # See utils/preflight.py: a stopped Ollama does not stop ULTRON from
    # hearing the user, only from understanding them, so it has to be checked
    # explicitly rather than discovered one wrong answer at a time.
    from utils.preflight import check_llm, report

    preflight = check_llm(settings)
    report(preflight)
    if not preflight.ok:
        sys.exit(1)

    # 2. Loading configuration log
    logger.info("Loading configuration…")

    # 3. Initializing logger log
    logger.info("Initializing logger…")

    # 4. Initializing EventBus log
    logger.info("Initializing EventBus…")
    container = ServiceContainer(settings)
    await container.initialise()

    # 5. Creating Assistant log
    logger.info("Creating Assistant…")
    assistant = container.assistant
    assistant.initialize()

    # 6. Start Assistant (transitions to IDLE)
    await assistant.start()

    # Allow async log flush
    await asyncio.sleep(0.05)

    # Sleep forever until KeyboardInterrupt

    # Sleep forever until KeyboardInterrupt
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        # Graceful stop on cancellation
        await assistant.stop()
        await container.shutdown()


def main() -> None:
    """
    Synchronous entry point.
    """
    args = parse_args()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    main_task = loop.create_task(run(args))
    
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        CLI.print_shutdown()
        # Stop main run loop gracefully on Ctrl+C
        main_task.cancel()
        try:
            loop.run_until_complete(main_task)
        except asyncio.CancelledError:
            pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
