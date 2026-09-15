"""
skills/notes_skill.py – Jot something down and find it again
=============================================================
``notes`` was one of three intents routed to ``DefaultSkill``: FRIDAY
recognised "make a note of that" and then did nothing with it.

Notes are stored on disk rather than in memory for the obvious reason -- a
note that a restart loses is not a note -- and separately from the fact store
in ``memory/``. The two look similar and are not: the fact store holds things
FRIDAY *inferred* about the user and prunes them on its own, while a note is
something the user asked to keep verbatim and expects to still be there.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.logging_config import get_logger
from skills.base import Skill
from utils.record_store import RecordStore

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.notes")

DEFAULT_STORE = Path("data/notes.json")

#: Notes read back in one listing. Spoken aloud, more than this is unusable.
MAX_LISTED = 20


class NotesSkill(Skill):
    """Add, list and search the user's notes."""

    name = "NotesSkill"
    description = "Saves short notes and reads them back."
    version = "1.0.0"
    enabled = True

    def __init__(self, container: Any = None, store_path: Path | str | None = None) -> None:
        super().__init__(container)
        self._store = RecordStore(store_path or DEFAULT_STORE)

    async def execute(self, task: Task) -> str:
        action = str(task.parameters.get("action") or "add").lower()

        if action in ("add", "create", "save", "new"):
            return self._add(task)
        if action in ("list", "read", "show", "all"):
            return self._list()
        if action in ("search", "find"):
            return self._search(task)
        if action in ("clear", "delete_all"):
            self._store.replace([])
            return "All notes cleared."

        return f"I can add, list or search notes, not '{action}'."

    # ── actions ───────────────────────────────────────────────────────────

    def _add(self, task: Task) -> str:
        text = self._text(task)

        if not text:
            return "What would you like me to note down?"

        self._store.append(
            {
                "id": uuid.uuid4().hex[:8],
                "text": text,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        logger.info("Note saved.")
        return f"Noted: {text}"

    def _list(self) -> str:
        records = self._store.all()
        if not records:
            return "You have no notes."

        # Newest first: a listing that is read aloud gets cut off at the end,
        # so the most recent note must not be the one that gets cut.
        recent = list(reversed(records))[:MAX_LISTED]
        lines = "\n".join(f"  {index}. {r['text']}" for index, r in enumerate(recent, 1))

        header = f"You have {len(records)} note{'s' if len(records) != 1 else ''}"
        if len(records) > len(recent):
            header += f"; here are the {len(recent)} most recent"

        return f"{header}:\n{lines}"

    def _search(self, task: Task) -> str:
        query = str(
            task.parameters.get("query") or task.parameters.get("text") or ""
        ).strip()

        if not query:
            return "What should I search your notes for?"

        matches = [
            r for r in self._store.all() if query.lower() in str(r.get("text", "")).lower()
        ]

        if not matches:
            return f"No notes mention '{query}'."

        lines = "\n".join(f"  {r['text']}" for r in matches[:MAX_LISTED])
        return f"{len(matches)} note{'s' if len(matches) != 1 else ''} matching '{query}':\n{lines}"

    # ── input ─────────────────────────────────────────────────────────────

    #: The words that mean "record this", which are not part of the note.
    _PREFIX_RE = re.compile(
        r"^\s*(?:hey\s+\w+[,\s]+)?(?:please\s+)?"
        r"(?:(?:make|take|add|write|jot|put)\s+(?:me\s+)?(?:a\s+|an\s+)?)?"
        r"note\s*(?:that|about|of|down|saying)?\s*"
        r"|^\s*(?:jot|write)\s+down\s*",
        re.IGNORECASE,
    )

    @classmethod
    def _text(cls, task: Task) -> str:
        """What to save, without the instruction to save it.

        Trimmed whoever supplied it. The classifier often extracts no entity
        at all, so the raw utterance is the fallback -- but the model is just
        as likely to hand over the whole sentence, and a note reading "make a
        note that the wifi password is swordfish" is absurd read back. Both
        paths get the same treatment rather than only the fallback.
        """
        text = str(
            task.parameters.get("text") or task.parameters.get("note") or ""
        ).strip()

        if not text:
            text = str((task.metadata or {}).get("raw_utterance") or "").strip()

        return cls._PREFIX_RE.sub("", text, count=1).strip(" .,!?")
