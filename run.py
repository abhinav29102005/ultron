"""
run.py – Unified Launcher for ULTRON Agent
==========================================
Supports three interaction modes:
  1. text       – Terminal text input (default)
  2. no-wake    – Continuous voice listening (no wake word)
  3. wakeword   – Wake word detection followed by voice command

Usage:
  python run.py                 # text mode (default)
  python run.py --mode text     # text mode
  python run.py --mode no-wake  # continuous voice listening
  python run.py --mode wakeword # wake word + voice command
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

from utils.console import force_utf8_output
from utils.env import load_env_file

# Before any output. Researched answers quote scraped pages, so a redirected
# run.py used to mangle every non-ASCII character it printed.
force_utf8_output()

# Makes .env visible to the os.getenv readers (speech config, wake word).
# See utils/env.py -- pydantic parses .env privately and never exports it.
load_env_file()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ultron",
        description="ULTRON – Autonomous AI Desktop Assistant & Streaming Live RAG",
    )
    parser.add_argument(
        "--mode",
        choices=["text", "no-wake", "wakeword"],
        default="text",
        help="Interaction mode: text (default), no-wake, or wakeword",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a custom .env configuration file",
    )
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="Do not start Ollama automatically when it is not running",
    )
    parser.add_argument(
        "--ignore-preflight",
        action="store_true",
        help="Start even when the LLM backend is unavailable (degraded mode)",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    """Bootstrap the application and run the selected mode."""
    # Defer heavy imports
    from config.settings import Settings
    from config.logging_config import configure_logging, get_logger
    from core.container import ServiceContainer
    from utils.cli import CLI
    from utils.preflight import check_llm, report

    logger = get_logger("run")

    CLI.print_startup()

    settings = Settings.load(env_file=args.config)
    configure_logging(settings)

    # Before the mic opens. A dead LLM backend does not stop ULTRON from
    # hearing the user -- it stops ULTRON from understanding them, and the
    # regex fallback that covers for it is convincing enough that the failure
    # looks like bad intent detection instead of a service that is down.
    preflight = check_llm(settings, autostart=not args.no_autostart)
    report(preflight)

    if not preflight.ok and not args.ignore_preflight:
        logger.error("Preflight failed; refusing to start with a degraded LLM.")
        print("  Start anyway with --ignore-preflight.\n")
        sys.exit(1)

    logger.info("Loading configuration...")
    logger.info("Initializing logger...")
    logger.info("Initializing EventBus...")

    container = ServiceContainer(settings)
    await container.initialise()

    logger.info("Creating Assistant...")
    assistant = container.assistant
    assistant.initialize()

    await assistant.start(launch_listen_loop=False)

    mode_runners = {
        "text": run_text_mode,
        "no-wake": run_no_wake_mode,
        "wakeword": run_wakeword_mode,
    }

    runner = mode_runners.get(args.mode)
    if runner:
        await runner(container)
    else:
        logger.error(f"Unknown mode: {args.mode}")
        sys.exit(1)


async def run_text_mode(container) -> None:
    """Run in text input mode (terminal)."""
    from core.state import AssistantState

    assistant = container.assistant
    await assistant.start(launch_listen_loop=True)

    try:
        while assistant.state != AssistantState.SHUTTING_DOWN:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await assistant.stop()
        await container.shutdown()


async def run_no_wake_mode(container) -> None:
    """Run in user-controlled voice listening mode (press Enter to listen, no wake word)."""
    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.speech_to_text.stt_pipeline import SpeechPipeline
    from speech.text_to_speech.tts_pipeline import stop_audio
    from utils.cli import CLI

    assistant = container.assistant
    await assistant.start(launch_listen_loop=False)

    from speech.hold_to_talk import HoldToTalkController
    hold_key = container.settings.hold_to_talk_key if container.settings else "right_shift"
    controller = HoldToTalkController(key_name=hold_key)
    controller.start_listening()

    import uuid

    # Session id for this run; turns increment per user utterance.
    session_id = str(uuid.uuid4())
    turn_id = 0

    try:
        CLI.print_startup()
        print(f"No-Wake mode active. Hold {hold_key} to talk, release to process.\n")
        while assistant.state != AssistantState.SHUTTING_DOWN:
            audio = await asyncio.to_thread(controller.collect_while_held)
            if audio is not None:
                stop_audio()
                CLI.print_processing()
                # Use a quick STT on the captured audio. Stream partial
                # transcript chunks (timestamped) for early-retrieval experiments
                # while still delivering the final utterance as a single event.
                from speech.speech_to_text.transcriber import Transcriber
                from speech.stt_stream import STTStreamer

                transcriber = Transcriber()
                streamer = STTStreamer(transcriber)

                final_text = ""
                try:
                    # New utterance -> increment turn id and mark active
                    turn_id += 1
                    container.cancellation_manager.set_active_turn(session_id, turn_id)

                    async for chunk in streamer.stream_from_audio(audio, chunk_words=8):
                        # Publish incremental partials so downstream controllers
                        # can react before the whole utterance is complete.
                        await container.event_bus.publish(
                            UserInputEvent(
                                text=chunk["text"],
                                source="voice_partial",
                                session_id=session_id,
                                turn_id=turn_id,
                            )
                        )
                        final_text = chunk["text"]
                except Exception:
                    # Best-effort: fall back to a single-shot transcription
                    try:
                        final_text = Transcriber().transcribe(audio)
                    except Exception:
                        final_text = ""

                if final_text.strip():
                    CLI.print_user_input(final_text)
                    await container.event_bus.publish(
                        UserInputEvent(
                            text=final_text,
                            source="voice",
                            session_id=session_id,
                            turn_id=turn_id,
                        )
                    )
    except asyncio.CancelledError:
        pass
    finally:
        controller.stop_listening()
        await assistant.stop()
        await container.shutdown()


async def run_wakeword_mode(container) -> None:
    """Run in wake word mode (wake word + voice command)."""
    # Said before the import, not after: pulling in openWakeWord drags in
    # sklearn and scipy, which measured 66-114s on a Windows laptop. Without
    # this line the CLI sits silent for over a minute on its way to the first
    # "Waiting for wake word" and looks wedged.
    print("Loading wake-word engine (first run can take a minute)…", flush=True)

    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.wake_word.detector import WakeWordDetector
    from speech.speech_to_text.stt_pipeline import SpeechPipeline
    from utils.cli import CLI

    assistant = container.assistant
    await assistant.start(launch_listen_loop=False)

    wake_detector = WakeWordDetector()
    pipeline = SpeechPipeline()

    try:
        while assistant.state != AssistantState.SHUTTING_DOWN:
            print("🔍 Waiting for wake word...")

            heard = await asyncio.to_thread(wake_detector.detect)
            if not heard:
                continue

            print("✅ Wake word detected!")
            CLI.print_listening()

            text = await asyncio.to_thread(pipeline.listen)

            if text.strip():
                # Wake-word interactions are their own turns.
                import uuid as _uuid

                turn_id += 1
                container.cancellation_manager.set_active_turn(session_id, turn_id)

                CLI.print_user_input(text)
                await container.event_bus.publish(
                    UserInputEvent(
                        text=text,
                        source="voice",
                        session_id=session_id,
                        turn_id=turn_id,
                    )
                )
    except asyncio.CancelledError:
        pass
    finally:
        wake_detector.stop()
        pipeline.stop()
        await assistant.stop()
        await container.shutdown()


def main() -> None:
    args = parse_args()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(run(args))

    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        from utils.cli import CLI

        CLI.print_shutdown()
        main_task.cancel()
        try:
            loop.run_until_complete(main_task)
        except asyncio.CancelledError:
            pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()