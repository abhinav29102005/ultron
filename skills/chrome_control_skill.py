"""
skills/chrome_control_skill.py – The tool that enables Chrome takeover
======================================================================
A thin skill around :mod:`skills.chrome_takeover`.

It exists so the restart goes through the ordinary tool path, where the agent
loop's ``confirm`` gate can ask the user before their browser closes. The
alternative -- having the browser session restart Chrome by itself when an
attach fails -- would mean a side effect the tools never requested and the
user never approved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.logging_config import get_logger
from skills.base import Skill
from skills.chrome_takeover import ChromeTakeover

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.chrome_control")


class ChromeControlSkill(Skill):
    """Make the user's own Chrome controllable, restarting it if needed."""

    name = "ChromeControlSkill"
    description = "Enables remote control of the user's own Chrome browser."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        settings = getattr(self.container, "settings", None)
        port = int(getattr(settings, "browser_cdp_port", 9222))

        # The agent loop has already asked the user -- this tool is marked
        # confirm, so reaching here at all means they said yes.
        result = await ChromeTakeover(port=port).ensure_debuggable(approved=True)

        if result.ok:
            # The next browser tool must attach rather than reuse the Chromium
            # the session may already have launched.
            from skills.browser_skill import close_session

            await close_session()

        logger.info(f"Chrome takeover: {result.outcome.value}")
        return result.message
