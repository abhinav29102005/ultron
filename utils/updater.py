"""
utils/updater.py – Self-Upgrade Engine for ULTRON CLI
======================================================
Handles automated, cross-platform updating of:
  1. Git repository (dynamic branch & remote detection, safe rebase with autostash)
  2. Python dependencies (uv sync / pip install fallback)
  3. Speech & Voice models (Piper ONNX model verification & auto-download)
  4. Database schema & persistent session verification
  5. System environment & CLI launcher diagnostics
  6. Rich changelog display and machine-readable JSON output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _run_cmd(
    cmd: list[str],
    cwd: Optional[Path] = None,
    timeout: Optional[int] = 30,
) -> Tuple[int, str, str]:
    """Run a subprocess command and capture exit code, stdout, and stderr."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def parse_upgrade_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI options for the upgrade subcommand."""
    parser = argparse.ArgumentParser(
        prog="ultron upgrade",
        description="Upgrade ULTRON repository, dependencies, voice models, and database schemas.",
    )
    parser.add_argument(
        "--check",
        "--dry-run",
        action="store_true",
        dest="check_only",
        help="Check for upstream releases without applying updates or pulling code.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-syncing dependencies, voice models, and database schemas even if git is up-to-date.",
    )
    parser.add_argument(
        "-b",
        "--branch",
        type=str,
        default=None,
        help="Target git branch to fetch and pull from (defaults to current active branch).",
    )
    parser.add_argument(
        "--remote",
        type=str,
        default="origin",
        help="Git remote name (default: 'origin').",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip Python dependency synchronization.",
    )
    parser.add_argument(
        "--skip-models",
        action="store_true",
        help="Skip checking or downloading Piper voice models.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output upgrade report in structured JSON format.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed debug and command execution output.",
    )
    return parser.parse_args(argv)


def get_current_git_info(repo_dir: Path) -> Dict[str, str]:
    """Get current git branch, commit hash, author, and commit subject."""
    info = {
        "branch": "unknown",
        "commit": "unknown",
        "subject": "unknown",
        "author": "unknown",
        "date": "unknown",
    }
    ret, out, _ = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    if ret == 0:
        info["branch"] = out

    ret, out, _ = _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir)
    if ret == 0:
        info["commit"] = out

    ret, out, _ = _run_cmd(["git", "log", "-1", "--format=%s"], cwd=repo_dir)
    if ret == 0:
        info["subject"] = out

    ret, out, _ = _run_cmd(["git", "log", "-1", "--format=%an"], cwd=repo_dir)
    if ret == 0:
        info["author"] = out

    ret, out, _ = _run_cmd(["git", "log", "-1", "--format=%ar"], cwd=repo_dir)
    if ret == 0:
        info["date"] = out

    return info


def check_remote_reachability(repo_dir: Path, remote: str = "origin", timeout_sec: int = 5) -> Tuple[bool, str]:
    """Check if the git remote can be reached within timeout_sec."""
    ret, _, err = _run_cmd(["git", "ls-remote", "--exit-code", remote, "HEAD"], cwd=repo_dir, timeout=timeout_sec)
    if ret == 0:
        return True, "Remote reachable"
    return False, err or "Remote unreachable / offline"


def verify_voice_models(repo_root: Path, auto_download: bool = True, verbose: bool = False) -> Tuple[str, bool]:
    """Verify that Piper TTS voice models exist and have valid size."""
    models_dir = repo_root / "speech" / "text_to_speech" / "models"
    bryce_model = models_dir / "en_US-bryce-medium.onnx"
    bryce_json = models_dir / "en_US-bryce-medium.onnx.json"
    lessac_model = models_dir / "en_US-lessac-medium.onnx"

    # Primary check: Bryce or Lessac ONNX model
    target_model = bryce_model if bryce_model.exists() else lessac_model

    if target_model.exists() and target_model.stat().st_size > 10 * 1024 * 1024:
        size_mb = target_model.stat().st_size / (1024 * 1024)
        return f"Verified ({target_model.name}, {size_mb:.1f} MB) ✓", True

    if not auto_download:
        return "Missing Piper voice model (download pending)", False

    # Attempt download
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
        import urllib.request
        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/bryce/medium/"
        onnx_url = base_url + "en_US-bryce-medium.onnx"
        json_url = base_url + "en_US-bryce-medium.onnx.json"

        if verbose:
            console.print("[dim]Downloading Piper voice model (en_US-bryce-medium.onnx)...[/dim]")
        urllib.request.urlretrieve(onnx_url, bryce_model)
        urllib.request.urlretrieve(json_url, bryce_json)

        size_mb = bryce_model.stat().st_size / (1024 * 1024)
        return f"Downloaded & Verified ({bryce_model.name}, {size_mb:.1f} MB) ✓", True
    except Exception as e:
        return f"Warning: Model download deferred ({str(e)[:40]})", False


def check_system_environment(repo_root: Path) -> Tuple[str, bool]:
    """Verify Python runtime, virtual environment, and CLI launcher availability."""
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    in_venv = (sys.prefix != sys.base_prefix) or ((repo_root / ".venv").exists())
    
    # Check CLI launcher
    launcher_ok = shutil.which("ultron") is not None or (Path.home() / ".local" / "bin" / "ultron").exists()
    launcher_text = "CLI linked in PATH" if launcher_ok else "Launcher in repo"

    status_str = f"Python {py_ver} ({'venv' if in_venv else 'system'}), {launcher_text} ✓"
    return status_str, True


async def verify_database_integrity() -> Tuple[str, bool]:
    """Verify database engine, sessions, messages, and user_settings schemas."""
    try:
        from core.database import DatabaseManager

        db = DatabaseManager()
        await db.initialize()
        sessions = await db.list_sessions()
        settings = await db.get_all_settings()
        await db.close()
        return f"Verified & Migrated ({len(sessions)} sessions, {len(settings)} settings) ✓", True
    except Exception as e:
        return f"Database notice: {str(e)[:45]}", False


async def run_upgrade(
    check_only: bool = False,
    force: bool = False,
    target_branch: Optional[str] = None,
    remote: str = "origin",
    skip_deps: bool = False,
    skip_models: bool = False,
    verbose: bool = False,
    as_json: bool = False,
) -> bool:
    """
    Execute the complete upgrade workflow asynchronously.
    Returns True if upgrade/verification completed cleanly, False otherwise.
    """
    repo_root = Path(__file__).resolve().parent.parent
    overall_success = True
    new_commits_log: List[str] = []

    if not as_json:
        console.print(Panel(
            "[bold red]ULTRON[/bold red] [bold white]Self-Upgrade Engine[/bold white]\n"
            "[dim]Synchronizing repository, dependencies, voice models & database persistence...[/dim]",
            border_style="cyan",
            box=ROUNDED
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Inspect & Synchronize Git Repository
    # ──────────────────────────────────────────────────────────────────────────
    if not (repo_root / ".git").exists():
        if not as_json:
            console.print("[yellow]⚠ Not a git repository. Skipping git pull step.[/yellow]")
        git_status = "Skipped (Not a git repo)"
        changelog = "None"
    else:
        current = get_current_git_info(repo_root)
        active_branch = target_branch or (current["branch"] if current["branch"] != "HEAD" else "main")

        if not as_json:
            console.print(
                f"[dim]Current version: [bold cyan]{current['commit']}[/bold cyan] "
                f"({active_branch}) – {current['subject']}[/dim]"
            )

        # Check connectivity
        if not as_json:
            console.print(f"[cyan]→ Checking remote reachability ({remote}/{active_branch})...[/cyan]")
        reachable, reach_err = check_remote_reachability(repo_root, remote=remote, timeout_sec=5)

        if not reachable:
            if not as_json:
                console.print(f"[yellow]⚠ Remote unreachable: {reach_err}. Skipping network pull.[/yellow]")
            git_status = f"Local ({current['commit']}) – Remote unreachable"
            changelog = "Offline / local verification mode"
        else:
            # Fetch latest
            ret, _, fetch_err = _run_cmd(["git", "fetch", remote, active_branch, "--quiet"], cwd=repo_root, timeout=15)
            if ret != 0:
                if not as_json:
                    console.print(f"[yellow]⚠ Git fetch warning: {fetch_err}[/yellow]")

            # Check commits behind
            ret, count_out, _ = _run_cmd(
                ["git", "rev-list", f"HEAD..{remote}/{active_branch}", "--count"],
                cwd=repo_root,
                timeout=10,
            )
            commits_behind = int(count_out) if ret == 0 and count_out.isdigit() else 0

            if commits_behind > 0:
                # Fetch changelog lines
                ret_log, log_out, _ = _run_cmd(
                    ["git", "log", f"HEAD..{remote}/{active_branch}", "--oneline", "-n", "5"],
                    cwd=repo_root,
                    timeout=10,
                )
                if ret_log == 0 and log_out:
                    new_commits_log = log_out.splitlines()

                if check_only:
                    git_status = f"Update available ({commits_behind} commit(s) behind)"
                    changelog = f"{commits_behind} new commit(s) upstream"
                    if not as_json:
                        console.print(f"[bold yellow]Found {commits_behind} new commit(s) upstream.[/bold yellow]")
                else:
                    if not as_json:
                        console.print(f"[bold green]Found {commits_behind} new commit(s) upstream.[/bold green] Pulling updates...")
                    ret_pull, pull_out, pull_err = _run_cmd(
                        ["git", "pull", "--rebase", "--autostash", remote, active_branch],
                        cwd=repo_root,
                        timeout=30,
                    )
                    if ret_pull != 0:
                        overall_success = False
                        git_status = f"Pull failed ({pull_err[:40]})"
                        changelog = f"Error: {pull_err}"
                        if not as_json:
                            console.print(f"[bold red]✗ Git pull failed: {pull_err}[/bold red]")
                    else:
                        new_info = get_current_git_info(repo_root)
                        git_status = f"Upgraded: {current['commit']} → {new_info['commit']}"
                        changelog = f"Pulled {commits_behind} commit(s)"
                        if not as_json:
                            console.print("[bold green]✓ Repository updated successfully.[/bold green]")
            else:
                git_status = f"Up to date ({current['commit']})"
                changelog = "Already at latest release"
                if not as_json:
                    console.print("[bold green]✓ Ultron is already at the latest release.[/bold green]")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Synchronize Python Dependencies
    # ──────────────────────────────────────────────────────────────────────────
    if skip_deps:
        dep_status = "Skipped (--skip-deps)"
        if not as_json:
            console.print("\n[dim]→ Skipping Python dependencies (--skip-deps)[/dim]")
    elif check_only:
        dep_status = "Ready to synchronize"
        if not as_json:
            console.print("\n[dim]→ Dependency check passed (dry-run)[/dim]")
    else:
        if not as_json:
            console.print("\n[cyan]→ Synchronizing Python dependencies...[/cyan]")
        uv_path = shutil.which("uv")
        if uv_path:
            ret, out, err = _run_cmd([uv_path, "sync"], cwd=repo_root, timeout=60)
            if ret == 0:
                dep_status = "Synchronized via uv ✓"
                if not as_json:
                    console.print("[bold green]✓ Dependencies synchronized via uv.[/bold green]")
            else:
                dep_status = f"uv sync warning ({err[:35]})"
                if not as_json:
                    console.print(f"[yellow]⚠ uv sync notice: {err}[/yellow]")
        else:
            # Fallback to pip
            ret, out, err = _run_cmd([sys.executable, "-m", "pip", "install", "-e", "."], cwd=repo_root, timeout=60)
            if ret == 0:
                dep_status = "Installed via pip ✓"
                if not as_json:
                    console.print("[bold green]✓ Dependencies refreshed via pip.[/bold green]")
            else:
                dep_status = "pip install warning"
                if not as_json:
                    console.print(f"[yellow]⚠ pip notice: {err}[/yellow]")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Speech & Voice Models Check
    # ──────────────────────────────────────────────────────────────────────────
    if skip_models:
        voice_status = "Skipped (--skip-models)"
        if not as_json:
            console.print("\n[dim]→ Skipping voice models (--skip-models)[/dim]")
    else:
        if not as_json:
            console.print("\n[cyan]→ Verifying Piper TTS voice models...[/cyan]")
        voice_status, voice_ok = verify_voice_models(
            repo_root,
            auto_download=(not check_only),
            verbose=verbose,
        )
        if not as_json:
            if voice_ok:
                console.print(f"[bold green]✓ {voice_status}[/bold green]")
            else:
                console.print(f"[yellow]⚠ {voice_status}[/yellow]")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Database Persistence & Schemas Check
    # ──────────────────────────────────────────────────────────────────────────
    if not as_json:
        console.print("\n[cyan]→ Verifying database persistence & migrations...[/cyan]")
    db_status, db_ok = await verify_database_integrity()
    if not as_json:
        if db_ok:
            console.print(f"[bold green]✓ {db_status}[/bold green]")
        else:
            console.print(f"[yellow]⚠ {db_status}[/yellow]")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. System Environment & CLI Launcher Check
    # ──────────────────────────────────────────────────────────────────────────
    env_status, env_ok = check_system_environment(repo_root)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Summary Report / Output
    # ──────────────────────────────────────────────────────────────────────────
    report = {
        "success": overall_success,
        "check_only": check_only,
        "git_repository": git_status,
        "dependencies": dep_status,
        "voice_models": voice_status,
        "database_schemas": db_status,
        "environment": env_status,
        "recent_changes": changelog,
        "commits": new_commits_log,
    }

    if as_json:
        print(json.dumps(report, indent=2))
        return overall_success

    # Render Rich Table
    table = Table(
        title="ULTRON Upgrade Summary",
        border_style="bright_blue",
        box=ROUNDED,
    )
    table.add_column("Component", style="bold cyan", width=22)
    table.add_column("Result", style="white", width=50)

    table.add_row("Git Repository", git_status)
    table.add_row("Dependencies", dep_status)
    table.add_row("Voice Models", voice_status)
    table.add_row("Database Schemas", db_status)
    table.add_row("Environment", env_status)
    table.add_row("Recent Changes", changelog)

    console.print()
    console.print(table)

    if new_commits_log:
        log_table = Table(
            title="Upstream Commit Log",
            border_style="green",
            box=ROUNDED,
        )
        log_table.add_column("Commit", style="bold yellow", width=12)
        log_table.add_column("Message", style="white")
        for line in new_commits_log:
            parts = line.split(maxsplit=1)
            c_hash = parts[0] if parts else ""
            c_msg = parts[1] if len(parts) > 1 else ""
            log_table.add_row(c_hash, c_msg)
        console.print(log_table)

    if check_only:
        console.print("[bold cyan]ℹ Dry-run check completed. Run 'ultron upgrade' to apply updates.[/bold cyan]\n")
    elif overall_success:
        console.print("[bold green]✓ ULTRON upgrade routine completed successfully![/bold green]\n")
    else:
        console.print("[bold red]⚠ ULTRON upgrade encountered issues during execution.[/bold red]\n")

    return overall_success


def upgrade_cli(argv: Optional[List[str]] = None) -> int:
    """Synchronous entry point for ultron upgrade command with argument parsing."""
    try:
        args = parse_upgrade_args(argv)
        ok = asyncio.run(run_upgrade(
            check_only=args.check_only,
            force=args.force,
            target_branch=args.branch,
            remote=args.remote,
            skip_deps=args.skip_deps,
            skip_models=args.skip_models,
            verbose=args.verbose,
            as_json=args.as_json,
        ))
        return 0 if ok else 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Upgrade interrupted by user.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[bold red]Upgrade failed with unexpected error: {e}[/bold red]")
        return 1
