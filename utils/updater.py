"""
utils/updater.py – Self-Upgrade Engine for ULTRON CLI
======================================================
Handles automated updating of:
  1. Git repository (fetches and pulls latest commits from origin/main)
  2. Dependencies (uv sync / pip install)
  3. Database schema & persistent session verification
  4. Display of changelog and upgrade report
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _run_cmd(cmd: list[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Run a subprocess command and capture exit code, stdout, and stderr."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def get_current_git_info(repo_dir: Path) -> Dict[str, str]:
    """Get current git branch, commit hash, and commit subject."""
    info = {"branch": "unknown", "commit": "unknown", "subject": "unknown"}
    ret, out, _ = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    if ret == 0:
        info["branch"] = out

    ret, out, _ = _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir)
    if ret == 0:
        info["commit"] = out

    ret, out, _ = _run_cmd(["git", "log", "-1", "--format=%s"], cwd=repo_dir)
    if ret == 0:
        info["subject"] = out

    return info


async def run_upgrade(verbose: bool = True) -> bool:
    """Execute the complete upgrade workflow asynchronously."""
    repo_root = Path(__file__).resolve().parent.parent

    console.print(Panel(
        "[bold red]ULTRON[/bold red] [bold white]Self-Upgrade Engine[/bold white]\n"
        "[dim]Checking for upstream releases, synchronizing dependencies & database schemas...[/dim]",
        border_style="cyan",
        box=ROUNDED
    ))

    # 1. Inspect Git Repository
    if not (repo_root / ".git").exists():
        console.print("[yellow]⚠ Not a git repository. Skipping git pull step.[/yellow]")
        git_status = "Skipped (No .git folder)"
        changelog = "None"
    else:
        current = get_current_git_info(repo_root)
        console.print(f"[dim]Current version: [bold cyan]{current['commit']}[/bold cyan] ({current['branch']}) – {current['subject']}[/dim]")
        
        console.print("[cyan]→ Fetching upstream changes from origin/main...[/cyan]")
        ret, _, err = _run_cmd(["git", "fetch", "origin", "main", "--quiet"], cwd=repo_root)
        if ret != 0:
            console.print(f"[yellow]⚠ Git fetch warning: {err or 'Failed to reach remote'}[/yellow]")

        # Count commits behind
        ret, count_out, _ = _run_cmd(["git", "rev-list", "HEAD..origin/main", "--count"], cwd=repo_root)
        commits_behind = int(count_out) if ret == 0 and count_out.isdigit() else 0

        if commits_behind > 0:
            console.print(f"[bold green]Found {commits_behind} new commit(s) upstream.[/bold green] Pulling updates...")
            ret, pull_out, pull_err = _run_cmd(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=repo_root)
            if ret != 0:
                console.print(f"[bold red]✗ Git pull failed: {pull_err}[/bold red]")
                return False

            new_info = get_current_git_info(repo_root)
            git_status = f"Upgraded: {current['commit']} → {new_info['commit']}"

            # Fetch recent commit log
            ret, log_out, _ = _run_cmd(["git", "log", f"-n", str(min(commits_behind, 5)), "--oneline"], cwd=repo_root)
            changelog = log_out if ret == 0 else "Updated to latest"
            console.print(f"[bold green]✓ Repository updated successfully.[/bold green]")
        else:
            git_status = f"Up to date ({current['commit']})"
            changelog = "Already at latest version"
            console.print("[bold green]✓ Ultron is already at the latest release.[/bold green]")

    # 2. Sync Dependencies
    console.print("\n[cyan]→ Synchronizing Python dependencies...[/cyan]")
    uv_path = shutil.which("uv")
    if uv_path:
        ret, out, err = _run_cmd([uv_path, "sync"], cwd=repo_root)
        if ret == 0:
            dep_status = "Synchronized via uv ✓"
            console.print("[bold green]✓ Dependencies synchronized via uv.[/bold green]")
        else:
            dep_status = f"uv sync warning ({err[:40]})"
            console.print(f"[yellow]⚠ uv sync returned code {ret}: {err}[/yellow]")
    else:
        # Fallback to pip install -e .
        ret, out, err = _run_cmd([sys.executable, "-m", "pip", "install", "-e", "."], cwd=repo_root)
        if ret == 0:
            dep_status = "Installed via pip ✓"
            console.print("[bold green]✓ Package dependencies refreshed via pip.[/bold green]")
        else:
            dep_status = "pip install error"
            console.print(f"[yellow]⚠ pip install error: {err}[/yellow]")

    # 3. Verify Database and Persistence
    console.print("\n[cyan]→ Verifying database persistence & migrations...[/cyan]")
    try:
        from core.database import DatabaseManager
        db = DatabaseManager()
        await db.initialize()
        await db.close()
        db_status = "Verified & Migrated ✓"
        console.print("[bold green]✓ Database sessions & turn tables verified.[/bold green]")
    except Exception as e:
        db_status = f"Warning: {str(e)[:40]}"
        console.print(f"[yellow]⚠ Database verification notice: {e}[/yellow]")

    # 4. Summary Table
    table = Table(
        title="ULTRON Upgrade Summary",
        border_style="bright_blue",
        box=ROUNDED,
    )
    table.add_column("Component", style="bold cyan", width=22)
    table.add_column("Result", style="white", width=42)

    table.add_row("Git Repository", git_status)
    table.add_row("Dependencies", dep_status)
    table.add_row("Database Schemas", db_status)
    table.add_row("Recent Changes", changelog.split("\n")[0] if "\n" in changelog else changelog)

    console.print()
    console.print(table)
    console.print("[bold green]✓ ULTRON upgrade routine completed successfully![/bold green]\n")
    return True


def upgrade_cli() -> None:
    """Synchronous entry point for ultron upgrade command."""
    import asyncio
    try:
        asyncio.run(run_upgrade())
    except KeyboardInterrupt:
        console.print("\n[yellow]Upgrade interrupted by user.[/yellow]")
        sys.exit(130)
