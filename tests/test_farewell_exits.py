"""Saying goodbye shuts FRIDAY down.

It used to hide to the system tray and leave the wake word listening, so an
assistant the user had just said good night to was still running and still
holding the microphone -- and "bye bye" was indistinguishable from
minimising.

The exit is deliberately deferred until the spoken farewell has finished, so
the goodbye is not cut off mid-word.
"""

from __future__ import annotations

import asyncio

import pytest

from core.event_bus import EventBus, ExitRequestedEvent
from skills.farewell_skill import FarewellSkill


class _Bus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event) -> None:
        self.published.append(event)


class _Container:
    def __init__(self, bus) -> None:
        self.event_bus = bus


def _task():
    from intelligence.task import Task, TaskStatus
    from datetime import datetime

    return Task(
        task_id="t1",
        skill_name="FarewellSkill",
        intent="farewell",
        parameters={},
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


class TestFarewellAsksToExit:
    def test_an_exit_is_requested(self):
        skill = FarewellSkill()
        bus = _Bus()
        skill.container = _Container(bus)

        asyncio.run(skill.execute(_task()))

        assert len(bus.published) == 1
        assert isinstance(bus.published[0], ExitRequestedEvent)
        assert bus.published[0].reason == "farewell"

    def test_the_spoken_goodbye_does_not_promise_to_keep_listening(self):
        # The old wording ("say my name whenever you need me") described
        # behaviour that no longer exists.
        for goodbye in FarewellSkill.GOODBYES:
            lowered = goodbye.lower()
            assert "say my name" not in lowered, goodbye
            assert "call" not in lowered or "closing" in lowered, goodbye

    def test_a_goodbye_is_still_spoken(self):
        skill = FarewellSkill()
        skill.container = _Container(_Bus())

        reply = asyncio.run(skill.execute(_task()))

        assert reply in FarewellSkill.GOODBYES

    def test_headless_still_answers_without_a_bus(self):
        """No window to close (CLI, tests) must not break the spoken reply."""
        skill = FarewellSkill()

        reply = asyncio.run(skill.execute(_task()))

        assert reply in FarewellSkill.GOODBYES


class TestTheWindowQuitsRatherThanHides:
    def test_exit_if_pending_calls_quit(self):
        import types

        from ui.main_window import MainWindow

        window = types.SimpleNamespace(_pending_exit=True, quit_calls=0)
        window._quit = lambda: setattr(window, "quit_calls", window.quit_calls + 1)

        MainWindow._exit_if_pending(window)

        assert window.quit_calls == 1
        assert window._pending_exit is False

    def test_nothing_happens_without_a_pending_exit(self):
        import types

        from ui.main_window import MainWindow

        window = types.SimpleNamespace(_pending_exit=False, quit_calls=0)
        window._quit = lambda: setattr(window, "quit_calls", window.quit_calls + 1)

        MainWindow._exit_if_pending(window)

        assert window.quit_calls == 0

    def test_the_window_no_longer_merely_hides_on_farewell(self):
        import inspect

        from ui.main_window import MainWindow

        source = inspect.getsource(MainWindow._exit_if_pending)

        assert "_quit()" in source
        assert "self.hide()" not in source, "farewell is hiding again, not exiting"
