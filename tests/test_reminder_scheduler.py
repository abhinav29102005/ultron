"""
Tests for core/reminder_scheduler.py – actually speaking the reminder.

Setting a reminder is only half of it. Something has to notice the time has
come and say so, and that something has to survive the ways a long-running
background loop normally dies:

  * it must not fire the same reminder twice, however often it ticks;
  * one failure -- a TTS hiccup, a locked store -- must not kill the loop and
    silently cancel every future reminder;
  * shutting down must stop it, not leave a task speaking into a closed app.

Time is injected. A scheduler tested against the wall clock either sleeps for
real or is flaky.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from core.reminder_scheduler import ReminderScheduler
from skills.reminder_skill import ReminderStore

NOW = datetime(2026, 3, 9, 14, 30, 0)


@pytest.fixture
def store(tmp_path):
    return ReminderStore(tmp_path / "reminders.json")


class Speaker:
    def __init__(self, fails=False):
        self.said: list[str] = []
        self._fails = fails

    async def __call__(self, message: str) -> None:
        if self._fails:
            raise RuntimeError("TTS is not available")
        self.said.append(message)


class TestFiring:
    @pytest.mark.asyncio
    async def test_a_due_reminder_is_spoken(self, store):
        store.add("check the oven", NOW - timedelta(seconds=1))
        speaker = Speaker()

        await ReminderScheduler(store, speaker, now=lambda: NOW).tick()

        assert len(speaker.said) == 1
        assert "check the oven" in speaker.said[0]

    @pytest.mark.asyncio
    async def test_a_future_reminder_stays_quiet(self, store):
        store.add("check the oven", NOW + timedelta(minutes=10))
        speaker = Speaker()

        await ReminderScheduler(store, speaker, now=lambda: NOW).tick()

        assert speaker.said == []

    @pytest.mark.asyncio
    async def test_a_reminder_fires_only_once_however_many_ticks(self, store):
        """The loop ticks every few seconds; without this the user is told to
        check the oven forever."""
        store.add("check the oven", NOW - timedelta(seconds=1))
        speaker = Speaker()
        scheduler = ReminderScheduler(store, speaker, now=lambda: NOW)

        for _ in range(5):
            await scheduler.tick()

        assert len(speaker.said) == 1

    @pytest.mark.asyncio
    async def test_several_due_reminders_all_fire(self, store):
        store.add("first thing", NOW - timedelta(minutes=2))
        store.add("second thing", NOW - timedelta(minutes=1))
        speaker = Speaker()

        await ReminderScheduler(store, speaker, now=lambda: NOW).tick()

        assert len(speaker.said) == 2


class TestResilience:
    @pytest.mark.asyncio
    async def test_a_failed_announcement_does_not_lose_the_reminder(self, store):
        """If it could not be spoken, it has not been delivered -- so it must
        stay due rather than being quietly marked done."""
        store.add("check the oven", NOW - timedelta(seconds=1))

        await ReminderScheduler(store, Speaker(fails=True), now=lambda: NOW).tick()

        assert len(store.due(NOW)) == 1

    @pytest.mark.asyncio
    async def test_a_tick_that_raises_does_not_propagate(self, store):
        """The loop calls tick forever; an exception escaping would end it and
        silently cancel every reminder the user ever sets."""

        class Broken:
            def due(self, now=None):
                raise RuntimeError("the store is on fire")

        await ReminderScheduler(Broken(), Speaker(), now=lambda: NOW).tick()


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop_leave_nothing_running(self, store):
        scheduler = ReminderScheduler(store, Speaker(), interval=0.01, now=lambda: NOW)

        scheduler.start()
        assert scheduler.running is True

        await asyncio.sleep(0.05)
        await scheduler.stop()

        assert scheduler.running is False

    @pytest.mark.asyncio
    async def test_the_loop_keeps_ticking(self, store):
        store.add("check the oven", NOW - timedelta(seconds=1))
        speaker = Speaker()
        scheduler = ReminderScheduler(store, speaker, interval=0.01, now=lambda: NOW)

        scheduler.start()
        await asyncio.sleep(0.08)
        await scheduler.stop()

        assert speaker.said, "the background loop never fired the due reminder"

    @pytest.mark.asyncio
    async def test_starting_twice_does_not_double_the_loop(self, store):
        scheduler = ReminderScheduler(store, Speaker(), interval=0.01, now=lambda: NOW)

        scheduler.start()
        first = scheduler._task
        scheduler.start()

        assert scheduler._task is first
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stopping_when_never_started_is_harmless(self, store):
        await ReminderScheduler(store, Speaker()).stop()
