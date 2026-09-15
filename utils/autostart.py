"""
utils/autostart.py – Windows Login Autostart Registration
==========================================================
Registers (or unregisters) FRIDAY so it launches automatically when the user
logs into Windows, without a visible console window and without admin rights.

Mechanism
---------
A single string value under the *per-user* Run key::

    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
        UltronAssistant = "<repo>\\.venv\\Scripts\\pythonw.exe" "<repo>\\scripts\\ultron_launcher.pyw"

Why the registry and not a Startup-folder shortcut:

* A Startup-folder entry has to be a ``.lnk``, and creating one requires COM
  (``pywin32`` / ``winshell``), which this project does not depend on. The
  alternatives -- a ``.bat`` or ``.vbs`` shim -- either flash a console window
  or add a scripting-host indirection that is harder to inspect and repair.
* ``winreg`` is in the standard library, so registration adds no dependency.
* Writing a value is inherently idempotent: the same value name is overwritten
  rather than duplicated, so ``enable()`` can never produce two entries.
* ``HKCU`` needs no elevation and runs in the interactive desktop session, so
  the app keeps access to the microphone, speakers and the display. (``HKLM``
  Run and Task Scheduler ``SYSTEM`` tasks are deliberately *not* used: they
  need admin rights and/or run in a session with no audio devices.)

Why ``pythonw.exe``
-------------------
FRIDAY is a PyQt GUI app. ``python.exe`` is a console subsystem binary, so
Windows allocates a black console window for it on every boot. ``pythonw.exe``
is the same interpreter built for the GUI subsystem -- no console is created.
The trade-off is that anything written to stdout/stderr is discarded, so the
launcher script logs startup failures to a file (see ``scripts/ultron_launcher.pyw``).

Why the launcher script
-----------------------
At login the working directory is *not* the repository (it is typically
``C:\\Windows\\system32``). Any relative path in the codebase -- the project has
already had a bug of exactly this class with a relative memory path -- would
resolve against the wrong directory. ``ultron_launcher.pyw`` chdir's to the
repository root and fixes ``sys.path`` before importing the app, so boot-time
startup behaves identically to launching from a shell inside the repo.

CLI
---
Usable without the GUI, for setup and recovery::

    .venv\\Scripts\\python.exe -m utils.autostart --status
    .venv\\Scripts\\python.exe -m utils.autostart --enable
    .venv\\Scripts\\python.exe -m utils.autostart --disable
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "is_enabled",
    "enable",
    "disable",
    "status",
    "build_command",
    "AutostartError",
    "AutostartUnsupportedError",
]


# ── Configuration ─────────────────────────────────────────────────────────────
# These are module-level so tests can monkeypatch RUN_KEY_PATH / VALUE_NAME onto
# a throwaway key and never touch the user's real Run key.

#: Registry sub-key holding per-user login entries.
RUN_KEY_PATH: str = r"Software\Microsoft\Windows\CurrentVersion\Run"

#: Name of the value this module owns. Anything else under the key is left alone.
VALUE_NAME: str = "UltronAssistant"

#: Human-readable identifier for the mechanism, surfaced by ``status()``.
METHOD: str = "HKCU Run registry key"


class AutostartError(RuntimeError):
    """Raised when autostart registration cannot be read or written."""


class AutostartUnsupportedError(AutostartError):
    """Raised when autostart is requested on a non-Windows platform."""


# ── Path resolution ───────────────────────────────────────────────────────────

def repo_root() -> Path:
    """Absolute path to the repository root (the parent of ``utils/``)."""
    return Path(__file__).resolve().parent.parent


def launcher_script() -> Path:
    """Absolute path to the GUI launcher shim started at login."""
    return repo_root() / "scripts" / "ultron_launcher.pyw"


def pythonw_executable() -> Path:
    """
    Absolute path to a *windowed* (console-less) interpreter.

    Preference order:

    1. ``<repo>/.venv/Scripts/pythonw.exe`` -- the project's own venv, which is
       what the app's dependencies are installed into.
    2. The ``pythonw.exe`` sitting next to the currently running interpreter,
       for people who use a differently-named or externally-managed venv.
    3. ``sys.executable`` as a last resort. This still works, it just shows a
       console window, which is better than not starting at all.
    """
    candidates = [
        repo_root() / ".venv" / "Scripts" / "pythonw.exe",
        Path(sys.executable).resolve().parent / "pythonw.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(sys.executable).resolve()


def build_command() -> str:
    """
    The exact command string written to the registry.

    Both halves are absolute and individually quoted, because the working
    directory at login is not the repository and either path may contain
    spaces (e.g. ``C:\\Users\\First Last\\...``).
    """
    return f'"{pythonw_executable()}" "{launcher_script()}"'


# ── Registry plumbing ─────────────────────────────────────────────────────────

def _winreg() -> Any:
    """Import ``winreg`` lazily so this module is importable on any platform."""
    if os.name != "nt":
        raise AutostartUnsupportedError(
            "Autostart registration is only implemented for Windows "
            f"(running on os.name={os.name!r})."
        )
    import winreg  # noqa: PLC0415 - deliberately deferred, Windows-only stdlib

    return winreg


def _read_value() -> str | None:
    """Current command registered under ``VALUE_NAME``, or ``None`` if absent."""
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        # Either the key or the value is missing -> simply not registered.
        return None
    except OSError as exc:  # pragma: no cover - permission / corrupt hive
        raise AutostartError(f"Could not read {RUN_KEY_PATH}: {exc}") from exc
    return str(value)


# ── Public API ────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """``True`` if FRIDAY is registered to start at login."""
    return _read_value() is not None


def enable() -> None:
    """
    Register FRIDAY to start at login.

    Idempotent: the registry value is keyed by name, so calling this twice
    overwrites the single existing entry instead of adding a second one. It is
    also self-repairing -- if the repo was moved or the venv rebuilt, calling
    ``enable()`` again rewrites the value with the current absolute paths.
    """
    winreg = _winreg()
    command = build_command()
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    except OSError as exc:
        raise AutostartError(
            f"Could not write {VALUE_NAME} to {RUN_KEY_PATH}: {exc}"
        ) from exc


def disable() -> None:
    """
    Unregister FRIDAY from login startup.

    Idempotent: removing an entry that is already gone is a no-op, not an error.
    Only the value this module owns is deleted; the Run key itself and every
    other application's entry are left untouched.
    """
    winreg = _winreg()
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return  # already disabled (or the key does not exist) -- nothing to do
    except OSError as exc:
        raise AutostartError(
            f"Could not remove {VALUE_NAME} from {RUN_KEY_PATH}: {exc}"
        ) from exc


def status() -> dict[str, Any]:
    """
    Snapshot of the current registration, safe to call on any platform.

    Keys:
        ``enabled``        -- bool, whether the entry exists right now.
        ``method``         -- human-readable mechanism description.
        ``target``         -- the command currently registered, or ``None``.
        ``expected``       -- the command ``enable()`` would write.
        ``up_to_date``     -- bool, whether ``target`` matches ``expected``.
        ``registry_key``   -- full ``HKCU\\...`` path of the key.
        ``value_name``     -- the value name owned by this module.
        ``python``         -- absolute interpreter path that will be launched.
        ``script``         -- absolute launcher path that will be run.
        ``supported``      -- bool, whether this platform is supported.
        ``error``          -- str, present only if the registry read failed.
    """
    expected = None
    try:
        expected = build_command()
    except Exception:  # pragma: no cover - path resolution is effectively total
        pass

    info: dict[str, Any] = {
        "enabled": False,
        "method": METHOD,
        "target": None,
        "expected": expected,
        "up_to_date": False,
        "registry_key": rf"HKEY_CURRENT_USER\{RUN_KEY_PATH}",
        "value_name": VALUE_NAME,
        "python": str(pythonw_executable()),
        "script": str(launcher_script()),
        "supported": os.name == "nt",
    }

    if not info["supported"]:
        return info

    try:
        current = _read_value()
    except AutostartError as exc:
        info["error"] = str(exc)
        return info

    info["target"] = current
    info["enabled"] = current is not None
    info["up_to_date"] = current is not None and current == expected
    return info


# ── CLI ───────────────────────────────────────────────────────────────────────

def _format_status(info: dict[str, Any]) -> str:
    lines = [
        f"enabled      : {info['enabled']}",
        f"method       : {info['method']}",
        f"registry key : {info['registry_key']}",
        f"value name   : {info['value_name']}",
        f"target       : {info['target'] or '(not registered)'}",
        f"expected     : {info['expected']}",
        f"up to date   : {info['up_to_date']}",
        f"python       : {info['python']}",
        f"script       : {info['script']}",
    ]
    if not info["supported"]:
        lines.append("supported    : False (Windows only)")
    if "error" in info:
        lines.append(f"error        : {info['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m utils.autostart``. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m utils.autostart",
        description="Register or unregister FRIDAY to start when you log into Windows.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--enable", action="store_true", help="start FRIDAY automatically at login"
    )
    group.add_argument(
        "--disable", action="store_true", help="stop starting FRIDAY at login"
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="show the current registration (default when no flag is given)",
    )
    args = parser.parse_args(argv)

    try:
        if args.enable:
            enable()
            print("Autostart enabled.")
        elif args.disable:
            disable()
            print("Autostart disabled.")
        print(_format_status(status()))
    except AutostartError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
