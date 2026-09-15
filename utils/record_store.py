"""
utils/record_store.py – A small append-mostly JSON list on disk
================================================================
Notes and reminders are the same storage problem: a short list of dicts that
has to survive a restart and must never be left half-written.

``memory/store.py`` already solves this for the fact store, but it is built
around a keyed dict of :class:`MemoryFact` with eviction and quarantine
behaviour that neither of these wants. Rather than bend that or copy its
internals twice, the one part worth sharing -- the atomic write -- lives here.

Atomicity is the whole point. A JSON file truncated by a power cut or a
mid-write kill reads back as a parse error, and the naive version of this
loses every note the user ever took. Writing to a temporary file in the same
directory and replacing the original means a reader sees either the old file
or the new one, never a partial one.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from config.logging_config import get_logger

logger = get_logger("record_store")

#: Where a relative path is anchored.
#:
#: The project root, not the working directory -- the same reasoning as
#: memory/store.py. Launched from a different folder, a relative path would
#: point at a different file and the user would appear to have lost
#: everything.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class RecordStore:
    """A list of dicts, persisted as JSON, written atomically."""

    def __init__(self, path: Path | str) -> None:
        self._path = self.resolve_path(path)
        self._lock = threading.Lock()

    @staticmethod
    def resolve_path(path: Path | str) -> Path:
        candidate = Path(path).expanduser()
        return candidate if candidate.is_absolute() else _PROJECT_ROOT / candidate

    @property
    def path(self) -> Path:
        return self._path

    def all(self) -> list[dict[str, Any]]:
        """Every record, oldest first. An unreadable file reads as empty."""
        with self._lock:
            return self._load()

    def replace(self, records: list[dict[str, Any]]) -> None:
        with self._lock:
            self._save(records)

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            records = self._load()
            records.append(record)
            self._save(records)

    def update(self, record_id: str, **changes: Any) -> bool:
        """Apply ``changes`` to the record with this id. True when one matched."""
        with self._lock:
            records = self._load()
            for record in records:
                if record.get("id") == record_id:
                    record.update(changes)
                    self._save(records)
                    return True
            return False

    def remove(self, record_id: str) -> bool:
        with self._lock:
            records = self._load()
            kept = [r for r in records if r.get("id") != record_id]
            if len(kept) == len(records):
                return False
            self._save(kept)
            return True

    # ── disk ──────────────────────────────────────────────────────────────

    def _load(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # Losing the file is bad; refusing to start because of it is
            # worse. An unreadable store reads as empty and the next write
            # replaces it.
            logger.warning(f"Could not read {self._path} ({exc}); treating as empty.")
            return []

        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    def _save(self, records: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Same directory as the target: os.replace is only atomic within one
        # filesystem, and the system temp dir is often a different one.
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=self._path.name,
            suffix=".tmp",
            delete=False,
        )

        try:
            with handle:
                json.dump(records, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(handle.name, self._path)
        except BaseException:
            # Never leave the temporary file behind on a failed write.
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise
