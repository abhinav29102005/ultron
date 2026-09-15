"""
Tests for taking over the user's already-running Chrome – W8.

The user's complaint: "if my browser is already opened and some website is
opened then it can't take control". Diagnosed live and confirmed: their Chrome
was running with nothing listening on port 9222. Chrome only exposes the
DevTools protocol when it is *started* with ``--remote-debugging-port``, and
there is no way to switch it on afterwards. So attaching could never work, and
ULTRON silently fell back to its own Chromium -- logged into nothing, which is
exactly the "it isn't my browser" experience.

The only fix is to restart Chrome with the flag. That closes the user's
windows for a few seconds, so it is asked first and their tabs are restored.

Nothing here starts or kills a real browser.
"""

from __future__ import annotations

import pytest

from skills.chrome_takeover import (
    CDP_ARGS,
    ChromeTakeover,
    TakeoverOutcome,
)


class FakeProbe:
    """Stands in for "is something listening on the debug port?"."""

    def __init__(self, *answers):
        self._answers = list(answers)
        self.calls = 0

    async def __call__(self, port):
        self.calls += 1
        return self._answers.pop(0) if self._answers else self._answers_default

    _answers_default = False


@pytest.fixture
def takeover(monkeypatch):
    def build(*, listening, running=True, chrome_path="C:/chrome.exe", probe=None):
        killed, launched = [], []

        t = ChromeTakeover(
            probe=probe or FakeProbe(*listening),
            is_running=lambda: running,
            kill=lambda: killed.append(True),
            launch=lambda path, args: launched.append((path, args)),
            find_chrome=lambda: chrome_path,
            settle_seconds=0.0,
        )
        t.killed, t.launched = killed, launched
        return t

    return build


class TestAlreadyEnabled:
    @pytest.mark.asyncio
    async def test_a_chrome_already_listening_is_used_as_is(self, takeover):
        """The second time round, nothing should be restarted."""
        t = takeover(listening=[True])

        result = await t.ensure_debuggable(approved=False)

        assert result.outcome is TakeoverOutcome.ALREADY_ENABLED
        assert t.killed == [] and t.launched == []

    @pytest.mark.asyncio
    async def test_no_approval_is_asked_for_when_it_is_already_enabled(self, takeover):
        t = takeover(listening=[True])
        assert (await t.ensure_debuggable(approved=False)).needs_approval is False


class TestNotRunning:
    @pytest.mark.asyncio
    async def test_a_closed_chrome_is_simply_started_with_the_flag(self, takeover):
        """Nothing is being taken away, so there is nothing to ask about."""
        t = takeover(listening=[False, True], running=False)

        result = await t.ensure_debuggable(approved=False)

        assert result.outcome is TakeoverOutcome.LAUNCHED
        assert t.killed == []
        assert t.launched, "Chrome should have been started"
        assert any("--remote-debugging-port=9222" in a for a in t.launched[0][1])


class TestRunningWithoutTheFlag:
    @pytest.mark.asyncio
    async def test_permission_is_required_before_closing_their_windows(self, takeover):
        t = takeover(listening=[False], running=True)

        result = await t.ensure_debuggable(approved=False)

        assert result.needs_approval is True
        assert result.outcome is TakeoverOutcome.NEEDS_APPROVAL
        assert t.killed == [], "their browser must not be closed unasked"
        assert t.launched == []

    @pytest.mark.asyncio
    async def test_the_request_explains_what_will_happen(self, takeover):
        result = await takeover(listening=[False]).ensure_debuggable(approved=False)

        assert "restart" in result.message.lower()
        assert "tabs" in result.message.lower(), "say the tabs come back"

    @pytest.mark.asyncio
    async def test_with_permission_chrome_is_restarted(self, takeover):
        t = takeover(listening=[False, True], running=True)

        result = await t.ensure_debuggable(approved=True)

        assert result.outcome is TakeoverOutcome.RELAUNCHED
        assert t.killed == [True]
        assert t.launched

    @pytest.mark.asyncio
    async def test_the_relaunch_restores_their_tabs(self, takeover):
        """Closing someone's browser and losing their tabs is not acceptable."""
        t = takeover(listening=[False, True], running=True)

        await t.ensure_debuggable(approved=True)

        assert "--restore-last-session" in t.launched[0][1]

    @pytest.mark.asyncio
    async def test_the_relaunch_uses_their_own_chrome(self, takeover):
        t = takeover(listening=[False, True], chrome_path="C:/Program Files/chrome.exe")

        await t.ensure_debuggable(approved=True)

        assert t.launched[0][0] == "C:/Program Files/chrome.exe"


class TestFailures:
    @pytest.mark.asyncio
    async def test_chrome_not_installed_is_reported(self, takeover):
        t = takeover(listening=[False], chrome_path=None)

        result = await t.ensure_debuggable(approved=True)

        assert result.outcome is TakeoverOutcome.FAILED
        assert "chrome" in result.message.lower()

    @pytest.mark.asyncio
    async def test_a_relaunch_that_never_comes_up_is_reported(self, takeover):
        """Rather than hanging, or claiming success."""
        t = takeover(listening=[False, False, False, False], running=True)

        result = await t.ensure_debuggable(approved=True, attempts=3)

        assert result.outcome is TakeoverOutcome.FAILED
        assert t.killed == [True]


class TestCdpArgs:
    def test_the_debug_port_is_present(self):
        assert any("--remote-debugging-port" in a for a in CDP_ARGS)

    def test_no_flag_disables_their_security(self):
        """A takeover is not an excuse to weaken the browser the user does
        their banking in."""
        joined = " ".join(CDP_ARGS).lower()
        for dangerous in ("--disable-web-security", "--no-sandbox", "--allow-running-insecure"):
            assert dangerous not in joined
