"""
Tests for skills/notes_skill.py and skills/reminder_skill.py.

These were two of the three intents wired to ``DefaultSkill``: the router
recognised "make a note of that" and "remind me in ten minutes", and then
nothing happened. (``clipboard``, the third, is already done.)

Both persist to disk, because both are worthless if they do not survive a
restart -- a reminder that a reboot silently cancels is a reminder the user
learns not to trust.

Everything here writes to tmp_path.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from intelligence.task import Task, TaskStatus

NOW = datetime(2026, 3, 9, 14, 30, 0)


def _task(intent: str, **params) -> Task:
    return Task(
        task_id="t1",
        skill_name="",
        intent=intent,
        parameters=params,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


# ── notes ─────────────────────────────────────────────────────────────────


@pytest.fixture
def notes(tmp_path):
    from skills.notes_skill import NotesSkill

    return NotesSkill(store_path=tmp_path / "notes.json")


class TestNotes:
    @pytest.mark.asyncio
    async def test_a_note_is_saved_and_confirmed(self, notes):
        out = await notes.execute(_task("notes", action="add", text="buy milk"))
        assert "buy milk" in out or "noted" in out.lower()

    @pytest.mark.asyncio
    async def test_saved_notes_come_back_in_a_listing(self, notes):
        await notes.execute(_task("notes", action="add", text="buy milk"))
        await notes.execute(_task("notes", action="add", text="call the dentist"))

        out = await notes.execute(_task("notes", action="list"))

        assert "buy milk" in out
        assert "call the dentist" in out

    @pytest.mark.asyncio
    async def test_notes_survive_a_restart(self, tmp_path):
        """A note held only in memory is not a note."""
        from skills.notes_skill import NotesSkill

        path = tmp_path / "notes.json"
        await NotesSkill(store_path=path).execute(
            _task("notes", action="add", text="remember the milk")
        )

        out = await NotesSkill(store_path=path).execute(_task("notes", action="list"))

        assert "remember the milk" in out

    @pytest.mark.asyncio
    async def test_search_finds_a_note_by_substring(self, notes):
        await notes.execute(_task("notes", action="add", text="buy oat milk"))
        await notes.execute(_task("notes", action="add", text="book a haircut"))

        out = await notes.execute(_task("notes", action="search", query="milk"))

        assert "oat milk" in out
        assert "haircut" not in out

    @pytest.mark.asyncio
    async def test_an_empty_list_says_so(self, notes):
        out = await notes.execute(_task("notes", action="list"))
        assert "no notes" in out.lower()

    @pytest.mark.asyncio
    async def test_adding_nothing_is_refused(self, notes):
        out = await notes.execute(_task("notes", action="add"))
        assert "what" in out.lower() or "need" in out.lower()

    @pytest.mark.asyncio
    async def test_the_raw_utterance_is_used_when_no_text_is_given(self, notes):
        """The classifier often extracts no entity; the words are still there."""
        task = _task("notes", action="add")
        task.metadata["raw_utterance"] = "make a note that the wifi password is swordfish"

        await notes.execute(task)
        out = await notes.execute(_task("notes", action="list"))

        assert "swordfish" in out


# ── reminders ─────────────────────────────────────────────────────────────


@pytest.fixture
def reminders(tmp_path):
    from skills.reminder_skill import ReminderSkill

    return ReminderSkill(store_path=tmp_path / "reminders.json", now=lambda: NOW)


class TestReminders:
    @pytest.mark.asyncio
    async def test_a_reminder_is_scheduled_from_spoken_time(self, reminders):
        out = await reminders.execute(
            _task("reminder", action="add", text="check the oven in 10 minutes")
        )
        assert "10" in out or "minute" in out.lower()

    @pytest.mark.asyncio
    async def test_the_subject_drops_the_time_words(self, reminders):
        await reminders.execute(
            _task("reminder", action="add", text="remind me in 5 minutes to check the oven")
        )

        out = await reminders.execute(_task("reminder", action="list"))

        assert "check the oven" in out
        assert "remind me" not in out.lower()

    @pytest.mark.asyncio
    async def test_a_reminder_with_no_time_asks_rather_than_guessing(self, reminders):
        """Inventing a time produces a reminder that fires at the wrong moment,
        which is worse than none at all."""
        out = await reminders.execute(
            _task("reminder", action="add", text="remind me to call mum")
        )

        assert "when" in out.lower()

    @pytest.mark.asyncio
    async def test_reminders_survive_a_restart(self, tmp_path):
        from skills.reminder_skill import ReminderSkill

        path = tmp_path / "reminders.json"
        await ReminderSkill(store_path=path, now=lambda: NOW).execute(
            _task("reminder", action="add", text="stand up in 1 hour")
        )

        out = await ReminderSkill(store_path=path, now=lambda: NOW).execute(
            _task("reminder", action="list")
        )

        assert "stand up" in out

    @pytest.mark.asyncio
    async def test_an_empty_list_says_so(self, reminders):
        out = await reminders.execute(_task("reminder", action="list"))
        assert "no reminders" in out.lower()

    @pytest.mark.asyncio
    async def test_a_reminder_can_be_cancelled(self, reminders):
        await reminders.execute(
            _task("reminder", action="add", text="call mum in 2 hours")
        )
        await reminders.execute(_task("reminder", action="cancel", query="call mum"))

        out = await reminders.execute(_task("reminder", action="list"))

        assert "no reminders" in out.lower()


class TestDueReminders:
    """What the scheduler uses to decide when to speak."""

    def test_a_future_reminder_is_not_due(self, tmp_path):
        from skills.reminder_skill import ReminderStore

        store = ReminderStore(tmp_path / "r.json")
        store.add("check the oven", NOW + timedelta(minutes=10))

        assert store.due(NOW) == []

    def test_a_passed_reminder_is_due(self, tmp_path):
        from skills.reminder_skill import ReminderStore

        store = ReminderStore(tmp_path / "r.json")
        store.add("check the oven", NOW - timedelta(seconds=1))

        due = store.due(NOW)

        assert len(due) == 1
        assert due[0].text == "check the oven"

    def test_a_fired_reminder_is_not_due_again(self, tmp_path):
        """Otherwise the scheduler repeats it on every tick, forever."""
        from skills.reminder_skill import ReminderStore

        store = ReminderStore(tmp_path / "r.json")
        store.add("check the oven", NOW - timedelta(seconds=1))

        first = store.due(NOW)
        store.mark_fired(first[0].id)

        assert store.due(NOW) == []

    def test_firing_is_recorded_on_disk(self, tmp_path):
        """A restart must not resurrect a reminder that already went off."""
        from skills.reminder_skill import ReminderStore

        path = tmp_path / "r.json"
        store = ReminderStore(path)
        store.add("check the oven", NOW - timedelta(seconds=1))
        store.mark_fired(store.due(NOW)[0].id)

        assert ReminderStore(path).due(NOW) == []


class TestNoteTextIsCleaned:
    """The scaffolding words are stripped whoever supplied them.

    Seen live: asked to note "make a note that the wifi password is
    swordfish", the model passed the *whole sentence* as the text, so the
    saved note read "make a note that the wifi password is swordfish". Reading
    that back is absurd. The prefix was already trimmed when falling back to
    the raw utterance; it has to be trimmed from what the model sends too.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "supplied,expected",
        [
            ("make a note that the wifi password is swordfish",
             "the wifi password is swordfish"),
            ("note that the bins go out on Tuesday", "the bins go out on Tuesday"),
            ("jot down buy milk", "buy milk"),
            ("take a note of the door code", "the door code"),
            # Already clean: left exactly as it is.
            ("the wifi password is swordfish", "the wifi password is swordfish"),
            ("meeting moved to 3pm", "meeting moved to 3pm"),
        ],
    )
    async def test_the_instruction_prefix_is_removed(self, notes, supplied, expected):
        await notes.execute(_task("notes", action="add", text=supplied))

        out = await notes.execute(_task("notes", action="list"))

        assert expected in out
        assert "make a note" not in out.lower()

    @pytest.mark.asyncio
    async def test_a_note_that_is_only_scaffolding_is_refused(self, notes):
        """"make a note" with nothing after it is not a note."""
        out = await notes.execute(_task("notes", action="add", text="make a note"))
        assert "what" in out.lower()
