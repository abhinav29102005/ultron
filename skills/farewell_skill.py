"""
skills/farewell_skill.py – Farewell / dismiss
==============================================
Handles "bye bye", "good night", "see you". Says goodbye and asks the UI to
shut down.

A goodbye means goodbye. This used to hide to the tray and leave the wake
word listening, which is a surprising thing to do to someone who has just
said good night: the assistant they dismissed was still running and still
holding the microphone. The UI waits for the farewell to finish speaking
before it exits, so the goodbye is never cut off mid-word.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task


class FarewellSkill(Skill):
    name = "FarewellSkill"
    description = "Says goodbye and shuts the assistant down."
    version = "1.0.0"
    enabled = True

    #: Wording matters here: these used to promise FRIDAY was still
    #: listening ("say my name whenever you need me"), which is now untrue.
    GOODBYES = (
        "Goodbye! Shutting down now.",
        "Good night! I'm signing off.",
        "See you later. Closing down.",
    )

    async def execute(self, task: "Task") -> str:
        message = random.choice(self.GOODBYES)

        # The event is best-effort. A missing container or event bus means we
        # are running headless (tests, CLI), where there is no window to close;
        # the spoken goodbye is still correct in that case.
        container = getattr(self, "container", None)
        bus = getattr(container, "event_bus", None) if container else None

        if bus is not None:
            try:
                from core.event_bus import ExitRequestedEvent

                await bus.publish(ExitRequestedEvent(reason="farewell"))
            except Exception:
                # Never let a UI concern break the spoken reply.
                pass

        return message
