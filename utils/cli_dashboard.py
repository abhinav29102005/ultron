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

        provider_name = os.getenv("LLM_PROVIDER", "groq").upper()
        if provider_name == "GROQ":
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

        table.add_row("/model [groq|nvidia|qwen]", "Switch active LLM engine (Groq ~250ms, NVIDIA 120B, Qwen local)")
        table.add_row("/rag <question>", "Query Theme 4 Streaming Live RAG over verified enterprise policy corpus")
        table.add_row("/setup, /keys", "Interactive API key setup wizard with cloud panel links")
        table.add_row("/hub, /providers", "View cloud LLM portal links and free tier quotas")
        table.add_row("/key <prov> <val>", "Save an API key (e.g. /key nvidia nvapi-xxxx)")
        table.add_row("/upgrade, /update", "Self-update Ultron repo, dependencies, and database migrations")
        table.add_row("/chats, /sessions", "List all persistent chat sessions with token counts")
        table.add_row("/switch <id>", "Switch context window to another chat session")
        table.add_row("/new [title]", "Create a fresh session and switch to it")
        table.add_row("/delete <id>", "Delete a chat session and its history")
        table.add_row("/rename <title>", "Rename the active chat session")
        table.add_row("/mode <online|offline|hybrid>", "Switch model execution mode (Cloud vs Local)")
        table.add_row("/settings, /config", "View all dynamic user configuration settings")
        table.add_row("/set <key> <val>", "Change a user setting on-the-fly (e.g., /set voice_enabled true)")
        table.add_row("/tokens", "Display session token usage, latency, and estimated cost")
        table.add_row("/voice [on|off]", "Switch to voice-based responses (spoken audio ON)")
        table.add_row("/text", "Switch to text-only responses (spoken audio OFF)")
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
        if not line.startswith("/"):
            return False

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
            from utils.updater import run_upgrade
            await run_upgrade()

        elif cmd == "key":
            from utils.api_key_manager import set_key_for_provider
            if not arg or " " not in arg:
                console.print("[red]Usage: /key <provider> <api_key> (e.g., /key nvidia nvapi-xxxx)[/red]")
            else:
                prov, val = arg.split(" ", 1)
                ok, msg = set_key_for_provider(prov, val)
                if ok:
                    console.print(f"[bold green]✓ {msg}[/bold green]")
                    if prov.lower() in ("groq", "nvidia", "qwen"):
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
                if target_prov in ("groq", "nvidia", "qwen"):
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
                    console.print("[red]Invalid provider. Available: 'groq' (~250ms), 'nvidia' (120B cloud), 'qwen' (local)[/red]")

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

        elif cmd == "mode":
            if not arg:
                console.print(f"[cyan]Current mode:[/cyan] {self.settings.execution_mode}. Usage: /mode <online|offline|hybrid>")
            else:
                ok, msg = await self.settings.update_setting(self.sm.db, "execution_mode", arg)
                if ok:
                    console.print(f"[bold green]✓ Mode updated:[/bold green] {self.settings.execution_mode.upper()}")
                    self.render_header()
                else:
                    console.print(f"[bold red]✗ {msg}[/bold red]")

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

        elif cmd in ("exit", "quit", "q"):
            console.print("[bold cyan]Saving session and shutting down ULTRON. Farewell.[/bold cyan]")
            return "exit"

        else:
            console.print(f"[red]Unknown command '/{cmd}'. Type /help for valid commands.[/red]")

        return True
