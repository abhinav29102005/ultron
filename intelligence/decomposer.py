"""
intelligence/decomposer.py
==========================

Minimal multi-intent decomposer stub. Listens for `RetrievalResultEvent`
and emits `DecomposedQueryEvent` containing a list of sub-queries derived
from the retrieval trigger. This is a placeholder to let the retrieval ->
decomposition -> retriever plumbing be exercised end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, List

from core.event_bus import BaseEvent
from .retrieval_handler import RetrievalResultEvent

logger = logging.getLogger("decomposer")


@dataclass
class DecomposedQueryEvent(BaseEvent):
    original_query: str
    subqueries: List[str] = field(default_factory=list)
    session_id: str | None = None
    turn_id: int | None = None
    trigger_timestamp_s: float | None = None
    start_timestamp_s: float | None = None


class Decomposer:
    """Very small rule-based decomposer for demonstration purposes.

    Splits the incoming query on common conjunctions and commas into
    sub-queries. Replace with an LLM-backed decomposer for production.
    """

    def __init__(self, container: Any) -> None:
        self.container = container
        self._subscribed = False
        self._handler = None

    async def start(self) -> None:
        if self._subscribed:
            return

        async def _on_retrieval_result(event: RetrievalResultEvent) -> None:
            try:
                q = (event.query or "").strip()
                if not q:
                    return

                # Naive split on ' and ', ',', ';' — removes trivial whitespace.
                parts = [p.strip() for p in __split_query(q) if p.strip()]

                # If splitting produced nothing meaningful, keep the whole query.
                subqueries = parts if len(parts) > 0 else [q]

                decomposed = DecomposedQueryEvent(
                    original_query=q,
                    subqueries=subqueries,
                    session_id=getattr(event, "session_id", None),
                    turn_id=getattr(event, "turn_id", None),
                    trigger_timestamp_s=getattr(event, "trigger_timestamp_s", None) or getattr(event, "timestamp_s", None),
                    start_timestamp_s=getattr(event, "start_timestamp_s", None),
                )
                await self.container.event_bus.publish(decomposed)
                logger.info("Published DecomposedQueryEvent with {} subqueries", len(subqueries))
            except Exception:
                logger.exception("Decomposer failed handling RetrievalResultEvent")

        self._handler = _on_retrieval_result
        try:
            self.container.event_bus.subscribe(RetrievalResultEvent, self._handler)
            self._subscribed = True
            logger.info("Decomposer subscribed to RetrievalResultEvent.")
        except Exception:
            logger.exception("Failed to subscribe Decomposer to EventBus")

    async def close(self) -> None:
        if self._subscribed and self._handler is not None:
            try:
                self.container.event_bus.unsubscribe(RetrievalResultEvent, self._handler)
            except Exception:
                logger.debug("Failed to unsubscribe Decomposer")
            self._subscribed = False
            self._handler = None
            logger.info("Decomposer stopped.")


def __split_query(q: str):
    separators = [",", ";", " and "]
    parts = [q]
    for sep in separators:
        new_parts: list[str] = []
        for p in parts:
            new_parts.extend(p.split(sep))
        parts = new_parts
    return parts
