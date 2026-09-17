"""
tests/test_windows_powershell_cli.py - Validation for Windows PowerShell CLI capabilities
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.user_settings import UserSettings
from skills.system_skills import ApplicationSkill
from utils.cli_dashboard import CyberneticCLI


def test_ultron_ps1_exists():
    root = Path(__file__).resolve().parent.parent
    ps1 = root / "ultron.ps1"
    assert ps1.exists(), "ultron.ps1 launcher must exist in repo root"
    content = ps1.read_text(encoding="utf-8")
    assert "UTF8" in content
    assert "run.py" in content


def test_application_skill_cli_and_terminal_aliases():
    skill = ApplicationSkill()
    assert "cli" in skill.APP_ALIASES
    assert skill.APP_ALIASES["cli"] == "powershell"
    assert skill.APP_ALIASES["pwsh"] == "powershell"
    assert skill.APP_ALIASES["terminal"] == "terminal"

    # On Windows, terminal should map to powershell.exe
    assert skill.WINDOWS_APPS["terminal"]["open"] == "powershell.exe"
    assert skill.WINDOWS_APPS["terminal"]["close"] == "powershell.exe"
    assert skill.WINDOWS_APPS["powershell"]["open"] == "powershell.exe"


@pytest.mark.asyncio
async def test_cybernetic_cli_handles_ps_commands():
    sm = MagicMock()
    settings = UserSettings()
    cli = CyberneticCLI(sm, settings)

    with patch.object(cli, "execute_powershell_command", new_callable=AsyncMock) as mock_exec:
        # 1. Slash /ps
        handled = await cli.handle_command("/ps Get-Process")
        assert handled is True
        mock_exec.assert_awaited_once_with("Get-Process")

    with patch.object(cli, "execute_powershell_command", new_callable=AsyncMock) as mock_exec:
        # 2. Exclamation prefix !
        handled = await cli.handle_command("!echo 'hello from ps'")
        assert handled is True
        mock_exec.assert_awaited_once_with("echo 'hello from ps'")

    with patch.object(cli, "execute_powershell_command", new_callable=AsyncMock) as mock_exec:
        # 3. /powershell
        handled = await cli.handle_command("/powershell Get-Date")
        assert handled is True
        mock_exec.assert_awaited_once_with("Get-Date")


@pytest.mark.asyncio
async def test_cybernetic_cli_ps_guardrails_blocks_destructive():
    sm = MagicMock()
    settings = UserSettings(guardrails_enabled=True)
    cli = CyberneticCLI(sm, settings)

    with patch("rich.console.Console.print") as mock_print:
        # Dangerous encoded command or destructive command
        await cli.execute_powershell_command("powershell.exe -enc dGVzdA==")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        assert "🛡️" in printed or "blocked" in printed.lower() or "prohibited" in printed.lower()


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell required")
async def test_live_powershell_execution():
    sm = MagicMock()
    settings = UserSettings(guardrails_enabled=True)
    cli = CyberneticCLI(sm, settings)

    with patch("rich.console.Console.print") as mock_print:
        await cli.execute_powershell_command("Write-Output 'ULTRON_PS_OK'")
        printed = " ".join(str(call) for call in mock_print.call_args_list)
        assert "ULTRON_PS_OK" in printed
