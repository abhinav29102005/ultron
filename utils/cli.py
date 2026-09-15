# -*- coding: utf-8 -*-
"""
utils/cli.py – Cybernetic CLI Interface & Banner for ULTRON
============================================================
Provides rich visual telemetry, ASCII typography, and standardized
terminal interaction elements for ULTRON AI Desktop Assistant.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

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


class CLI:
    """High-performance, cybernetic CLI console formatter."""

    @staticmethod
    def print_startup(mode: str = "Text / Reactive") -> None:
        """Display the official ULTRON startup banner and operational parameters."""
        if _RICH_AVAILABLE and console is not None:
            grid = Table.grid(expand=True, padding=(0, 2))
            grid.add_column(justify="left", ratio=3)
            grid.add_column(justify="right", ratio=2)

            grid.add_row("[bold bright_red]STATUS[/]  [bold green]● ONLINE[/]", "[bold bright_white]BUILD[/]  [cyan]v0.2.0[/]")
            grid.add_row("[bold bright_red]ENGINE[/]  [bright_white]Dual LLM (NVIDIA NIM + Ollama)[/]", f"[bold bright_white]MODE[/]   [cyan]{mode}[/]")
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
        if _RICH_AVAILABLE and console is not None:
            console.print("[bold bright_yellow]◐ PROCESSING[/] [dim]Analyzing intent & retrieving knowledge...[/]")
        else:
            print("[PROC] Processing...")
            sys.stdout.flush()

    @staticmethod
    def print_user_input(text: str) -> None:
        """Display recognized or typed user utterance."""
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
        if _RICH_AVAILABLE and console is not None:
            console.print("\n[bold bright_red]■ SHUTDOWN[/] [dim]Terminating active loops... ULTRON offline.[/]\n")
        else:
            print("\n[BYE] Shutting down... ULTRON offline.\n")
            sys.stdout.flush()
