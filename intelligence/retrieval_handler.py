"""
intelligence/retrieval_handler.py
=================================

Simple consumer for `RetrievalEvent` that acts as a placeholder for the
retrieval pipeline. When a retrieval is requested the handler publishes a
`RetrievalResultEvent` with a minimal payload so downstream components can
hook into the flow while we build the real retriever.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from core.event_bus import BaseEvent
from .retrieval_controller import RetrievalEvent

logger = logging.getLogger("retrieval.handler")


@dataclass
class RetrievalResultEvent(BaseEvent):
    """Published when a (stub) retrieval run completes.

    Fields:
        query: the partial query that triggered retrieval
        results: a list of lightweight result dicts (title,url,snippet)
        decision: decision string carried from the trigger
    """
    query: str
    results: list[dict] = field(default_factory=list)
    decision: str = ""
    session_id: str | None = None
    turn_id: int | None = None


class RetrievalHandler:
    """Subscribe to `RetrievalEvent` and emit `RetrievalResultEvent`.

    Currently a stub: it returns an empty results list and logs the trigger.
    Replace with the hybrid retriever integration later.
    """

    def __init__(self, container: Any) -> None:
        self.container = container
        self._subscribed = False
        self._handler = None

    async def start(self) -> None:
        if self._subscribed:
            return

        async def _on_retrieval(event: RetrievalEvent) -> None:
            try:
                logger.info(f"Retrieval requested: {event.decision} -> {event.text}")

                # Stubbed results: empty list for now. Real retriever goes here.
                result_event = RetrievalResultEvent(
                    query=event.text,
                    results=[],
                    decision=event.decision,
                    session_id=getattr(event, "session_id", None),
                    turn_id=getattr(event, "turn_id", None),
                )
                await self.container.event_bus.publish(result_event)
                logger.debug("Published RetrievalResultEvent stub.")
            except Exception:
                logger.exception("RetrievalHandler failed processing event")

        self._handler = _on_retrieval
        try:
            from .retrieval_controller import RetrievalEvent as _RE

            self.container.event_bus.subscribe(_RE, self._handler)
            self._subscribed = True
            logger.info("RetrievalHandler subscribed to RetrievalEvent.")
        except Exception:
            logger.exception("Failed to subscribe RetrievalHandler to EventBus")

    async def close(self) -> None:
        if self._subscribed and self._handler is not None:
            try:
                from .retrieval_controller import RetrievalEvent as _RE

                self.container.event_bus.unsubscribe(_RE, self._handler)
            except Exception:
                logger.debug("Failed to unsubscribe RetrievalHandler")
            self._subscribed = False
            self._handler = None
            logger.info("RetrievalHandler stopped.")
