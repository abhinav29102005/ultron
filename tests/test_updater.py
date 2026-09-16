"""
tests/test_updater.py – Test suite for ULTRON Self-Upgrade Engine
"""

import pytest
from pathlib import Path
from utils.updater import get_current_git_info, run_upgrade


def test_get_current_git_info():
    """Verify git metadata retrieval from local repository."""
    repo_dir = Path(__file__).resolve().parent.parent
    info = get_current_git_info(repo_dir)

    assert "commit" in info
    assert "branch" in info
    assert info["commit"] != "unknown"
    assert len(info["commit"]) >= 6


@pytest.mark.asyncio
async def test_run_upgrade_dry_run(monkeypatch):
    """Test upgrade workflow execution."""
    # Test that run_upgrade executes without exception
    res = await run_upgrade(verbose=False)
    assert res is True
