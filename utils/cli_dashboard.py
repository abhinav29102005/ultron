"""
utils/cli_dashboard.py – Cybernetic CLI Interface & Command Interceptor
========================================================================
Inspired by Claude Code, Hermes Agent, and Antigravity:
  • Real-time status header bar (Mode, Active Session, Tokens, Cost, Voice, Guardrails)
  • Slash commands for multi-session context switching (/chats, /switch, /new)
  • Dynamic settings editor (/settings, /set, /mode)
  • Safety guardrail enforcement and fast response panels
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, List, Optional, Tuple

from rich.box import ROUNDED, DOUBLE_EDGE
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config.user_settings import UserSettings
from core.session_manager import SessionManager, SessionInfo

console = Console()


class CyberneticCLI:
    """Renders cybernetic CLI UI panels, status banners, and intercepts commands."""

    def __init__(self, session_manager: SessionManager, settings: UserSettings, container: Optional[Any] = None):
        self.sm = session_manager
        self.settings = settings
        self.container = container

    def render_header(self) -> None:
        """Render the top status bar displaying mode, session, tokens, and safety."""
        sess = self.sm.active_session
        sess_title = sess.title if sess else "None"
        sess_id = sess.id if sess else "None"
        tokens = sess.total_tokens if sess else 0
        cost = (tokens / 1000.0) * self.settings.cost_per_1k_tokens

        mode_str = self.settings.execution_mode.upper()
        if mode_str == "HYBRID":
            mode_badge = "[bold cyan]HYBRID ⚡[/bold cyan]"
        elif mode_str == "OFFLINE":
            mode_badge = "[bold yellow]OFFLINE 🔒[/bold yellow]"
        else:
            mode_badge = "[bold green]ONLINE 🌐[/bold green]"

        voice_badge = "[bold green]ON[/bold green]" if self.settings.voice_enabled else "[dim]OFF[/dim]"
        guard_badge = "[bold green]ON[/bold green]" if self.settings.guardrails_enabled else "[bold red]OFF[/bold red]"

        provider_name = os.getenv("LLM_PROVIDER", "dual").upper()
        if provider_name == "DUAL":
            prov_badge = "[bold bright_yellow]DUAL ⚡ (Groq+NIM)[/bold bright_yellow]"
        elif provider_name == "GROQ":
            prov_badge = "[bold green]GROQ ⚡[/bold green]"
        elif provider_name == "NVIDIA":
            prov_badge = "[bold cyan]NVIDIA 🌐[/bold cyan]"
        else:
            prov_badge = "[bold yellow]QWEN 🔒[/bold yellow]"

        status_text = (
            f"[bold red]ULTRON[/bold red] [dim]v0.2.0[/dim] │ "
            f"LLM: {prov_badge} │ "
            f"Mode: {mode_badge} │ "
            f"Chat: [bold white]{sess_title}[/bold white] [dim]({sess_id})[/dim] │ "
            f"Tokens: [bold magenta]{tokens:,}[/bold magenta] [dim](${cost:.4f})[/dim] │ "
            f"Voice: {voice_badge} │ "
            f"Guardrails: {guard_badge}"
        )
        console.print(Panel(status_text, border_style="bright_blue", box=ROUNDED))

    def render_help(self) -> None:
        """Render slash commands manual."""
        table = Table(title="ULTRON Cybernetic CLI — Commands", border_style="cyan", box=ROUNDED)
        table.add_column("Command", style="bold yellow", width=22)
        table.add_column("Description", style="white")

        table.add_row("/model [nebius|dual|groq|nvidia|qwen]", "Switch active LLM engine (Nebius Token Factory Nemotron, Dual, Groq, NVIDIA, Qwen)")
        table.add_row("/rag <question>", "Query Theme 4 Streaming Live RAG over verified enterprise policy corpus")
        table.add_row("/setup, /keys", "Interactive API key setup wizard with cloud panel links")
        table.add_row("/hub, /providers", "View cloud LLM portal links and free tier quotas")
        table.add_row("/key <prov> <val>", "Save an API key (e.g. /key nvidia nvapi-xxxx)")
        table.add_row("/upgrade [flags], /update", "Self-update Ultron repo, dependencies, voice models & database (--check, --force)")
        table.add_row("/chats, /sessions", "List all persistent chat sessions with token counts")
        table.add_row("/switch <id>", "Switch context window to another chat session")
        table.add_row("/new [title]", "Create a fresh session and switch to it")
        table.add_row("/delete <id>", "Delete a chat session and its history")
        table.add_row("/rename <title>", "Rename the active chat session")
        table.add_row("/listen, /talk", "Speak a voice command now (real-time microphone visualizer)")
        table.add_row("/mode [no-wake|wakeword|text]", "Switch interaction mode dynamically within this session")
        table.add_row("/mode <online|offline|hybrid>", "Switch model execution mode (Cloud vs Local)")
        table.add_row("/settings, /config", "View all dynamic user configuration settings")
        table.add_row("/set <key> <val>", "Change a user setting on-the-fly (e.g., /set voice_enabled true)")
        table.add_row("/tokens", "Display session token usage, latency, and estimated cost")
        table.add_row("/voice [on|off]", "Switch to voice-based responses (spoken audio ON)")
        table.add_row("/text", "Switch to text-only responses (spoken audio OFF)")
        table.add_row("/ps <cmd>, !<cmd>", "Execute native Windows PowerShell CLI command & stream telemetry")
        table.add_row("/guardrails <on|off>", "Toggle safety execution guardrails")
        table.add_row("/clear", "Clear message history of the current chat")
        table.add_row("/help", "Show this command manual")
        table.add_row("/quit, /exit", "Exit ULTRON safely with state persistence")

        console.print(table)

    async def render_chats(self) -> None:
        """Render a table of all existing sessions."""
        sessions = await self.sm.list_sessions()
        active_id = self.sm.active_session.id if self.sm.active_session else ""

        table = Table(title="Persistent Chat Sessions", border_style="bright_blue", box=ROUNDED)
        table.add_column("Active", justify="center", width=8)
        table.add_column("Session ID", style="cyan", width=26)
        table.add_column("Title", style="bold white", width=24)
        table.add_column("Tokens", justify="right", style="magenta", width=12)
        table.add_column("Last Updated", style="dim", width=20)

        for s in sessions:
            is_active = "[bold green]▶ [*][/bold green]" if s.id == active_id else " "
            updated = (s.updated_at or "")[:19].replace("T", " ")
            table.add_row(is_active, s.id, s.title, f"{s.total_tokens:,}", updated)

        console.print(table)
        console.print("[dim]Use [bold cyan]/switch <id>[/bold cyan] to change session or [bold cyan]/new [title][/bold cyan] to create one.[/dim]\n")

    def render_settings(self) -> None:
        """Render user settings table."""
        table = Table(title="ULTRON User Settings & Preferences", border_style="magenta", box=ROUNDED)
        table.add_column("Setting Key", style="bold yellow", width=28)
        table.add_column("Current Value", style="bold white", width=24)
        table.add_column("Description", style="dim")

        s = self.settings
        table.add_row("execution_mode", str(s.execution_mode), "hybrid (Cloud+Local) | online | offline")
        table.add_row("voice_enabled", str(s.voice_enabled), "Enable voice microphone and spoken output")
        table.add_row("voice_output_mode", str(s.voice_output_mode), "always | on_voice_input | never")
        table.add_row("context_continuity", str(s.context_continuity), "Maintain multi-turn conversational context")
        table.add_row("max_context_turns", str(s.max_context_turns), "Sliding context window size (turns)")
        table.add_row("guardrails_enabled", str(s.guardrails_enabled), "Enforce safety checks on commands/paths")
        table.add_row("confirm_destructive_commands", str(s.confirm_destructive_commands), "Prompt before destructive actions")
        table.add_row("max_response_tokens", str(s.max_response_tokens), "Response length limit (e.g. 512 for speed)")
        table.add_row("fast_response_mode", str(s.fast_response_mode), "Low-latency streaming response prioritization")
        table.add_row("concise_mode", str(s.concise_mode), "Omit filler; produce dense, direct answers")
        table.add_row("output_style", str(s.output_style), "cybernetic | compact | markdown")
        table.add_row("show_citations", str(s.show_citations), "Show [Doc_XX §YY] grounding citations")
        table.add_row("show_telemetry", str(s.show_telemetry), "Display token & latency badge on answers")
        table.add_row("session_token_budget", f"{s.session_token_budget:,}", "Session token alert threshold")

        console.print(table)
        console.print("[dim]Update any setting with: [bold cyan]/set <key> <value>[/bold cyan][/dim]\n")

    def render_tokens(self) -> None:
        """Render token telemetry card."""
        sess = self.sm.active_session
        p_tokens = sess.prompt_tokens if sess else 0
        c_tokens = sess.completion_tokens if sess else 0
        total = p_tokens + c_tokens
        cost = (total / 1000.0) * self.settings.cost_per_1k_tokens

        table = Table(title="Session Token Telemetry & Budget", border_style="green", box=ROUNDED)
        table.add_column("Metric", style="white", width=25)
        table.add_column("Value", style="bold green", width=20)

        table.add_row("Active Session", sess.title if sess else "None")
        table.add_row("Prompt Tokens (Input)", f"{p_tokens:,}")
        table.add_row("Completion Tokens (Output)", f"{c_tokens:,}")
        table.add_row("Total Turn Tokens", f"{total:,}")
        table.add_row("Estimated Cost (USD)", f"${cost:.5f}")
        table.add_row("Session Budget Limit", f"{self.settings.session_token_budget:,}")
        table.add_row("Budget Remaining", f"{max(0, self.settings.session_token_budget - total):,}")

        console.print(table)

    def render_response(
        self,
        content: str,
        citations: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        tokens: int = 0,
    ) -> None:
        """Render an AI response in cybernetic panel format."""
        if self.settings.output_style == "compact":
            console.print(f"[bold red]ULTRON:[/bold red] {content}")
            if citations and self.settings.show_citations:
                console.print(f"[dim]Citations: {', '.join(citations)}[/dim]")
            return

        body = content
        if citations and self.settings.show_citations:
            cit_str = ", ".join(citations)
            body += f"\n\n[dim cyan]📚 Citations: {cit_str}[/dim cyan]"

        subtitle = None
        if self.settings.show_telemetry and (latency_ms > 0 or tokens > 0):
            subtitle = f"[dim magenta]{tokens} tokens · {latency_ms:.0f}ms[/dim magenta]"

        panel = Panel(
            body,
            title="[bold red]ULTRON[/bold red]",
            subtitle=subtitle,
            border_style="bright_blue",
            box=ROUNDED,
            padding=(1, 2),
        )
        console.print(panel)

    async def handle_command(self, line: str) -> bool:
        """
        Intercept and process a slash command.
        Returns True if the line was a handled slash command, False if it is a normal chat prompt.
        """
        if not line.startswith("/") and not line.startswith("!"):
            return False

        if line.startswith("!"):
            cmd = "ps"
            arg = line[1:].strip()
        else:
            parts = line[1:].strip().split(maxsplit=1)
            if not parts:
                return True
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("help", "?"):
            self.render_help()

        elif cmd in ("setup", "keys", "wizard"):
            from utils.api_key_manager import interactive_setup_wizard
            await interactive_setup_wizard(cli=self)

        elif cmd in ("hub", "providers", "portals"):
            from utils.api_key_manager import render_provider_hub
            render_provider_hub()

        elif cmd in ("upgrade", "update"):
            from utils.updater import parse_upgrade_args, run_upgrade
            args_list = arg.split() if arg else []
            try:
                up_args = parse_upgrade_args(args_list)
                await run_upgrade(
                    check_only=up_args.check_only,
                    force=up_args.force,
                    target_branch=up_args.branch,
                    remote=up_args.remote,
                    skip_deps=up_args.skip_deps,
                    skip_models=up_args.skip_models,
                    verbose=up_args.verbose,
                    as_json=up_args.as_json,
                )
            except SystemExit:
                pass

        elif cmd == "key":
            from utils.api_key_manager import set_key_for_provider
            if not arg or " " not in arg:
                console.print("[red]Usage: /key <provider> <api_key> (e.g., /key nvidia nvapi-xxxx)[/red]")
            else:
                prov, val = arg.split(" ", 1)
                ok, msg = set_key_for_provider(prov, val)
                if ok:
                    console.print(f"[bold green]✓ {msg}[/bold green]")
                    if prov.lower() in ("groq", "nebius", "nvidia", "qwen"):
                        console.print(f"[bold green]✓ Switched active LLM engine to {prov.upper()}[/bold green]")
                        if hasattr(self, "settings"):
                            self.settings.llm_provider = prov.lower()
                        if hasattr(self, "container") and hasattr(self.container, "llm_switcher"):
                            try:
                                self.container.llm_switcher.switch(prov.lower())
                            except Exception:
                                pass
                    self.render_header()
                else:
                    console.print(f"[bold red]✗ {msg}[/bold red]")

        elif cmd in ("chats", "sessions", "list"):
            await self.render_chats()

        elif cmd == "switch":
            if not arg:
                console.print("[red]Usage: /switch <session_id>[/red]")
            else:
                sess = await self.sm.switch_session(arg)
                if sess:
                    console.print(f"[bold green]✓ Switched context to:[/bold green] {sess.title} [dim]({sess.id})[/dim]")
                    self.render_header()
                else:
                    console.print(f"[red]Session '{arg}' not found. Run /chats to list IDs.[/red]")

        elif cmd in ("new", "create"):
            title = arg if arg else "New Chat"
            sess = await self.sm.create_session(title=title)
            console.print(f"[bold green]✓ Created new chat session:[/bold green] {sess.title} [dim]({sess.id})[/dim]")
            self.render_header()

        elif cmd in ("delete", "rm"):
            if not arg:
                console.print("[red]Usage: /delete <session_id>[/red]")
            else:
                ok = await self.sm.delete_session(arg)
                if ok:
                    console.print(f"[bold green]✓ Deleted session '{arg}'[/bold green]")
                else:
                    console.print(f"[red]Could not delete session '{arg}'.[/red]")

        elif cmd == "rename":
            if not arg:
                console.print("[red]Usage: /rename <new_title>[/red]")
            else:
                await self.sm.update_title(arg)
                console.print(f"[bold green]✓ Renamed session to:[/bold green] {arg}")

        elif cmd in ("settings", "config"):
            self.render_settings()

        elif cmd == "set":
            if not arg or "=" not in arg and " " not in arg:
                console.print("[red]Usage: /set <key> <value> (e.g. /set voice_enabled true)[/red]")
            else:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                else:
                    k, v = arg.split(" ", 1)
                k = k.strip()
                v = v.strip()
                ok, msg = await self.settings.update_setting(self.sm.db, k, v)
                if ok:
                    console.print(f"[bold green]✓ {msg}[/bold green]")
                    self.render_header()
                else:
                    console.print(f"[bold red]✗ {msg}[/bold red]")

        elif cmd in ("model", "llm"):
            from utils.api_key_manager import update_env_file
            if not arg:
                curr = os.getenv("LLM_PROVIDER", "groq")
                console.print(f"[cyan]Current LLM Provider:[/cyan] [bold green]{curr.upper()}[/bold green] (Options: groq, nvidia, qwen)")
            else:
                target_prov = arg.lower().strip()
                if target_prov in ("nebius", "dual", "groq", "nvidia", "qwen"):
                    update_env_file("LLM_PROVIDER", target_prov)
                    os.environ["LLM_PROVIDER"] = target_prov

                    if target_prov == "groq":
                        curr_gm = os.getenv("GROQ_MODEL", "")
                        if not curr_gm or any(d in curr_gm.lower() for d in ("llama", "mixtral")):
                            update_env_file("GROQ_MODEL", "openai/gpt-oss-120b")
                            os.environ["GROQ_MODEL"] = "openai/gpt-oss-120b"
                            update_env_file("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
                            os.environ["GROQ_FAST_MODEL"] = "openai/gpt-oss-20b"

                    if target_prov == "nvidia":
                        curr_nm = os.getenv("NVIDIA_MODEL", "")
                        if not curr_nm or any(d in curr_nm.lower() for d in ("llama-3.1-8b", "llama3.1-8b")):
                            update_env_file("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")
                            os.environ["NVIDIA_MODEL"] = "nvidia/nemotron-3-super-120b-a12b"

                    if self.container and hasattr(self.container, "llm") and hasattr(self.container.llm, "switch"):
                        try:
                            self.container.llm.switch(target_prov)
                        except Exception as e:
                            console.print(f"[yellow]Warning: {e}[/yellow]")
                    console.print(f"[bold green]✓ Switched LLM provider to: {target_prov.upper()}[/bold green]")
                    self.render_header()
                else:
                    console.print("[red]Invalid provider. Available: 'nebius' (Nebius Token Factory Nemotron), 'dual', 'groq', 'nvidia', 'qwen'[/red]")

        elif cmd in ("rag", "search"):
            if not arg:
                console.print("[red]Usage: /rag <question> (e.g. /rag Pune workshop for 30 people)[/red]")
            else:
                from streaming_rag.pipeline import StreamingLiveRAG
                from streaming_rag.models import StreamingChunk
                console.print(f"[dim]Executing Streaming Live RAG over enterprise corpus...[/dim]")
                rag = StreamingLiveRAG()
                stream = [StreamingChunk(timestamp_s=0.5, text=arg, is_final=True)]
                rec = rag.process_stream(stream, session_id=self.sm.active_session.id if self.sm.active_session else "rag_cli")
                self.render_response(
                    rec.answer,
                    citations=rec.citations,
                    latency_ms=rec.telemetry.total_latency_ms,
                    tokens=rec.telemetry.prompt_tokens + rec.telemetry.completion_tokens,
                )
                if rec.uncertainty:
                    console.print(f"[bold yellow]⚠️ Uncertainty:[/bold yellow] [dim]{rec.uncertainty}[/dim]")

        elif cmd in ("listen", "talk", "mic", "speak", "record"):
            spoken = await self.capture_voice_turn()
            if spoken:
                return f"voice_prompt:{spoken}"
            return True

        elif cmd in ("nowake", "no-wake", "ptt"):
            await self.settings.update_setting(self.sm.db, "voice_enabled", "true")
            return "switch_mode:no-wake"

        elif cmd in ("wakeword", "wake"):
            await self.settings.update_setting(self.sm.db, "voice_enabled", "true")
            return "switch_mode:wakeword"

        elif cmd in ("continuous", "voicechat", "chatvoice"):
            await self.settings.update_setting(self.sm.db, "voice_enabled", "true")
            return "switch_mode:continuous"

        elif cmd == "mode":
            mode_arg = arg.lower().strip()
            if not mode_arg:
                console.print(f"[cyan]Current interaction mode:[/cyan] [bold green]text[/bold green]")
                console.print(f"[dim]Available interaction modes: [bold cyan]/mode no-wake[/bold cyan] (push-to-talk), [bold cyan]/mode wakeword[/bold cyan], [bold cyan]/mode continuous[/bold cyan], [bold cyan]/mode text[/bold cyan][/dim]")
                console.print(f"[dim]Available engine modes: [bold cyan]/mode online[/bold cyan], [bold cyan]/mode offline[/bold cyan], [bold cyan]/mode hybrid[/bold cyan][/dim]")
            elif mode_arg in ("no-wake", "nowake", "voice", "ptt", "push-to-talk"):
                await self.settings.update_setting(self.sm.db, "voice_enabled", "true")
                return "switch_mode:no-wake"
            elif mode_arg in ("wakeword", "wake", "wake-word"):
                await self.settings.update_setting(self.sm.db, "voice_enabled", "true")
                return "switch_mode:wakeword"
            elif mode_arg in ("continuous", "voicechat", "chatvoice"):
                await self.settings.update_setting(self.sm.db, "voice_enabled", "true")
                return "switch_mode:continuous"
            elif mode_arg in ("text", "chat"):
                console.print("[bold green]✓ Interaction Mode: TEXT (Interactive terminal prompt)[/bold green]")
                console.print("[dim]Tip: Type [bold cyan]/voice on[/bold cyan] anytime to hear spoken audio replies in text mode.[/dim]")
            elif mode_arg in ("online", "offline", "hybrid"):
                ok, msg = await self.settings.update_setting(self.sm.db, "execution_mode", mode_arg)
                if ok:
                    console.print(f"[bold green]✓ Engine mode updated:[/bold green] {self.settings.execution_mode.upper()}")
                    self.render_header()
                else:
                    console.print(f"[bold red]✗ {msg}[/bold red]")
            else:
                console.print(f"[red]Unknown mode '{arg}'. Available: no-wake, wakeword, continuous, text, online, offline, hybrid[/red]")

        elif cmd == "voice":
            if not arg:
                new_val = True
            else:
                new_val = arg.lower() in ("on", "true", "1", "enable")
            await self.settings.update_setting(self.sm.db, "voice_enabled", str(new_val))
            status = "ENABLED 🎤 (Spoken voice replies ON)" if new_val else "DISABLED 🔇 (Text replies only)"
            console.print(f"[bold green]✓ Voice responses {status}[/bold green]")
            self.render_header()

        elif cmd == "text":
            new_val = False
            await self.settings.update_setting(self.sm.db, "voice_enabled", str(new_val))
            console.print("[bold green]✓ Text-only responses ENABLED 📝 (Spoken audio OFF)[/bold green]")
            self.render_header()

        elif cmd == "guardrails":
            if not arg:
                new_val = not self.settings.guardrails_enabled
            else:
                new_val = arg.lower() in ("on", "true", "1", "enable")
            await self.settings.update_setting(self.sm.db, "guardrails_enabled", str(new_val))
            status = "ENABLED 🛡️" if new_val else "DISABLED ⚠️"
            console.print(f"[bold green]✓ Safety Guardrails {status}[/bold green]")
            self.render_header()

        elif cmd == "tokens":
            self.render_tokens()

        elif cmd == "clear":
            if self.sm.active_session:
                sess_id = self.sm.active_session.id
                await self.sm.delete_session(sess_id)
                await self.sm.create_session("New Chat")
                console.print("[bold green]✓ Cleared conversation context.[/bold green]")
                self.render_header()

        elif cmd in ("ps", "powershell", "exec", "sh"):
            if not arg:
                console.print("[red]Usage: /ps <command> (or !<command>)[/red]")
            else:
                await self.execute_powershell_command(arg)

        elif cmd in ("exit", "quit", "q"):
            console.print("[bold cyan]Saving session and shutting down ULTRON. Farewell.[/bold cyan]")
            return "exit"

        else:
            console.print(f"[red]Unknown command '/{cmd}'. Type /help for valid commands.[/red]")

        return True

    async def execute_powershell_command(self, cmd_str: str) -> None:
        """Execute a native Windows PowerShell command asynchronously with telemetry."""
        import asyncio
        import subprocess
        import time

        # Security guardrails validation
        if hasattr(self, "settings") and self.settings:
            safe, reason = self.settings.check_guardrails(cmd_str)
            if not safe:
                console.print(f"[bold red]🛡️ {reason}[/bold red]")
                return

        console.print(f"[dim]⚡ Running in PowerShell:[/] [bold cyan]{cmd_str}[/]")
        start = time.perf_counter()

        try:
            ps_executable = "powershell.exe"
            args = [
                ps_executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd_str,
            ]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stdout, stderr = await proc.communicate()
            elapsed_ms = (time.perf_counter() - start) * 1000

            out_text = stdout.decode("utf-8", errors="replace").strip()
            err_text = stderr.decode("utf-8", errors="replace").strip()

            from utils.cli import mask_secrets, sanitize_terminal_text
            out_text = mask_secrets(sanitize_terminal_text(out_text))
            err_text = mask_secrets(sanitize_terminal_text(err_text))

            if proc.returncode == 0:
                body = out_text if out_text else "[dim](Command completed with exit code 0 and no output)[/dim]"
                border = "green"
                status_badge = f"[bold green]● Exit: 0[/] [dim]({elapsed_ms:.1f}ms)[/]"
            else:
                body = f"{out_text}\n[bold red]{err_text}[/]" if out_text else f"[bold red]{err_text}[/]"
                if not body.strip():
                    body = f"[red]Process exited with code {proc.returncode}[/red]"
                border = "red"
                status_badge = f"[bold red]● Exit: {proc.returncode}[/] [dim]({elapsed_ms:.1f}ms)[/]"

            console.print(Panel(
                body,
                title=f"[bold cyan] PowerShell CLI [/] {status_badge}",
                title_align="left",
                border_style=border,
                box=ROUNDED,
                padding=(0, 1),
            ))
        except Exception as exc:
            console.print(f"[bold red]✗ Failed to run PowerShell command: {exc}[/bold red]")

    async def capture_voice_turn(self) -> str:
        """Capture a single voice command from the microphone with live volume bar."""
        import asyncio
        from speech.speech_to_text.stt_pipeline import SpeechPipeline

        console.print("[bold bright_cyan]● LISTENING[/] [dim]Speak command into microphone now...[/]")
        pipeline = SpeechPipeline()
        try:
            text = await asyncio.to_thread(pipeline.listen)
            text = (text or "").strip()
            if text:
                console.print(f"[bold bright_white]USER (Spoken)[/] [bright_cyan]›[/] [white]{text}[/]")
            else:
                console.print("[dim](No speech detected)[/dim]")
            return text
        except Exception as exc:
            console.print(f"[bold red]✗ Microphone capture error: {exc}[/bold red]")
            return ""
        finally:
            pipeline.stop()

