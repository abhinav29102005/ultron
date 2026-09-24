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

# Suppress noisy HuggingFace Hub symlinks warning on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Makes .env visible to the os.getenv readers (speech config, wake word).
# See utils/env.py -- pydantic parses .env privately and never exports it.
load_env_file()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ultron",
        description="ULTRON – Autonomous AI Desktop Assistant & Streaming Live RAG",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="ULTRON v0.2.0 – Autonomous AI Desktop Assistant & Streaming Live RAG",
        help="Show Ultron version information and exit",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        choices=["upgrade", "update", "setup", "keys", "hub", None],
        help="Subcommand to execute: 'upgrade' (update Ultron to latest release), 'setup', or 'hub'",
    )
    parser.add_argument(
        "--mode",
        choices=["text", "no-wake", "wakeword", "continuous"],
        default="text",
        help="Interaction mode: text (default), no-wake, wakeword, or continuous",
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
        if args.mode == "text":
            from utils.api_key_manager import prompt_first_run_if_needed
            from rich.console import Console
            Console().print("\n[yellow]Launching interactive key setup or offline configuration...[/yellow]\n")
            await prompt_first_run_if_needed()
            # Reload settings in case keys were saved to .env
            settings = Settings.load(env_file=args.config)
            preflight = check_llm(settings, autostart=not args.no_autostart)
            if not preflight.ok:
                Console().print("[dim]Starting CLI. Use [bold cyan]/setup[/bold cyan] to add keys or [bold cyan]/mode offline[/bold cyan] anytime.[/dim]\n")
        else:
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
        "continuous": run_continuous_mode,
    }

    runner = mode_runners.get(args.mode)
    if runner:
        await runner(container)
    else:
        logger.error(f"Unknown mode: {args.mode}")
        sys.exit(1)


async def run_in_session_no_wake_loop(container, cli, turn_meta: dict) -> None:
    """Run interactive push-to-talk loop directly within the active session."""
    import asyncio
    import time
    from rich.console import Console
    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.hold_to_talk import HoldToTalkController
    from speech.speech_to_text.transcriber import Transcriber
    from speech.text_to_speech.tts_pipeline import stop_audio
    from utils.cli import CLI

    hold_key = container.settings.hold_to_talk_key if container.settings else "right_shift"
    controller = HoldToTalkController(key_name=hold_key)
    controller.start_listening()
    transcriber = Transcriber()

    Console().print(f"\n[bold bright_magenta]🎙️  PUSH-TO-TALK MODE ACTIVATED[/bold bright_magenta]")
    Console().print(f"[dim]Hold [bold bright_white]{hold_key}[/bold bright_white] to talk, release to send.[/dim]")
    if hasattr(container, "user_settings") and container.user_settings:
        container.user_settings.voice_enabled = True

    sess = container.session_manager.active_session
    sess_id = sess.id if sess else "main"
    turn_id = 0

    try:
        while container.assistant.state != AssistantState.SHUTTING_DOWN:
            audio = await asyncio.to_thread(controller.collect_while_held)
            if audio is not None:
                stop_audio()
                CLI.print_processing()
                text = await asyncio.to_thread(transcriber.transcribe, audio)
                text = (text or "").strip()
                if text:
                    turn_id += 1
                    turn_meta["start"] = time.perf_counter()
                    turn_meta["text"] = text
                    turn_meta["received"] = False

                    container.cancellation_manager.set_active_turn(sess_id, turn_id)
                    CLI.print_user_input(text)

                    await container.assistant._set_state(AssistantState.THINKING)
                    with Console().status("[bold cyan]ULTRON thinking...[/bold cyan]", spinner="dots"):
                        await container.event_bus.publish(
                            UserInputEvent(
                                text=text,
                                source="voice",
                                session_id=sess_id,
                                turn_id=turn_id,
                            )
                        )
                    while not turn_meta["received"] and container.assistant.state == AssistantState.THINKING:
                        await asyncio.sleep(0.05)
                    Console().print(f"[dim]Ready. Hold [bold]{hold_key}[/bold] to speak, or press Ctrl+C to return to text.[/dim]\n")
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        controller.stop_listening()
        Console().print("\n[bold green]✓ Returned to interactive text prompt.[/bold green]\n")


async def run_in_session_wakeword_loop(container, cli, turn_meta: dict) -> None:
    """Run interactive wake-word detection loop directly within the active session."""
    import asyncio
    import time
    from rich.console import Console
    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.wake_word.detector import WakeWordDetector
    from speech.speech_to_text.stt_pipeline import SpeechPipeline
    from utils.cli import CLI

    Console().print("\n[bold bright_cyan]🔍 WAKE-WORD MODE ACTIVATED[/bold bright_cyan]")
    Console().print("[dim]Listening for wake word ('Computer' / 'Hey Jarvis'). Speak after detection.[/dim]")
    if hasattr(container, "user_settings") and container.user_settings:
        container.user_settings.voice_enabled = True

    wake_detector = WakeWordDetector()
    pipeline = SpeechPipeline()

    sess = container.session_manager.active_session
    sess_id = sess.id if sess else "main"
    turn_id = 0

    try:
        while container.assistant.state != AssistantState.SHUTTING_DOWN:
            Console().print("[dim]🔍 Waiting for wake word... (Ctrl+C to return to text)[/dim]")
            heard = await asyncio.to_thread(wake_detector.detect)
            if not heard:
                continue

            Console().print("\n[bold green]✅ Wake word detected![/bold green]")
            CLI.print_listening()

            text = await asyncio.to_thread(pipeline.listen)
            text = (text or "").strip()
            if text:
                turn_id += 1
                turn_meta["start"] = time.perf_counter()
                turn_meta["text"] = text
                turn_meta["received"] = False

                container.cancellation_manager.set_active_turn(sess_id, turn_id)
                CLI.print_user_input(text)

                await container.assistant._set_state(AssistantState.THINKING)
                with Console().status("[bold cyan]ULTRON thinking...[/bold cyan]", spinner="dots"):
                    await container.event_bus.publish(
                        UserInputEvent(
                            text=text,
                            source="voice",
                            session_id=sess_id,
                            turn_id=turn_id,
                        )
                    )
                while not turn_meta["received"] and container.assistant.state == AssistantState.THINKING:
                    await asyncio.sleep(0.05)
                Console().print("[dim]Listening for next wake word...[/dim]\n")
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        wake_detector.stop()
        pipeline.stop()
        Console().print("\n[bold green]✓ Returned to interactive text prompt.[/bold green]\n")


async def run_in_session_continuous_loop(container, cli, turn_meta: dict) -> None:
    """Run interactive continuous voice loop directly within the active session."""
    import asyncio
    import time
    from rich.console import Console
    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.speech_to_text.stt_pipeline import SpeechPipeline
    from utils.cli import CLI

    Console().print("\n[bold bright_cyan]🔄 CONTINUOUS VOICE MODE ACTIVATED[/bold bright_cyan]")
    Console().print("[dim]Listening continuously. Speak directly. (Ctrl+C to return to text)[/dim]")
    if hasattr(container, "user_settings") and container.user_settings:
        container.user_settings.voice_enabled = True

    pipeline = SpeechPipeline()

    sess = container.session_manager.active_session
    sess_id = sess.id if sess else "main"
    turn_id = 0

    try:
        while container.assistant.state != AssistantState.SHUTTING_DOWN:
            CLI.print_listening()

            text = await asyncio.to_thread(pipeline.listen)
            text = (text or "").strip()
            if text:
                turn_id += 1
                turn_meta["start"] = time.perf_counter()
                turn_meta["text"] = text
                turn_meta["received"] = False

                container.cancellation_manager.set_active_turn(sess_id, turn_id)
                CLI.print_user_input(text)

                await container.assistant._set_state(AssistantState.THINKING)
                with Console().status("[bold cyan]ULTRON thinking...[/bold cyan]", spinner="dots"):
                    await container.event_bus.publish(
                        UserInputEvent(
                            text=text,
                            source="voice",
                            session_id=sess_id,
                            turn_id=turn_id,
                        )
                    )
                while not turn_meta["received"] and container.assistant.state == AssistantState.THINKING:
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        pipeline.stop()
        Console().print("\n[bold green]✓ Returned to interactive text prompt.[/bold green]\n")


async def run_text_mode(container) -> None:
    """Run in interactive cybernetic text input mode (terminal)."""
    import os
    import sys
    import time
    import asyncio
    from core.state import AssistantState
    from core.event_bus import UserInputEvent, ResponseReadyEvent
    from utils.cli_dashboard import CyberneticCLI
    from rich.console import Console

    # Initialize persistence and user settings
    await container.db.initialize()
    await container.user_settings.load_from_db(container.db)
    await container.session_manager.initialize("Main Chat")

    assistant = container.assistant
    await assistant.start(launch_listen_loop=False)

    cli = CyberneticCLI(container.session_manager, container.user_settings, container=container)
    cli.render_header()

    turn_meta = {"start": 0.0, "text": "", "received": False}

    async def _on_response_ready(event: ResponseReadyEvent) -> None:
        latency = (time.perf_counter() - turn_meta["start"]) * 1000 if turn_meta["start"] > 0 else 0.0
        p_tok = max(1, len(turn_meta["text"].split()))
        c_tok = max(1, len(event.response.split()))
        from utils.cli import mask_secrets, sanitize_terminal_text
        safe_resp = mask_secrets(sanitize_terminal_text(event.response))
        cli.render_response(safe_resp, latency_ms=latency, tokens=p_tok + c_tok)
        turn_meta["received"] = True

    container.event_bus.subscribe(ResponseReadyEvent, _on_response_ready)

    from utils.api_key_manager import prompt_first_run_if_needed
    await prompt_first_run_if_needed(cli=cli, container=container)
    Console().print("[dim]Type your message or use slash commands ([bold cyan]/help, /model, /listen, /mode, /rag, /chats, /voice, /text, /settings[/bold cyan]).[/dim]\n")

    # Configure prompt_toolkit for rich interactive terminal sessions
    is_interactive = sys.stdin.isatty()
    prompt_session = None
    if is_interactive:
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import FileHistory
            from prompt_toolkit.completion import NestedCompleter

            history_file = os.path.expanduser("~/.ultron_history")
            completer = NestedCompleter.from_nested_dict({
                "/help": None,
                "/model": {"dual": None, "groq": None, "nvidia": None, "qwen": None},
                "/listen": None,
                "/talk": None,
                "/mic": None,
                "/nowake": None,
                "/wakeword": None,
                "/continuous": None,
                "/voicechat": None,
                "/rag": None,
                "/chats": None,
                "/switch": None,
                "/new": None,
                "/delete": None,
                "/rename": None,
                "/mode": {
                    "text": None,
                    "no-wake": None,
                    "wakeword": None,
                    "continuous": None,
                    "voice": None,
                    "ptt": None,
                    "hybrid": None,
                    "online": None,
                    "offline": None,
                },
                "/settings": None,
                "/set": None,
                "/tokens": None,
                "/voice": {"on": None, "off": None},
                "/text": None,
                "/ps": None,
                "/powershell": None,
                "/guardrails": {"on": None, "off": None},
                "/clear": None,
                "/setup": None,
                "/keys": None,
                "/hub": None,
                "/providers": None,
                "/key": {"groq": None, "nvidia": None},
                "/upgrade": None,
                "/exit": None,
                "/quit": None,
            })
            prompt_session = PromptSession(
                history=FileHistory(history_file),
                completer=completer,
                complete_while_typing=False,
            )
        except Exception:
            prompt_session = None

    try:
        while assistant.state != AssistantState.SHUTTING_DOWN:
            sess = container.session_manager.active_session
            sess_name = sess.title if sess else "ultron"

            try:
                if prompt_session is not None:
                    from prompt_toolkit.formatted_text import HTML
                    prompt_html = HTML(
                        f"<b><ansicyan>ultron</ansicyan></b> "
                        f"<ansigray>[</ansigray><ansiyellow>{sess_name}</ansiyellow><ansigray>]</ansigray> "
                        f"<ansigreen>❯</ansigreen> "
                    )
                    line = await prompt_session.prompt_async(prompt_html)
                else:
                    prompt_str = f"ultron [{sess_name}] > "
                    line = await asyncio.to_thread(input, prompt_str)
            except KeyboardInterrupt:
                Console().print("[dim](Input cleared. Type /exit or Ctrl+D to quit)[/dim]")
                continue
            except EOFError:
                break

            from utils.cli import sanitize_terminal_text
            line = sanitize_terminal_text(line.strip())
            if not line:
                continue

            is_voice_turn = False
            # Check slash command or shell ! command
            if line.startswith("/") or line.startswith("!"):
                res = await cli.handle_command(line)
                if res == "exit":
                    break
                if isinstance(res, str) and res.startswith("voice_prompt:"):
                    line = res[len("voice_prompt:"):].strip()
                    if not line:
                        continue
                    is_voice_turn = True
                elif res == "switch_mode:no-wake":
                    await run_in_session_no_wake_loop(container, cli, turn_meta)
                    continue
                elif res == "switch_mode:wakeword":
                    await run_in_session_wakeword_loop(container, cli, turn_meta)
                    continue
                elif res == "switch_mode:continuous":
                    await run_in_session_continuous_loop(container, cli, turn_meta)
                    continue
                elif res:
                    continue

            # Guardrails validation
            safe, reason = container.user_settings.check_guardrails(line)
            if not safe:
                Console().print(f"[bold red]🛡️ {reason}[/bold red]")
                continue

            # Track and execute turn through assistant
            turn_meta["start"] = time.perf_counter()
            turn_meta["text"] = line
            turn_meta["received"] = False

            await assistant._set_state(AssistantState.THINKING)
            with Console().status("[bold cyan]ULTRON thinking...[/bold cyan]", spinner="dots"):
                await container.event_bus.publish(
                    UserInputEvent(
                        text=line,
                        source="voice" if is_voice_turn else "text"
                    )
                )

    except asyncio.CancelledError:
        pass
    finally:
        try:
            container.event_bus.unsubscribe(ResponseReadyEvent, _on_response_ready)
        except Exception:
            pass
        await assistant.stop()
        await container.db.close()
        await container.shutdown()


async def run_no_wake_mode(container) -> None:
    """Run in user-controlled voice listening mode (press Enter to listen, no wake word)."""
    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.speech_to_text.stt_pipeline import SpeechPipeline
    from speech.text_to_speech.tts_pipeline import stop_audio
    from utils.cli import CLI

    # Initialize persistence and user settings so voice responses are active
    await container.db.initialize()
    await container.user_settings.load_from_db(container.db)
    container.user_settings.voice_enabled = True

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

    # Initialize persistence and user settings so voice responses are active
    await container.db.initialize()
    await container.user_settings.load_from_db(container.db)
    container.user_settings.voice_enabled = True

    assistant = container.assistant
    await assistant.start(launch_listen_loop=False)

    wake_detector = WakeWordDetector()
    pipeline = SpeechPipeline()

    import uuid as _uuid
    session_id = str(_uuid.uuid4())
    turn_id = 0

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


async def run_continuous_mode(container) -> None:
    """Run in continuous listening mode without a wake word."""
    from core.state import AssistantState
    from core.event_bus import UserInputEvent
    from speech.speech_to_text.stt_pipeline import SpeechPipeline
    from utils.cli import CLI

    # Initialize persistence and user settings so voice responses are active
    await container.db.initialize()
    await container.user_settings.load_from_db(container.db)
    container.user_settings.voice_enabled = True

    assistant = container.assistant
    await assistant.start(launch_listen_loop=False)

    pipeline = SpeechPipeline()

    import uuid as _uuid
    session_id = str(_uuid.uuid4())
    turn_id = 0

    try:
        print("🔄 Continuous Voice Mode Active")
        while assistant.state != AssistantState.SHUTTING_DOWN:
            CLI.print_listening()

            text = await asyncio.to_thread(pipeline.listen)

            if text and text.strip():
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
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        await assistant.stop()
        await container.shutdown()


def main() -> None:
    # Fast-path CLI subcommands before general arg parsing
    if len(sys.argv) > 1:
        first_arg = sys.argv[1].lower()
        if first_arg in ("upgrade", "update"):
            from utils.updater import upgrade_cli
            code = upgrade_cli(sys.argv[2:])
            sys.exit(code)

        if first_arg in ("setup", "keys"):
            from utils.api_key_manager import interactive_setup_wizard
            asyncio.run(interactive_setup_wizard())
            sys.exit(0)

        if first_arg in ("hub", "providers"):
            from utils.api_key_manager import render_provider_hub
            render_provider_hub()
            sys.exit(0)

    args = parse_args()

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

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