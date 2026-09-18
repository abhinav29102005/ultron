"""
tests/test_updater.py – Comprehensive Test Suite for ULTRON Self-Upgrade Engine
"""

import pytest
from pathlib import Path
from utils.updater import (
    get_current_git_info,
    parse_upgrade_args,
    verify_voice_models,
    verify_database_integrity,
    check_system_environment,
    run_upgrade,
    upgrade_cli,
)


def test_get_current_git_info():
    """Verify git metadata retrieval from local repository."""
    repo_dir = Path(__file__).resolve().parent.parent
    info = get_current_git_info(repo_dir)

    assert "commit" in info
    assert "branch" in info
    assert "subject" in info
    assert "author" in info
    assert info["commit"] != "unknown"
    assert len(info["commit"]) >= 6


def test_parse_upgrade_args_defaults():
    """Verify default parsed arguments for upgrade command."""
    args = parse_upgrade_args([])
    assert args.check_only is False
    assert args.force is False
    assert args.branch is None
    assert args.remote == "origin"
    assert args.skip_deps is False
    assert args.skip_models is False
    assert args.as_json is False
    assert args.verbose is False


def test_parse_upgrade_args_flags():
    """Verify customized CLI flag parsing for upgrade command."""
    args = parse_upgrade_args([
        "--check",
        "--force",
        "--branch", "win",
        "--remote", "upstream",
        "--skip-deps",
        "--skip-models",
        "--json",
        "-v",
    ])
    assert args.check_only is True
    assert args.force is True
    assert args.branch == "win"
    assert args.remote == "upstream"
    assert args.skip_deps is True
    assert args.skip_models is True
    assert args.as_json is True
    assert args.verbose is True


def test_verify_voice_models():
    """Verify detection and size inspection of Piper TTS voice models."""
    repo_root = Path(__file__).resolve().parent.parent
    status, ok = verify_voice_models(repo_root, auto_download=False)
    assert isinstance(status, str)
    assert "bryce" in status.lower() or "lessac" in status.lower() or ok is True


def test_check_system_environment():
    """Verify Python version, virtualenv, and launcher detection."""
    repo_root = Path(__file__).resolve().parent.parent
    status, ok = check_system_environment(repo_root)
    assert ok is True
    assert "Python" in status


@pytest.mark.asyncio
async def test_verify_database_integrity():
    """Verify real database schema initialization and query test."""
    status, ok = await verify_database_integrity()
    assert ok is True
    assert "Verified & Migrated" in status
    assert "sessions" in status


@pytest.mark.asyncio
async def test_run_upgrade_dry_run():
    """Test dry-run upgrade workflow without making alterations."""
    res = await run_upgrade(check_only=True, verbose=False)
    assert res is True


@pytest.mark.asyncio
async def test_run_upgrade_json_mode(capsys):
    """Test machine-readable JSON output emission."""
    res = await run_upgrade(check_only=True, as_json=True)
    assert res is True
    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert data["success"] is True
    assert data["check_only"] is True
    assert "git_repository" in data
    assert "dependencies" in data
    assert "voice_models" in data
    assert "database_schemas" in data


@pytest.mark.asyncio
async def test_run_upgrade_skip_deps_and_models():
    """Test running with skip_deps and skip_models flags."""
    res = await run_upgrade(force=True, skip_deps=True, skip_models=True, verbose=False)
    assert res is True


def test_upgrade_cli_exit_code():
    """Test synchronous CLI wrapper exit codes."""
    code = upgrade_cli(["--check"])
    assert code == 0
