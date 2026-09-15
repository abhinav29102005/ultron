"""
skills/reminder_skill.py – Remind me to, in, and at
====================================================
The third of the ``DefaultSkill`` stubs, and the one with real teeth: a
reminder is a promise, and a promise a restart quietly cancels is worse than
saying no in the first place.

So two things are non-negotiable here:

  * **it persists.** Reminders live on disk from the moment they are set, and
    firing is recorded on disk too -- otherwise a restart resurrects one that
    has already gone off, and the user is told to check the oven at midnight;
  * **it refuses to guess.** A reminder with no parseable time asks the user
    when. Inventing an hour produces a reminder that fires at the wrong moment,
    which teaches the user to stop trusting them.

The clock is injected (``now``) rather than read directly so behaviour around
"already past" is testable at any hour.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from config.logging_config import get_logger
from skills.base import Skill
from utils.record_store import RecordStore
from utils.when import parse_when, strip_when

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.reminder")

DEFAULT_STORE = Path("data/reminders.json")


@dataclass(frozen=True)
class Reminder:
    id: str
    text: str
    due_at: datetime
    fired: bool = False


class ReminderStore:
    """The reminders on disk, and which of them are due."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._store = RecordStore(path or DEFAULT_STORE)

    def add(self, text: str, due_at: datetime) -> Reminder:
        reminder = Reminder(id=uuid.uuid4().hex[:8], text=text, due_at=due_at)
        self._store.append(
            {
                "id": reminder.id,
                "text": reminder.text,
                "due_at": due_at.isoformat(),
                "fired": False,
            }
        )
        return reminder

    def pending(self) -> list[Reminder]:
        """Everything still waiting to fire, soonest first."""
        return sorted(
            (r for r in self._all() if not r.fired), key=lambda r: r.due_at
        )

    def due(self, now: datetime | None = None) -> list[Reminder]:
        """Reminders whose time has come and which have not fired yet."""
        now = now or datetime.now()
        return [r for r in self.pending() if r.due_at <= now]

    def mark_fired(self, reminder_id: str) -> bool:
        """Record that this one has gone off.

        On disk, not in memory: the scheduler ticks repeatedly and a restart
        must not bring a fired reminder back.
        """
        return self._store.update(reminder_id, fired=True)

    def cancel(self, query: str) -> Reminder | None:
        """Remove the soonest pending reminder matching ``query``."""
        needle = (query or "").strip().lower()
        if not needle:
            return None

        for reminder in self.pending():
            if needle in reminder.text.lower():
                self._store.remove(reminder.id)
                return reminder
        return None

    def _all(self) -> list[Reminder]:
        reminders = []
        for record in self._store.all():
            try:
                reminders.append(
                    Reminder(
                        id=str(record["id"]),
                        text=str(record.get("text", "")),
                        due_at=datetime.fromisoformat(str(record["due_at"])),
                        fired=bool(record.get("fired")),
                    )
                )
            except (KeyError, ValueError) as exc:
                # One malformed row must not hide every other reminder.
                logger.warning(f"Skipping unreadable reminder {record!r}: {exc}")
        return reminders


class ReminderSkill(Skill):
    """Set, list and cancel reminders."""

    name = "ReminderSkill"
    description = "Sets reminders and reads back the pending ones."
    version = "1.0.0"
    enabled = True

    def __init__(
        self,
        container: Any = None,
        store_path: Path | str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(container)
        self.store = ReminderStore(store_path or DEFAULT_STORE)
        self._now = now or datetime.now

    async def execute(self, task: Task) -> str:
        action = str(task.parameters.get("action") or "add").lower()

        if action in ("add", "set", "create", "new"):
            return self._add(task)
        if action in ("list", "show", "read", "all", "pending"):
            return self._list()
        if action in ("cancel", "delete", "remove", "clear"):
            return self._cancel(task)

        return f"I can set, list or cancel reminders, not '{action}'."

    # ── actions ───────────────────────────────────────────────────────────

    def _add(self, task: Task) -> str:
        spoken = str(
            task.parameters.get("text")
            or task.parameters.get("reminder")
            or (task.metadata or {}).get("raw_utterance")
            or ""
        ).strip()

        if not spoken:
            return "What should I remind you about?"

        now = self._now()

        # The time can be given separately ("when": "in 10 minutes") or left
        # inside the sentence, which is the usual case for speech.
        when_text = str(task.parameters.get("when") or "").strip()
        due_at = parse_when(when_text, now=now) if when_text else None
        if due_at is None:
            due_at = parse_when(spoken, now=now)

        if due_at is None:
            return (
                "When would you like that reminder? Say something like "
                "'in ten minutes' or 'at 5pm'."
            )

        subject = strip_when(spoken) or "your reminder"
        self.store.add(subject, due_at)

        logger.info(f"Reminder set for {due_at.isoformat(timespec='minutes')}")
        return f"I'll remind you to {subject} {self._describe(due_at, now)}."

    def _list(self) -> str:
        pending = self.store.pending()
        if not pending:
            return "You have no reminders."

        now = self._now()
        lines = "\n".join(
            f"  {r.text} — {self._describe(r.due_at, now)}" for r in pending[:20]
        )
        return f"You have {len(pending)} reminder{'s' if len(pending) != 1 else ''}:\n{lines}"

    def _cancel(self, task: Task) -> str:
        query = str(
            task.parameters.get("query") or task.parameters.get("text") or ""
        ).strip()

        if not query:
            return "Which reminder should I cancel?"

        cancelled = self.store.cancel(query)
        if cancelled is None:
            return f"I couldn't find a reminder matching '{query}'."

        return f"Cancelled the reminder to {cancelled.text}."

    # ── speaking a time ───────────────────────────────────────────────────

    @staticmethod
    def _describe(due_at: datetime, now: datetime) -> str:
        """A spoken description of when something happens.

        "in about ten minutes" rather than a timestamp: an assistant that
        reads "2026-03-09T14:40:00" aloud is unusable, and for anything within
        the hour the offset is what the user is actually thinking in.
        """
        seconds = (due_at - now).total_seconds()

        if seconds < 60:
            return "in under a minute"
        if seconds < 3600:
            return f"in {round(seconds / 60)} minutes"
        if due_at.date() == now.date():
            return f"at {due_at.strftime('%-I:%M %p') if _supports_dash() else due_at.strftime('%I:%M %p').lstrip('0')}"

        day = "tomorrow" if (due_at.date() - now.date()).days == 1 else due_at.strftime("%A")
        clock = due_at.strftime("%I:%M %p").lstrip("0")
        return f"{day} at {clock}"


def _supports_dash() -> bool:
    """True on platforms where strftime understands ``%-I``.

    Windows does not, and raises rather than ignoring it, so the padded form
    is stripped by hand there instead.
    """
    try:
        datetime.now().strftime("%-I")
        return True
    except ValueError:
        return False
