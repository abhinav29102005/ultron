"""
tests/test_autostart.py – Tests for Windows login autostart registration
=========================================================================
Every test that writes to the registry is redirected onto a throwaway key,
``HKCU\\Software\\FridayAgentTest\\Run``, by the ``sandbox_key`` fixture. The
user's real Run key is never opened for writing by this test module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from utils import autostart

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="autostart registration is Windows-only"
)

TEST_KEY_PATH = r"Software\FridayAgentTest\Run"
TEST_KEY_PARENT = r"Software\FridayAgentTest"
TEST_VALUE_NAME = "UltronAssistantTest"


def _delete_test_tree() -> None:
    """Remove the sandbox key, ignoring the case where it was never created."""
    import winreg

    for path in (TEST_KEY_PATH, TEST_KEY_PARENT):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass


@pytest.fixture
def sandbox_key(monkeypatch: pytest.MonkeyPatch):
    """Point the module at a disposable registry key and clean it up afterwards."""
    monkeypatch.setattr(autostart, "RUN_KEY_PATH", TEST_KEY_PATH)
    monkeypatch.setattr(autostart, "VALUE_NAME", TEST_VALUE_NAME)
    _delete_test_tree()
    try:
        yield
    finally:
        _delete_test_tree()


# ── Path / command construction ───────────────────────────────────────────────

class TestCommandConstruction:
    """The command must survive being run from an arbitrary working directory."""

    def test_repo_root_is_the_project_directory(self) -> None:
        root = autostart.repo_root()
        assert root.is_absolute()
        assert (root / "utils" / "autostart.py").is_file()
        assert (root / "main_gui.py").is_file()

    def test_launcher_script_exists(self) -> None:
        script = autostart.launcher_script()
        assert script.is_absolute()
        assert script.is_file(), "scripts/ultron_launcher.pyw must ship with the repo"

    def test_uses_windowed_interpreter_so_no_console_appears(self) -> None:
        exe = autostart.pythonw_executable()
        assert exe.is_absolute()
        assert exe.is_file()
        assert exe.name.lower() == "pythonw.exe", (
            "a console-subsystem python.exe would pop a black window on every boot"
        )

    def test_prefers_the_project_venv_interpreter(self) -> None:
        venv_pythonw = autostart.repo_root() / ".venv" / "Scripts" / "pythonw.exe"
        if not venv_pythonw.is_file():
            pytest.skip("project venv not present in this environment")
        assert autostart.pythonw_executable() == venv_pythonw

    def test_command_paths_are_absolute_and_quoted(self) -> None:
        command = autostart.build_command()
        # Two quoted, absolute arguments: interpreter and launcher script.
        assert command.count('"') == 4
        assert command.startswith('"')
        interpreter, script = [part for part in command.split('" "')]
        interpreter = interpreter.lstrip('"')
        script = script.rstrip('"')
        assert Path(interpreter).is_absolute()
        assert Path(script).is_absolute()
        assert Path(interpreter).is_file()
        assert Path(script).is_file()

    def test_command_contains_no_relative_path_segments(self) -> None:
        # The working directory at login is C:\Windows\system32, so anything
        # relative would resolve against the wrong directory.
        command = autostart.build_command()
        assert ".\\" not in command
        assert "..\\" not in command


# ── enable / disable / is_enabled ─────────────────────────────────────────────

class TestEnableDisable:

    def test_disabled_by_default(self, sandbox_key: None) -> None:
        assert autostart.is_enabled() is False

    def test_enable_then_is_enabled(self, sandbox_key: None) -> None:
        autostart.enable()
        assert autostart.is_enabled() is True

    def test_enable_writes_the_expected_command(self, sandbox_key: None) -> None:
        import winreg

        autostart.enable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH) as key:
            value, value_type = winreg.QueryValueEx(key, TEST_VALUE_NAME)
        assert value == autostart.build_command()
        assert value_type == winreg.REG_SZ

    def test_enable_is_idempotent_no_duplicate_entries(self, sandbox_key: None) -> None:
        import winreg

        autostart.enable()
        autostart.enable()
        autostart.enable()

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH) as key:
            value_count = winreg.QueryInfoKey(key)[1]
        assert value_count == 1, "enable() must overwrite, never append a second entry"
        assert autostart.is_enabled() is True

    def test_disable_removes_the_entry(self, sandbox_key: None) -> None:
        autostart.enable()
        assert autostart.is_enabled() is True
        autostart.disable()
        assert autostart.is_enabled() is False

    def test_disable_is_idempotent_when_already_disabled(self, sandbox_key: None) -> None:
        autostart.enable()
        autostart.disable()
        autostart.disable()  # must not raise
        autostart.disable()
        assert autostart.is_enabled() is False

    def test_disable_when_key_never_existed(self, sandbox_key: None) -> None:
        # Nothing has created the sandbox key at this point.
        autostart.disable()  # must not raise
        assert autostart.is_enabled() is False

    def test_enable_disable_cycle_leaves_no_residue(self, sandbox_key: None) -> None:
        import winreg

        autostart.enable()
        autostart.disable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH) as key:
            assert winreg.QueryInfoKey(key)[1] == 0

    def test_disable_leaves_other_entries_untouched(self, sandbox_key: None) -> None:
        """Only the value we own may be deleted -- never a neighbour's entry."""
        import winreg

        autostart.enable()
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, TEST_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "SomeOtherApp", 0, winreg.REG_SZ, "C:\\other.exe")

        autostart.disable()

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH) as key:
            survivor, _ = winreg.QueryValueEx(key, "SomeOtherApp")
        assert survivor == "C:\\other.exe"

    def test_enable_repairs_a_stale_command(self, sandbox_key: None) -> None:
        """Re-enabling after a repo move must rewrite the paths, not duplicate."""
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, TEST_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, TEST_VALUE_NAME, 0, winreg.REG_SZ, '"C:\\old\\pythonw.exe" "C:\\old\\x.pyw"'
            )

        autostart.enable()

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, TEST_VALUE_NAME)
            assert winreg.QueryInfoKey(key)[1] == 1
        assert value == autostart.build_command()


# ── status ────────────────────────────────────────────────────────────────────

class TestStatus:

    def test_status_shape(self, sandbox_key: None) -> None:
        info = autostart.status()
        for field in (
            "enabled",
            "method",
            "target",
            "expected",
            "up_to_date",
            "registry_key",
            "value_name",
            "python",
            "script",
            "supported",
        ):
            assert field in info, f"status() must report {field!r}"

    def test_status_when_disabled(self, sandbox_key: None) -> None:
        info = autostart.status()
        assert info["enabled"] is False
        assert info["target"] is None
        assert info["up_to_date"] is False

    def test_status_when_enabled(self, sandbox_key: None) -> None:
        autostart.enable()
        info = autostart.status()
        assert info["enabled"] is True
        assert info["target"] == autostart.build_command()
        assert info["up_to_date"] is True
        assert info["method"] == autostart.METHOD
        assert info["value_name"] == TEST_VALUE_NAME
        assert info["registry_key"] == rf"HKEY_CURRENT_USER\{TEST_KEY_PATH}"

    def test_status_flags_a_stale_registration(self, sandbox_key: None) -> None:
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, TEST_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, TEST_VALUE_NAME, 0, winreg.REG_SZ, "C:\\moved\\away.exe")

        info = autostart.status()
        assert info["enabled"] is True
        assert info["up_to_date"] is False, "a stale path must be reported as out of date"

    def test_status_does_not_raise_on_a_missing_key(self, sandbox_key: None) -> None:
        # No enable() call, so the sandbox key does not exist at all.
        assert autostart.status()["enabled"] is False


# ── CLI ───────────────────────────────────────────────────────────────────────

class TestCLI:

    def test_status_flag_returns_zero(
        self, sandbox_key: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert autostart.main(["--status"]) == 0
        assert "enabled" in capsys.readouterr().out

    def test_no_flag_defaults_to_status_without_changing_anything(
        self, sandbox_key: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert autostart.main([]) == 0
        capsys.readouterr()
        assert autostart.is_enabled() is False, "a bare invocation must not enable anything"

    def test_enable_and_disable_flags(
        self, sandbox_key: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert autostart.main(["--enable"]) == 0
        assert "Autostart enabled." in capsys.readouterr().out
        assert autostart.is_enabled() is True

        assert autostart.main(["--disable"]) == 0
        assert "Autostart disabled." in capsys.readouterr().out
        assert autostart.is_enabled() is False

    def test_enable_and_disable_are_mutually_exclusive(self, sandbox_key: None) -> None:
        with pytest.raises(SystemExit):
            autostart.main(["--enable", "--disable"])


# ── Safety net ────────────────────────────────────────────────────────────────

class TestRealKeyUntouched:
    """Guards against a test (or a future edit) writing to the real Run key."""

    def test_module_defaults_point_at_the_per_user_run_key(self) -> None:
        # Read the defaults from a fresh import-time constant, not the patched one.
        assert "CurrentVersion\\Run" in autostart.RUN_KEY_PATH or (
            autostart.RUN_KEY_PATH == TEST_KEY_PATH
        )

    def test_real_registration_is_absent(self) -> None:
        """This suite must never leave FRIDAY registered on the developer's machine."""
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
            ) as key:
                with pytest.raises(FileNotFoundError):
                    winreg.QueryValueEx(key, "UltronAssistant")
        except FileNotFoundError:  # pragma: no cover - the Run key always exists
            pass

    def test_sandbox_key_is_not_the_real_key(self) -> None:
        assert TEST_KEY_PATH != r"Software\Microsoft\Windows\CurrentVersion\Run"


# ── Launcher shim ─────────────────────────────────────────────────────────────

class TestLauncherScript:

    def test_launcher_resolves_repo_root_correctly(self) -> None:
        source = autostart.launcher_script().read_text(encoding="utf-8")
        assert "os.chdir(REPO_ROOT)" in source, (
            "the launcher must fix the working directory; at login it is system32"
        )
        assert "sys.path.insert" in source

    def test_launcher_logs_failures(self) -> None:
        source = autostart.launcher_script().read_text(encoding="utf-8")
        # pythonw.exe has no console, so a traceback would otherwise be invisible.
        assert "autostart_launcher.log" in source
