"""
utils/api_key_manager.py – Interactive Cloud LLM API Key Wizard & Provider Hub
================================================================================
Provides interactive key configuration, validation, and direct portal links
for major cloud LLM providers:
  1. NVIDIA NIM (1,000 Free Credits): https://build.nvidia.com/
  2. Groq Cloud (Free Tier, High Speed): https://console.groq.com/keys
  3. OpenRouter (100+ Models Aggregator): https://openrouter.ai/keys
  4. OpenAI Platform (GPT-4o, Embeddings): https://platform.openai.com/api-keys
  5. Anthropic Claude (Claude 3.5 Sonnet): https://console.anthropic.com/
  6. Picovoice (Porcupine Wake Word): https://console.picovoice.ai/
  7. Local Ollama (Zero keys, Offline): http://localhost:11434
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass
class ProviderInfo:
    id: str
    name: str
    env_var: str
    portal_url: str
    free_tier_info: str
    recommended_models: str
    prefix_hint: str = ""


PROVIDERS: Dict[str, ProviderInfo] = {
    "nvidia": ProviderInfo(
        id="nvidia",
        name="NVIDIA NIM",
        env_var="NVIDIA_API_KEY",
        portal_url="https://build.nvidia.com/",
        free_tier_info="1,000 Free API credits upon signup (No credit card)",
        recommended_models="nvidia/nemotron-3-super-120b-a12b, meta/llama-3.3-70b-instruct",
        prefix_hint="nvapi-",
    ),
    "groq": ProviderInfo(
        id="groq",
        name="Groq Cloud",
        env_var="GROQ_API_KEY",
        portal_url="https://console.groq.com/keys",
        free_tier_info="Free high-speed inference tier (~500+ tok/s)",
        recommended_models="llama-3.3-70b-versatile, mixtral-8x7b-32768",
        prefix_hint="gsk_",
    ),
    "openrouter": ProviderInfo(
        id="openrouter",
        name="OpenRouter",
        env_var="OPENROUTER_API_KEY",
        portal_url="https://openrouter.ai/keys",
        free_tier_info="Aggregated access to 100+ models with free test tiers",
        recommended_models="deepseek/deepseek-chat, anthropic/claude-3.5-sonnet",
        prefix_hint="sk-or-",
    ),
    "openai": ProviderInfo(
        id="openai",
        name="OpenAI Platform",
        env_var="OPENAI_API_KEY",
        portal_url="https://platform.openai.com/api-keys",
        free_tier_info="Pay-as-you-go / Trial credits",
        recommended_models="gpt-4o, text-embedding-3-small",
        prefix_hint="sk-",
    ),
    "anthropic": ProviderInfo(
        id="anthropic",
        name="Anthropic Claude",
        env_var="ANTHROPIC_API_KEY",
        portal_url="https://console.anthropic.com/",
        free_tier_info="Developer console access (Claude 3.5 Sonnet / Haiku)",
        recommended_models="claude-3-5-sonnet-20241022",
        prefix_hint="sk-ant-",
    ),
    "picovoice": ProviderInfo(
        id="picovoice",
        name="Picovoice (Porcupine)",
        env_var="PICOVOICE_ACCESS_KEY",
        portal_url="https://console.picovoice.ai/",
        free_tier_info="Free personal tier for custom wake word detection",
        recommended_models="Ultron wake word model",
        prefix_hint="",
    ),
}


def update_env_file(key: str, value: str, env_path: str = ".env") -> bool:
    """Update or append an environment variable in the .env file."""
    path = Path(env_path)
    if not path.exists():
        example = Path(".env.example")
        if example.exists():
            content = example.read_text(encoding="utf-8")
        else:
            content = ""
    else:
        content = path.read_text(encoding="utf-8")

    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"

    if re.search(pattern, content, flags=re.MULTILINE):
        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip() + "\n" + f"{key}={value}\n"

    path.write_text(new_content, encoding="utf-8")
    os.environ[key] = value
    return True


def render_provider_hub() -> None:
    """Render a comprehensive table of cloud LLM panels with direct access URLs."""
    table = Table(
        title="ULTRON Cloud LLM & API Key Hub",
        border_style="bright_blue",
        box=ROUNDED,
    )
    table.add_column("Provider", style="bold cyan", width=18)
    table.add_column("Portal Link (Get Free Keys)", style="bright_green", width=36)
    table.add_column("Free Tier & Capacity", style="white", width=34)
    table.add_column("Key Status", justify="center", width=14)

    for p in PROVIDERS.values():
        val = os.getenv(p.env_var, "")
        status = "[bold green]CONFIGURED ✓[/bold green]" if (val and not val.startswith("your_")) else "[dim]NOT SET[/dim]"
        table.add_row(p.name, p.portal_url, p.free_tier_info, status)

    console.print(table)
    console.print(
        "[dim]To set a key anytime, run [bold cyan]/setup[/bold cyan] or type [bold cyan]/key <provider> <api_key>[/bold cyan] "
        "(e.g., [bold cyan]/key nvidia nvapi-xxxx[/bold cyan]).[/dim]\n"
    )


def set_key_for_provider(provider_id: str, key_value: str) -> Tuple[bool, str]:
    """Validate and set key for a provider."""
    provider_id = provider_id.lower().strip()
    if provider_id not in PROVIDERS:
        avail = ", ".join(PROVIDERS.keys())
        return False, f"Unknown provider '{provider_id}'. Available: {avail}"

    info = PROVIDERS[provider_id]
    key_value = key_value.strip()

    if not key_value:
        return False, "Key value cannot be empty."

    update_env_file(info.env_var, key_value)
    return True, f"Successfully saved {info.name} API key to .env ({info.env_var})"


def has_any_cloud_key() -> bool:
    """Check if at least one cloud LLM API key is present and configured."""
    for p in PROVIDERS.values():
        val = os.getenv(p.env_var, "").strip()
        if val and not val.startswith("your_"):
            return True
    return False


async def prompt_first_run_if_needed(cli=None, container=None) -> None:
    """
    Prompt the user on CLI startup if no cloud LLM API keys are detected.
    Provides direct links and options to get free keys from cloud provider panels.
    """
    import asyncio

    if container and hasattr(container, "user_settings"):
        if container.user_settings.execution_mode == "offline":
            return

    if has_any_cloud_key():
        return

    notice = (
        "[bold yellow]⚡ No Cloud LLM API Keys Detected[/bold yellow]\n"
        "[white]Ultron can query free high-performance cloud models or run 100% offline via local Ollama.[/white]\n\n"
        "[bold green]Get Free Keys From Provider Developer Panels:[/bold green]\n"
        "  • [bold cyan]NVIDIA NIM[/bold cyan] (1,000 Free Credits): [underline green]https://build.nvidia.com/[/underline green]\n"
        "  • [bold cyan]Groq Cloud[/bold cyan] (High-Speed Free Tier): [underline green]https://console.groq.com/keys[/underline green]\n"
        "  • [bold cyan]OpenRouter[/bold cyan] (100+ Models Aggregator): [underline green]https://openrouter.ai/keys[/underline green]\n"
        "  • [bold cyan]Local Ollama[/bold cyan] (Zero keys, Offline): [underline cyan]http://localhost:11434[/underline cyan]"
    )
    console.print(Panel(notice, border_style="yellow", box=ROUNDED))

    try:
        choice = await asyncio.to_thread(
            input,
            "Configure API key now? [ (y)es / (o)ffline / (s)kip ]: "
        )
        choice = choice.strip().lower()
        if choice in ("y", "yes", "setup"):
            await interactive_setup_wizard(cli=cli)
        elif choice in ("o", "offline"):
            if cli and hasattr(cli, "settings") and hasattr(cli, "sm"):
                await cli.settings.update_setting(cli.sm.db, "execution_mode", "offline")
                console.print("[bold green]✓ Switched to 100% Offline Mode (Local Ollama).[/bold green]\n")
            elif container and hasattr(container, "user_settings"):
                container.user_settings.execution_mode = "offline"
                console.print("[bold green]✓ Switched to 100% Offline Mode (Local Ollama).[/bold green]\n")
        else:
            console.print("[dim]Skipped key setup. Type [bold cyan]/setup[/bold cyan] anytime to add keys.[/dim]\n")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Skipped setup.[/dim]\n")


async def interactive_setup_wizard(cli=None) -> None:
    """Run an interactive console walkthrough to view links and configure keys."""
    import asyncio

    console.print(Panel(
        "[bold red]ULTRON[/bold red] [bold white]Interactive Cloud API Key Setup Wizard[/bold white]\n"
        "[dim]Obtain free inference keys from provider panels below or switch to local Ollama.[/dim]",
        border_style="cyan",
        box=ROUNDED
    ))
    render_provider_hub()

    console.print("[bold yellow]Select a provider to configure:[/bold yellow]")
    console.print("  [bold cyan]1[/bold cyan]. NVIDIA NIM ([green]1,000 Free Credits[/green] – Recommended)")
    console.print("  [bold cyan]2[/bold cyan]. Groq Cloud ([green]Free High-Speed Tier[/green])")
    console.print("  [bold cyan]3[/bold cyan]. OpenRouter ([green]100+ Models Aggregator[/green])")
    console.print("  [bold cyan]4[/bold cyan]. OpenAI Platform (GPT-4o)")
    console.print("  [bold cyan]5[/bold cyan]. Anthropic Claude (Claude 3.5 Sonnet)")
    console.print("  [bold cyan]6[/bold cyan]. Picovoice AccessKey (Porcupine wake word)")
    console.print("  [bold cyan]7[/bold cyan]. Switch to 100% Offline Mode (Local Ollama, zero keys)")
    console.print("  [bold cyan]0[/bold cyan]. Back / Done\n")

    try:
        choice = await asyncio.to_thread(input, "Select option (0-7): ")
        choice = choice.strip()

        target_map = {
            "1": "nvidia",
            "2": "groq",
            "3": "openrouter",
            "4": "openai",
            "5": "anthropic",
            "6": "picovoice",
        }

        if choice in target_map:
            p_id = target_map[choice]
            info = PROVIDERS[p_id]
            console.print(f"\n[bold green]Provider Portal:[/bold green] [underline cyan]{info.portal_url}[/underline cyan]")
            console.print(f"[bold white]Free Tier / Info:[/bold white] [dim]{info.free_tier_info}[/dim]")
            console.print(f"[bold white]Recommended Models:[/bold white] [dim]{info.recommended_models}[/dim]")
            if info.prefix_hint:
                console.print(f"[dim]Key format hint: Starts with '{info.prefix_hint}'[/dim]")

            val = await asyncio.to_thread(input, f"Paste your {info.name} API key (or Enter to cancel): ")
            val = val.strip()
            if val:
                ok, msg = set_key_for_provider(p_id, val)
                if ok:
                    console.print(f"[bold green]✓ {msg}[/bold green]\n")
                    if cli and hasattr(cli, "render_header"):
                        cli.render_header()
                else:
                    console.print(f"[bold red]✗ {msg}[/bold red]\n")
            else:
                console.print("[yellow]Cancelled input.[/yellow]\n")

        elif choice == "7":
            if cli and hasattr(cli, "settings") and hasattr(cli, "sm"):
                await cli.settings.update_setting(cli.sm.db, "execution_mode", "offline")
                console.print("[bold green]✓ Switched to 100% Offline Mode (Local Ollama). Zero cloud keys required.[/bold green]\n")
                if hasattr(cli, "render_header"):
                    cli.render_header()
            else:
                update_env_file("LLM_PROVIDER", "qwen")
                console.print("[bold green]✓ Configured LLM_PROVIDER=qwen in .env.[/bold green]\n")

        elif choice in ("0", "done", "q", "exit"):
            console.print("[dim]Returning to main session.[/dim]\n")
            return

    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled setup wizard.[/dim]\n")
