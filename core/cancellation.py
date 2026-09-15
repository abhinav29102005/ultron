"""
core/cancellation.py
=====================

Simple session/turn cancellation registry used to cancel in-flight
retrievals when newer user input (a newer turn) arrives for the same
session. This is intentionally lightweight: the retriever checks the
registry to determine whether a turn is still the active one.
"""

from __future__ import annotations

from typing import Dict
import asyncio


class CancellationManager:
    def __init__(self) -> None:
        # maps session_id -> current active turn_id
        self._active: Dict[str, int] = {}
        # maps session_id -> asyncio.Task for the active retrieval
        self._tasks: Dict[str, asyncio.Task] = {}

    def set_active_turn(self, session_id: str, turn_id: int) -> None:
        if not session_id:
            return
        self._active[session_id] = turn_id

    def is_current(self, session_id: str | None, turn_id: int | None) -> bool:
        if not session_id or turn_id is None:
            return True
        return self._active.get(session_id) == turn_id

    def clear_session(self, session_id: str) -> None:
        if session_id in self._active:
            del self._active[session_id]
        # Also cancel and clear any active task
        task = self._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def register_task(self, session_id: str | None, turn_id: int | None, task: asyncio.Task) -> None:
        """Register an asyncio Task for a session/turn. Cancels any previous task for the session.

        The newest task is stored; older task (if any) will be cancelled so only
        the latest retrieval continues.
        """
        if not session_id:
            return

        # Cancel and remove previous task
        prev = self._tasks.get(session_id)
        if prev and not prev.done():
            try:
                prev.cancel()
            except Exception:
                pass

        self._tasks[session_id] = task
