# -*- coding: utf-8 -*-
"""
utils/cli.py – Cybernetic CLI Interface & Banner for ULTRON
============================================================
Provides rich visual telemetry, ASCII typography, and standardized
terminal interaction elements for ULTRON AI Desktop Assistant.
"""

from __future__ import annotations

import sys
from typing import Any, Optional, Sequence

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    _RICH_AVAILABLE = True
    console = Console()
except ImportError:
    _RICH_AVAILABLE = False
    console = None

ULTRON_ASCII = """  ██╗   ██╗██╗  ████████╗██████╗  ██████╗ ███╗   ██╗
  ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔═══██╗████╗  ██║
  ██║   ██║██║     ██║   ██████╔╝██║   ██║██╔██╗ ██║
  ██║   ██║██║     ██║   ██╔══██╗██║   ██║██║╚██╗██║
  ╚██████╔╝███████╗██║   ██║  ██║╚██████╔╝██║ ╚████║
   ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝"""


import re

SECRET_REDACT_REGEX = re.compile(
    r"(nvapi-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z-_]{35}|Bearer\s+[A-Za-z0-9._-]{20,})"
)

def mask_secrets(text: str) -> str:
    """Mask sensitive credentials, tokens, and API keys from terminal output."""
    if not text:
        return ""
    return SECRET_REDACT_REGEX.sub("[REDACTED_SECRET]", str(text))

def sanitize_terminal_text(text: str) -> str:
    """Sanitize dangerous ANSI escape sequences (OSC, APC, CSI) from inputs/outputs."""
    if not text:
        return ""
    # Strip OSC sequences like \x1b]0;Title\x07
    sanitized = re.sub(r"\x1b\][^\x07\x1b]*[\x07\x1b\\]?", "", str(text))
    # Strip standard CSI escape sequences like \x1b[31m
    sanitized = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", sanitized)
    # Strip single escape characters
    sanitized = sanitized.replace("\x1b", "")
    return sanitized


def calculate_audio_level(chunk: Any) -> float:
    """Calculate normalized audio energy level (0.0 to 1.0) from a raw audio chunk."""
    if chunk is None:
        return 0.0
    try:
        import numpy as np
        if not isinstance(chunk, np.ndarray):
            chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.size == 0:
            return 0.0
        # Root Mean Square (RMS) energy
        rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float32)))))
        if not np.isfinite(rms) or rms <= 1e-5:
            return 0.0
        # Decibel scaling: -45 dB (noise floor) to -10 dB (loud human speech)
        db = 20.0 * np.log10(rms)
        pct = (db + 45.0) / 35.0
        return max(0.0, min(1.0, float(pct)))
    except Exception:
        return 0.0


class CLI:
    """High-performance, cybernetic CLI console formatter."""

    _last_level: float = 0.0

    @classmethod
    def format_listening_bar(
        cls,
        audio_or_level: float | Any,
        is_held: bool = False,
        status: str = "",
        is_speech: Optional[bool] = None,
        total_bars: int = 16,
        smooth: bool = True,
    ) -> tuple[str, float]:
        """Generate formatted listening bar markup and normalized level."""
        raw_level = (
            max(0.0, min(1.0, float(audio_or_level)))
            if isinstance(audio_or_level, (int, float))
            else calculate_audio_level(audio_or_level)
        )

        if smooth:
            if raw_level > cls._last_level:
                cls._last_level = 0.75 * raw_level + 0.25 * cls._last_level
            else:
                cls._last_level = 0.35 * raw_level + 0.65 * cls._last_level
            if cls._last_level < 0.01:
                cls._last_level = 0.0
            level = cls._last_level
        else:
            level = raw_level
            cls._last_level = raw_level

        pct = int(round(level * 100))
        filled = int(round(level * total_bars))
        empty = max(0, total_bars - filled)

        # 3-tier colors for VU meter
        green_cap = int(total_bars * 0.6)
        yellow_cap = int(total_bars * 0.85)

        g_bars = min(filled, green_cap)
        y_bars = max(0, min(filled - green_cap, yellow_cap - green_cap))
        r_bars = max(0, filled - yellow_cap)

        # Unicode symbols
        f_char = "▰"
        e_char = "▱"

        badge = (
            "[bold bright_magenta]● PUSH-TO-TALK[/]"
            if is_held
            else "[bold bright_cyan]● LISTENING[/]"
        )

        if not status:
            if is_speech is True or level >= 0.10:
                status = "[bold bright_green]Hearing voice...[/]"
            elif is_held:
                status = "[dim]Key held, speak...[/]"
            else:
                status = "[dim]Listening...[/]"

        bar_colored = ""
        if g_bars:
            bar_colored += f"[bold green]{f_char * g_bars}[/]"
        if y_bars:
            bar_colored += f"[bold bright_yellow]{f_char * y_bars}[/]"
        if r_bars:
            bar_colored += f"[bold bright_red]{f_char * r_bars}[/]"
        if empty:
            bar_colored += f"[dim]{e_char * empty}[/]"

        meter_text = f"\r{badge}  [{bar_colored}] [bold bright_white]{pct:3d}%[/]  {status}   "
        return meter_text, level

    @classmethod
    def render_listening_bar(
        cls,
        audio_or_level: float | Any,
        is_held: bool = False,
        status: str = "",
        is_speech: Optional[bool] = None,
        total_bars: int = 16,
        smooth: bool = True,
    ) -> None:
        """Render a real-time, dynamic volume visualizer bar in-place during audio capture."""
        import os
        if os.getenv("ULTRON_AUDIO_BAR", "1").lower() in ("0", "false", "no"):
            return

        meter_text, level = cls.format_listening_bar(
            audio_or_level=audio_or_level,
            is_held=is_held,
            status=status,
            is_speech=is_speech,
            total_bars=total_bars,
            smooth=smooth,
        )

        pct = int(round(level * 100))
        filled = int(round(level * total_bars))
        empty = max(0, total_bars - filled)

        if _RICH_AVAILABLE and console is not None:
            try:
                console.print(meter_text, end="\r")
            except Exception:
                sys.stdout.write(f"\r[MIC] [{'#' * filled}{'-' * empty}] {pct:3d}%   ")
                sys.stdout.flush()
        else:
            sys.stdout.write(f"\r[MIC] [{'#' * filled}{'-' * empty}] {pct:3d}%   ")
            sys.stdout.flush()

    @classmethod
    def clear_listening_bar(cls) -> None:
        """Clear the dynamic listening visualizer line from the terminal."""
        cls._last_level = 0.0
        try:
            sys.stdout.write("\r\x1b[2K" + " " * 80 + "\r")
            sys.stdout.flush()
        except Exception:
            pass

    @staticmethod
    def print_startup(mode: str = "Text / Reactive") -> None:
        """Display the official ULTRON startup banner and operational parameters."""
        if _RICH_AVAILABLE and console is not None:
            grid = Table.grid(expand=True, padding=(0, 2))
            grid.add_column(justify="left", ratio=3)
            grid.add_column(justify="right", ratio=2)

            grid.add_row("[bold bright_red]STATUS[/]  [bold green]● ONLINE[/]", "[bold bright_white]BUILD[/]  [cyan]v0.2.0[/]")
            import os
            prov = os.getenv("LLM_PROVIDER", "dual").lower()
            if prov == "dual":
                engine_label = "Dual LLM (Groq ⚡ + NVIDIA NIM ☁️)"
            elif prov == "groq":
                engine_label = "Groq Cloud ⚡ (~500 tok/s)"
            elif prov == "nvidia":
                engine_label = "NVIDIA NIM ☁️ (Nemotron 120B)"
            else:
                engine_label = f"Local LLM ({prov.upper()})"
            grid.add_row(f"[bold bright_red]ENGINE[/]  [bright_white]{engine_label}[/]", f"[bold bright_white]MODE[/]   [cyan]{mode}[/]")
            grid.add_row("[bold bright_red]RAG[/]     [bright_white]Streaming Live (Theme 4)[/]", "[bold bright_white]EXIT[/]   [dim]Ctrl + C[/]")

            title_text = Text(ULTRON_ASCII.strip("\n"), style="bold bright_red")
            sub_text = Text("\n  AUTONOMOUS AI DESKTOP AGENT & STREAMING LIVE RAG\n  Zero Parametric Hallucination · Strict Grounding · Dynamic Synthesis\n", style="bold white")

            panel_content = Table.grid(padding=0)
            panel_content.add_row(title_text)
            panel_content.add_row(sub_text)
            panel_content.add_row(grid)

            panel = Panel(
                panel_content,
                border_style="bright_red",
                title="[bold bright_white] SYSTEM INITIALIZED [/]",
                subtitle="[dim]ULTRON Core Platform · Ready for Commands[/]",
                padding=(1, 2),
            )
            console.print()
            console.print(panel)
            console.print()
        else:
            print("\n====================================================")
            print(ULTRON_ASCII)
            print("         ULTRON – AI DESKTOP AGENT & LIVE RAG")
            print("====================================================")
            print(f"Status: ONLINE | Mode: {mode} | Version: 0.2.0")
            print("Ready for input. Press Ctrl+C anytime to exit.\n")
            sys.stdout.flush()

    @staticmethod
    def print_listening() -> None:
        """Indicate active microphone / audio stream listening."""
        if _RICH_AVAILABLE and console is not None:
            console.print("[bold bright_cyan]● LISTENING[/] [dim]Speak command into microphone...[/]")
        else:
            print("[MIC] Listening...")
            sys.stdout.flush()

    @staticmethod
    def print_processing() -> None:
        """Indicate LLM / RAG intent decomposition and processing."""
        CLI.clear_listening_bar()
        if _RICH_AVAILABLE and console is not None:
            console.print("[bold bright_yellow]◐ PROCESSING[/] [dim]Analyzing intent & retrieving knowledge...[/]")
        else:
            print("[PROC] Processing...")
            sys.stdout.flush()

    @staticmethod
    def print_user_input(text: str) -> None:
        """Display recognized or typed user utterance."""
        CLI.clear_listening_bar()
        if _RICH_AVAILABLE and console is not None:
            console.print(f"\n[bold bright_white]USER[/] [bright_cyan]›[/] [white]{text}[/]")
        else:
            print(f"\nYou:\n> {text}\n")
            sys.stdout.flush()

    @staticmethod
    def print_ultron_response(text: str, citations: Optional[Sequence[str]] = None) -> None:
        """Display synthesized agent response with optional grounded citations."""
        if _RICH_AVAILABLE and console is not None:
            citation_badge = ""
            if citations:
                rendered_citations = " ".join([f"[bold cyan][{c}][/]" for c in citations])
                citation_badge = f"\n\n[dim]Grounding Sources:[/] {rendered_citations}"

            panel = Panel(
                f"[bright_white]{text}[/]{citation_badge}",
                border_style="bright_red",
                title="[bold bright_red] ULTRON [/]",
                title_align="left",
                padding=(0, 1),
            )
            console.print(panel)
            console.print("[dim]Ready for next command...[/]\n")
        else:
            print(f"ULTRON:\n> {text}")
            if citations:
                print(f"Citations: {', '.join(citations)}")
            print("------------------------------------------------")
            print("[MIC] Ready for next command...\n")
            sys.stdout.flush()

    @staticmethod
    def print_ultron_response_compat(text: str) -> None:
        """Backwards compatible signature for legacy callers."""
        CLI.print_ultron_response(text)

    @staticmethod
    def print_shutdown() -> None:
        """Display system shutdown notification."""
        CLI.clear_listening_bar()
        if _RICH_AVAILABLE and console is not None:
            console.print("\n[bold bright_red]■ SHUTDOWN[/] [dim]Terminating active loops... ULTRON offline.[/]\n")
        else:
            print("\n[BYE] Shutting down... ULTRON offline.\n")
            sys.stdout.flush()
