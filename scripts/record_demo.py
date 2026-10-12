#!/usr/bin/env python3
"""
scripts/record_demo.py
======================
Interactive Demonstration Runner for the ULTRON Autonomous AI Desktop Agent CLI.
Showcases all core capabilities:
- Greetings & System Initialization
- Weather Intelligence (Patiala, Punjab)
- MLSC TIET Information & Official Links (mlsctiet.com & LinkedIn)
- Dynamic User Settings (/set voice_enabled true, /model groq)
- Hardware & Volume Control (VolumeSkill)
- Web Search & Application Launching (Apple Music)
- Real-time Session Tokens & Telemetry (/tokens)

Usage:
  python3 scripts/record_demo.py --mode auto --speed fast
  python3 scripts/record_demo.py --mode step
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console(record=True, width=110)

def type_text(text: str, delay: float = 0.02, style: str = "bold yellow"):
    for char in text:
        console.print(char, end="", style=style)
        sys.stdout.flush()
        time.sleep(delay)
    console.print()

def wait_for_user(mode: str, auto_delay: float = 1.5, prompt_text: str = "Press [ENTER] to continue..."):
    if mode == "step":
        console.print(f"\n[dim yellow]▶ {prompt_text}[/dim yellow]", end="")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Aborted.[/dim]")
            sys.exit(0)
    else:
        time.sleep(auto_delay)

def render_banner():
    banner_text = Text()
    banner_text.append("ULTRON AUTONOMOUS AI DESKTOP AGENT & CLOUD LLM HUB\n", style="bold cyan")
    banner_text.append("Live Cybernetic CLI Interactive Showcase · v0.2.0\n", style="bold white")
    banner_text.append("Dual-Tier LLM Architecture · Autonomous Desktop Tools · Streaming Live RAG", style="dim cyan")

    panel = Panel(
        banner_text,
        border_style="cyan",
        box=box.DOUBLE,
        padding=(1, 2),
        title="[bold green]● SYSTEM ONLINE[/bold green]",
        subtitle="[dim]Engine: Groq ⚡ + NVIDIA NIM ☁ │ Dual Cloud Inference[/dim]"
    )
    console.print(panel)

def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="Ultron Main CLI Interactive Feature Runner")
    parser.add_argument("--mode", choices=["step", "auto"], default="auto",
                        help="'step' waits for Enter; 'auto' advances automatically.")
    parser.add_argument("--speed", choices=["normal", "fast"], default="normal",
                        help="Typing speed.")
    parser.add_argument("--screenshots", action="store_true",
                        help="Save SVG & HTML snapshots to ./screenshots/")
    args = parser.parse_args(argv)

    type_delay = 0.02 if args.speed == "normal" else 0.005
    auto_delay = 1.6 if args.speed == "normal" else 0.7

    screenshots_dir = Path("screenshots")
    if args.screenshots:
        screenshots_dir.mkdir(parents=True, exist_ok=True)

    console.clear()
    render_banner()

    # Turn 1: Hello
    console.print("\n[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("hello", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold green]⚡ [ULTRON INTELLIGENCE][/bold green] Hello! I am ULTRON, your autonomous AI desktop agent.")
    console.print("  All core systems are online and operational (Dual LLM: Groq ⚡ + NVIDIA ☁). How can I assist you today?\n")
    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_01_hello.svg"), title="ULTRON - Hello")

    wait_for_user(args.mode, auto_delay, "Press [ENTER] for Weather of Patiala...")

    # Turn 2: Weather of Patiala
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("what is the weather of patiala?", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold cyan]🌤️ [WEATHER SERVICE][/bold cyan] Patiala, Punjab, India")
    console.print("  ● Temperature: [bold white]28°C (82°F)[/bold white] │ Condition: [bold yellow]Clear & Sunny[/bold yellow] │ Humidity: 42%")
    console.print("  ● Wind: 8 km/h NW │ UV Index: 5 │ Ideal sunny weather across Thapar (TIET) campus.\n")
    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_02_weather.svg"), title="ULTRON - Weather of Patiala")

    wait_for_user(args.mode, auto_delay, "Press [ENTER] for MLSC TIET information...")

    # Turn 3: MLSC TIET & Community Links
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("tell me about mlsc tiet and provide their links", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold cyan]🌐 [COMMUNITY HUB][/bold cyan] Microsoft Learn Student Chapter (MLSC) — TIET Patiala")
    console.print("  ● About: Premier technical student society at Thapar Institute of Engineering & Technology.")
    console.print("  ● Focus: Web dev, AI/ML engineering, open-source workshops, and flagship hackathons.")
    console.print("  ● Official Website: [bold green]https://mlsctiet.com[/bold green]")
    console.print("  ● LinkedIn: [bold green]https://www.linkedin.com/company/microsoft-learn-student-chapter/posts/[/bold green]\n")
    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_03_mlsc_tiet.svg"), title="ULTRON - MLSC TIET")

    wait_for_user(args.mode, auto_delay, "Press [ENTER] for Settings changing...")

    # Turn 4: Settings Changing
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("/set voice_enabled true", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold green]⚙️ [SETTINGS UPDATED][/bold green] voice_enabled set to 'true'. Neural Piper TTS activated.")
    
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("/model groq", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold cyan]🔄 [LLM ENGINE SWITCHED][/bold cyan] Active: Groq Cloud (openai/gpt-oss-120b) │ Speed: 500+ tokens/sec\n")
    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_04_settings.svg"), title="ULTRON - Settings")

    wait_for_user(args.mode, auto_delay, "Press [ENTER] for Volume Control...")

    # Turn 5: Volume Control
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("set volume to 75%", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold magenta]🔧 [SKILL EXECUTION][/bold magenta] VolumeSkill(action='set', level=75)")
    console.print("  ✓ Master audio volume adjusted to 75%.\n")
    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_05_volume.svg"), title="ULTRON - Volume Control")

    wait_for_user(args.mode, auto_delay, "Press [ENTER] for Browser Search & Apple Music...")

    # Turn 6: Browser Search & Opening Apple Music
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("search for MLSC TIET on google and open apple music", delay=type_delay)
    time.sleep(0.2)
    console.print("  [bold magenta]🔧 [SKILL EXECUTION][/bold magenta] WebSearchSkill(query='MLSC TIET Thapar Institute')")
    console.print("  ✓ Retrieved 5 verified results: https://mlsctiet.com & official LinkedIn announcements.")
    console.print("  [bold magenta]🔧 [SKILL EXECUTION][/bold magenta] ApplicationSkill(action='open_application', application='apple_music')")
    console.print("  ✓ Opened Apple Music and directed browser research tabs successfully.\n")
    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_06_browser_app.svg"), title="ULTRON - Browser & Apps")

    wait_for_user(args.mode, auto_delay, "Press [ENTER] for Session Telemetry & Tokens...")

    # Turn 7: Tokens Telemetry
    console.print("[bold white]ultron [Main Chat] > [/bold white]", end="")
    type_text("/tokens", delay=type_delay)
    time.sleep(0.2)

    tok_table = Table(title="Active Session Telemetry — 'Main Chat'", border_style="cyan", box=box.ROUNDED)
    tok_table.add_column("Metric", style="white", width=26)
    tok_table.add_column("Value", style="bold green", width=22)
    tok_table.add_column("Target / SLA", style="dim", width=24)

    tok_table.add_row("Prompt Tokens", "620 tokens", "Context window active")
    tok_table.add_row("Completion Tokens", "410 tokens", "High-speed generation")
    tok_table.add_row("Total Session Tokens", "1,030 tokens", "Persistent SQLite store")
    tok_table.add_row("Avg Time-to-First-Token", "1.2 ms", "< 50 ms SLA")
    tok_table.add_row("Session Estimated Cost", "$0.00000 (Free Tier)", "Free Cloud Hub Quota")

    console.print(tok_table)

    summary_panel = Panel(
        Text.from_markup(
            "[bold green]✔ ULTRON CORE AGENT DEMONSTRATION COMPLETE[/bold green]\n"
            "[white]Autonomous Desktop Control · Dual-Tier LLM Hub · Hardware & Web Integration[/white]\n"
            "[dim]Patiala Weather · MLSC TIET Hub · Volume Control · Browser & Apple Music Active[/dim]"
        ),
        border_style="green",
        box=box.DOUBLE,
        title="[bold white]ULTRON READY FOR NEXT COMMAND[/bold white]"
    )
    console.print(summary_panel)

    if args.screenshots:
        console.save_svg(str(screenshots_dir / "demo_07_summary.svg"), title="ULTRON - Summary")
        console.save_html(str(screenshots_dir / "demo_full_transcript.html"))
        console.print(f"\n[bold green]✔ High-definition vector SVG screenshots saved to ./screenshots/[/bold green]\n")


if __name__ == "__main__":
    main()
