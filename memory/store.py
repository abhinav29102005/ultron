"""
memory/store.py – Persistent Fact Store
=========================================
Owns the on-disk JSON file holding what ULTRON knows about the user.
Deliberately free of any LLM dependency so it can be exercised with no
model server running.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from config.logging_config import get_logger
from memory.models import MemoryFact, from_dict, to_dict

logger = get_logger("memory.store")

#: Anything that is not a letter, a digit or an underscore becomes an
#: underscore, so "Favourite Editor" and "favourite-editor" land on one key.
_KEY_SEPARATORS = re.compile(r"[\s\-]+")
_KEY_ILLEGAL = re.compile(r"[^a-z0-9_]+")

#: Where a relative store path is anchored. The configured default is
#: "data/memory.json", which against the process working directory would point
#: at a different file every time ULTRON is launched from another folder — the
#: user would appear to have lost everything they told it.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MemoryStore:
    """
    Reads and writes the user's remembered facts as a JSON document.
    """

    def __init__(self, path: Path, max_facts: int = 200) -> None:
        """
        Initialise the store.

        Args:
            path: Location of the JSON document backing the store. A relative
                path is anchored at the project root, never at the working
                directory.
            max_facts: Upper bound on retained facts before eviction kicks in.
        """
        self._path = self.resolve_path(path)
        self._max_facts = max_facts
        self._facts: dict[str, MemoryFact] | None = None
        # Capture is scheduled as a background task and skills run on the same
        # loop, so two writes can be in flight against one store. The lock is
        # re-entrant because upsert() loads and saves under it.
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        """Get the path of the JSON document backing the store."""
        return self._path

    @staticmethod
    def resolve_path(path: Path | str) -> Path:
        """
        Pin a store path to one absolute location, whatever the working
        directory happens to be.

        Args:
            path: Configured location, absolute or relative.

        Returns:
            An absolute path: relative ones are anchored at the project root.
        """
        candidate = Path(path).expanduser()

        if not candidate.is_absolute():
            candidate = _PROJECT_ROOT / candidate

        return candidate

    def all(self) -> list[MemoryFact]:
        """
        List every remembered fact, most recently updated first.

        Returns:
            The stored facts ordered newest-updated first.
        """
        with self._lock:
            facts = self._load()
            return sorted(facts.values(), key=lambda fact: fact.updated_at, reverse=True)

    def upsert(self, key: str, value: str, source_utterance: str) -> MemoryFact:
        """
        Insert a fact, or overwrite the existing one under the same key.

        Overwriting in place is what lets a correction supersede an outdated
        fact instead of leaving both versions in the store to contradict
        each other.

        Args:
            key: Fact identifier; normalised before use.
            value: The remembered value.
            source_utterance: The sentence the fact was taken from.

        Returns:
            The stored :class:`MemoryFact`.
        """
        with self._lock:
            facts = self._load()
            normalised = self.normalise_key(key)
            now = datetime.utcnow()

            existing = facts.get(normalised)

            if existing is not None:
                existing.value = value
                existing.source_utterance = source_utterance
                existing.updated_at = now
                fact = existing
            else:
                fact = MemoryFact(
                    key=normalised,
                    value=value,
                    source_utterance=source_utterance,
                    created_at=now,
                    updated_at=now,
                )
                facts[normalised] = fact

            self._evict(facts)
            self._save(facts)
            return fact

    def delete(self, key: str) -> bool:
        """
        Remove a fact by key.

        Args:
            key: Fact identifier; normalised before lookup.

        Returns:
            True when a fact was removed, False when the key was unknown.
        """
        with self._lock:
            facts = self._load()
            normalised = self.normalise_key(key)

            if normalised not in facts:
                return False

            del facts[normalised]
            self._save(facts)
            return True

    def find(self, query: str) -> list[MemoryFact]:
        """
        Search facts by case-insensitive substring across key and value.

        Args:
            query: Text to look for.

        Returns:
            Matching facts, newest-updated first; empty when nothing matches.
        """
        needle = (query or "").strip().lower()

        if not needle:
            return []

        return [
            fact
            for fact in self.all()
            if needle in fact.key.lower() or needle in fact.value.lower()
        ]

    def clear(self) -> None:
        """Forget everything and persist the empty store."""
        with self._lock:
            self._facts = {}
            self._save(self._facts)

    @staticmethod
    def normalise_key(key: str) -> str:
        """
        Reduce a key to its canonical lowercase snake_case form.

        Args:
            key: Raw key as supplied by the extractor or the user.

        Returns:
            The normalised key.
        """
        candidate = (key or "").strip().lower()
        candidate = _KEY_SEPARATORS.sub("_", candidate)
        candidate = _KEY_ILLEGAL.sub("_", candidate)
        return candidate.strip("_")

    def _load(self) -> dict[str, MemoryFact]:
        """
        Read the JSON document once and cache it for the process lifetime.

        Returns:
            The in-memory mapping of key to fact.
        """
        if self._facts is not None:
            return self._facts

        self._facts = {}

        if not self._path.exists():
            return self._facts

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            entries = raw["facts"] if isinstance(raw, dict) else raw

            if not isinstance(entries, list):
                raise ValueError("'facts' must be a JSON array.")

            for entry in entries:
                fact = from_dict(entry)
                fact.key = self.normalise_key(fact.key)
                if fact.key:
                    self._facts[fact.key] = fact

        except Exception as exc:
            # A damaged store must never stop ULTRON from booting: quarantine
            # the file so it can still be inspected, and carry on empty.
            self._facts = {}
            self._quarantine(exc)

        return self._facts

    def _quarantine(self, exc: Exception) -> None:
        """
        Move an unreadable store aside so a fresh one can take its place.

        Args:
            exc: The parse failure that triggered quarantine.
        """
        corrupt_path = self._path.with_name(self._path.name + ".corrupt")

        try:
            os.replace(self._path, corrupt_path)
            logger.warning(
                f"Memory store at '{self._path}' was unreadable ({exc}); "
                f"moved to '{corrupt_path}' and starting empty."
            )
        except Exception as move_exc:
            logger.warning(
                f"Memory store at '{self._path}' was unreadable ({exc}) and could "
                f"not be quarantined ({move_exc}); starting empty."
            )

    def _evict(self, facts: dict[str, MemoryFact]) -> None:
        """
        Drop the least recently updated facts until the store fits its cap.

        Args:
            facts: The mapping to trim in place.
        """
        if self._max_facts <= 0 or len(facts) <= self._max_facts:
            return

        ordered = sorted(facts.values(), key=lambda fact: fact.updated_at, reverse=True)

        for stale in ordered[self._max_facts:]:
            del facts[stale.key]

    def _save(self, facts: dict[str, MemoryFact]) -> None:
        """
        Persist the store, newest-updated first.

        The write goes to a sibling temp file and is then moved into place, so
        an interrupted save leaves the previous document intact rather than a
        half-written one.

        Args:
            facts: The mapping to persist.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        ordered = sorted(facts.values(), key=lambda fact: fact.updated_at, reverse=True)
        payload = {"facts": [to_dict(fact) for fact in ordered]}

        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self._path.parent),
            prefix=self._path.name + ".",
            suffix=".tmp",
            delete=False,
        )

        temp_path = Path(handle.name)

        try:
            with handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temp_path, self._path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        self._fsync_directory()

    def _fsync_directory(self) -> None:
        """
        Flush the rename itself to disk where the platform allows it.

        On POSIX the file contents can be durable while the directory entry
        pointing at them is not, so a power cut just after the replace could
        still lose the save. Windows has no directory handle to sync and
        journals the rename itself, so this is a no-op there.
        """
        if not hasattr(os, "O_DIRECTORY"):
            return

        try:
            fd = os.open(str(self._path.parent), os.O_DIRECTORY)

            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception as exc:
            logger.debug(f"Could not fsync '{self._path.parent}': {exc}")
