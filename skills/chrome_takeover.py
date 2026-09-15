"""
skills/chrome_takeover.py – Getting control of the user's own Chrome
=====================================================================
The missing piece behind "it can't take control of my already-open browser".

Playwright can drive a Chrome it did not start, but only over the DevTools
protocol, and Chrome only speaks that protocol when it is *launched* with
``--remote-debugging-port``. There is no way to switch it on afterwards --
diagnosed live on this machine: Chrome running, nothing listening on 9222.

So every attach attempt failed and ULTRON quietly fell back to its own
Chromium, which is logged into nothing. From the user's side that reads as
"it opened some other browser and couldn't do anything".

The only real fix is to restart Chrome with the flag. That closes their
windows for a few seconds, which is not something to do silently, so:

  * **already listening** -> use it, ask nothing;
  * **not running at all** -> just start it with the flag, nothing to lose;
  * **running without the flag** -> ask first, then restart with
    ``--restore-last-session`` so their tabs come back.

Their profile is untouched, so cookies and logins survive. No flag here
weakens the browser's security -- a takeover is not a licence to disable the
sandbox in the browser somebody does their banking in.

This module owns the decision and none of the mechanism: probing, killing and
launching are injected, which is what makes the whole flow testable without
closing anybody's browser.
"""

from __future__ import annotations

import asyncio
import enum
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Awaitable, Callable

from config.logging_config import get_logger

logger = get_logger("skills.chrome")

#: Flags Chrome is relaunched with.
#:
#: Only two, deliberately. The debug port is what makes control possible;
#: restore-last-session is what makes closing their browser acceptable.
CDP_ARGS = (
    "--remote-debugging-port=9222",
    "--restore-last-session",
)

#: Where Chrome usually lives on Windows.
_CHROME_PATHS = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
)

#: Seconds to wait between asking Chrome to close and starting it again.
DEFAULT_SETTLE = 1.5

#: Polls for the debug port after a relaunch, at one second apart.
DEFAULT_ATTEMPTS = 12


class TakeoverOutcome(enum.Enum):
    ALREADY_ENABLED = "already_enabled"
    LAUNCHED = "launched"
    RELAUNCHED = "relaunched"
    NEEDS_APPROVAL = "needs_approval"
    FAILED = "failed"


@dataclass(frozen=True)
class TakeoverResult:
    outcome: TakeoverOutcome
    message: str

    @property
    def needs_approval(self) -> bool:
        return self.outcome is TakeoverOutcome.NEEDS_APPROVAL

    @property
    def ok(self) -> bool:
        return self.outcome in (
            TakeoverOutcome.ALREADY_ENABLED,
            TakeoverOutcome.LAUNCHED,
            TakeoverOutcome.RELAUNCHED,
        )


# ── the injected mechanism ────────────────────────────────────────────────


async def probe_cdp(port: int) -> bool:
    """True when something is answering the DevTools protocol on ``port``."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://localhost:{port}/json/version")
            return response.status_code == 200
    except Exception:
        return False


def chrome_is_running() -> bool:
    try:
        output = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            # Console-window hygiene; see tests/test_no_console_windows.py.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        return False

    return "chrome.exe" in output.lower()


def kill_chrome() -> None:
    subprocess.run(
        ["taskkill", "/IM", "chrome.exe", "/F"],
        capture_output=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def find_chrome() -> str | None:
    for template in _CHROME_PATHS:
        candidate = os.path.expandvars(template)
        if "%" not in candidate and os.path.isfile(candidate):
            return candidate
    return shutil.which("chrome") or shutil.which("chrome.exe")


def launch_chrome(path: str, args: tuple[str, ...]) -> None:
    subprocess.Popen(
        [path, *args],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


# ── the decision ──────────────────────────────────────────────────────────


class ChromeTakeover:
    """Decide what has to happen for Chrome to be controllable, and do it."""

    def __init__(
        self,
        probe: Callable[[int], Awaitable[bool]] = probe_cdp,
        is_running: Callable[[], bool] = chrome_is_running,
        kill: Callable[[], None] = kill_chrome,
        launch: Callable[[str, tuple[str, ...]], None] = launch_chrome,
        find_chrome: Callable[[], str | None] = find_chrome,
        port: int = 9222,
        settle_seconds: float = DEFAULT_SETTLE,
    ) -> None:
        self._probe = probe
        self._is_running = is_running
        self._kill = kill
        self._launch = launch
        self._find = find_chrome
        self._port = port
        self._settle = settle_seconds

    async def ensure_debuggable(
        self, *, approved: bool, attempts: int = DEFAULT_ATTEMPTS
    ) -> TakeoverResult:
        """Make Chrome controllable, asking first when that costs the user.

        ``approved`` is the answer to the question this method asked on a
        previous call. It is threaded through rather than the method prompting
        directly, because the only channel to the user is the agent loop's
        confirmation flow, and a session object doing side effects behind the
        tools' back is exactly what makes such flows impossible to reason
        about.
        """
        if await self._probe(self._port):
            return TakeoverResult(
                TakeoverOutcome.ALREADY_ENABLED,
                "Your Chrome is already set up for me to control.",
            )

        path = self._find()
        if path is None:
            return TakeoverResult(
                TakeoverOutcome.FAILED,
                "I couldn't find Chrome installed on this machine.",
            )

        running = self._is_running()

        if running and not approved:
            return TakeoverResult(
                TakeoverOutcome.NEEDS_APPROVAL,
                "To control your Chrome I need to restart it with remote "
                "control switched on. Your tabs will come back. Shall I?",
            )

        if running:
            logger.info("Restarting Chrome with remote debugging enabled.")
            self._kill()
            await asyncio.sleep(self._settle)

        try:
            self._launch(path, CDP_ARGS)
        except Exception as exc:
            return TakeoverResult(
                TakeoverOutcome.FAILED, f"I couldn't start Chrome: {exc}"
            )

        for _ in range(attempts):
            if await self._probe(self._port):
                return TakeoverResult(
                    TakeoverOutcome.RELAUNCHED if running else TakeoverOutcome.LAUNCHED,
                    "Chrome is ready and I can control it now.",
                )
            await asyncio.sleep(1.0)

        return TakeoverResult(
            TakeoverOutcome.FAILED,
            "Chrome restarted but never opened its remote control port.",
        )
