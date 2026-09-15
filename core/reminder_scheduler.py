"""
core/reminder_scheduler.py – Saying the reminder when it comes due
==================================================================
Setting a reminder is the easy half. This is the half that makes it a promise:
a background loop that notices the time has come and speaks.

Three failure modes shape the whole design, and all three are the kind that
fail *silently* -- the user does not find out the scheduler is broken until a
reminder they were counting on never arrives:

  * **firing twice.** The loop ticks every few seconds, so a reminder that is
    not marked delivered is re-delivered on every tick, forever;
  * **dying quietly.** An exception escaping the loop body ends the task, and
    an asyncio task that ends is not restarted. Every future reminder is then
    cancelled with no error anywhere the user can see -- so the loop body
    catches everything;
  * **being marked done when it was not.** If the announcement itself failed,
    the reminder has not been delivered, and marking it fired would lose it.
    It stays due and is retried on the next tick.

Polling rather than sleeping until the next due time. A sleeping task has to
be woken and rescheduled every time a reminder is added or cancelled, and it
oversleeps across a laptop suspend -- exactly when a user is most likely to
have a reminder waiting. A cheap poll of a small JSON file avoids all of it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable

from config.logging_config import get_logger

logger = get_logger("reminders")

#: How often to look for due reminders.
#:
#: Twenty seconds: the worst-case lateness a user would notice is about that,
#: and the check is a small file read. Anything faster buys accuracy nobody
#: perceives in a spoken reminder.
DEFAULT_INTERVAL = 20.0

Speaker = Callable[[str], Awaitable[None]]


class ReminderScheduler:
    """Polls the reminder store and speaks whatever has come due."""

    def __init__(
        self,
        store: Any,
        speak: Speaker,
        *,
        interval: float = DEFAULT_INTERVAL,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._speak = speak
        self._interval = interval
        self._now = now or datetime.now
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Begin polling. Starting an already-running scheduler does nothing."""
        if self.running:
            return

        self._task = asyncio.create_task(self._loop())
        logger.info(f"Reminder scheduler started (every {self._interval:g}s).")

    async def stop(self) -> None:
        """Stop polling and wait for the loop to actually finish."""
        task, self._task = self._task, None

        if task is None or task.done():
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.tick()

    async def tick(self) -> None:
        """One pass: speak everything due, and record that it was delivered.

        Never raises. This runs inside a loop that must not end -- see the
        module docstring.
        """
        try:
            due = self._store.due(self._now())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Could not read reminders: {exc}")
            return

        for reminder in due:
            try:
                await self._speak(f"Reminder: {reminder.text}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Not delivered, so not marked delivered. The next tick tries
                # again rather than losing it.
                logger.warning(f"Could not announce a reminder: {exc}")
                continue

            try:
                self._store.mark_fired(reminder.id)
            except Exception as exc:
                # Spoken but not recorded: it will repeat on the next tick.
                # Annoying, and still better than a reminder that vanishes.
                logger.warning(f"Could not mark a reminder as fired: {exc}")
