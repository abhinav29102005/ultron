"""
intelligence/retriever.py
=========================

Minimal retriever stub that consumes `DecomposedQueryEvent` and publishes
`RetrievalResultEvent` with synthetic documents and provenance. This gives
us an end-to-end testable pipeline for Streaming Live RAG while the real
hybrid retriever is developed.
"""

from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any

from core.event_bus import BaseEvent
from .decomposer import DecomposedQueryEvent
from .retrieval_handler import RetrievalResultEvent

logger = logging.getLogger("retriever")


class Retriever:
    """Stub retriever that returns synthetic documents per subquery."""

    def __init__(self, container: Any) -> None:
        self.container = container
        self._subscribed = False
        self._handler = None

    async def start(self) -> None:
        if self._subscribed:
            return

        async def _on_decomposed(event: DecomposedQueryEvent) -> None:
            try:
                # Check cancellation: if this turn is no longer current, abort.
                session_id = getattr(event, "session_id", None)
                turn_id = getattr(event, "turn_id", None)
                if not self.container.cancellation_manager.is_current(session_id, turn_id):
                    logger.info("Retriever aborting: turn no longer current")
                    return

                docs = []
                for i, sq in enumerate(event.subqueries):
                    docs.append({
                        "id": f"stub-{i}",
                        "title": f"Result for '{sq}'",
                        "url": f"https://example.com/{i}",
                        "snippet": f"Synthetic snippet matching {sq}",
                        "source": "stub",
                    })

                result_event = RetrievalResultEvent(
                    query=event.original_query,
                    results=docs,
                    decision="retrieve_stub",
                    session_id=session_id,
                    turn_id=turn_id,
                )

                await self.container.event_bus.publish(result_event)
                logger.info(f"Retriever published {len(docs)} stub docs for '{event.original_query}'")
            except Exception:
                logger.exception("Retriever failed handling DecomposedQueryEvent")

        self._handler = _on_decomposed
        try:
            self.container.event_bus.subscribe(DecomposedQueryEvent, self._handler)
            self._subscribed = True
            logger.info("Retriever subscribed to DecomposedQueryEvent.")
        except Exception:
            logger.exception("Failed to subscribe Retriever to EventBus")

    async def close(self) -> None:
        if self._subscribed and self._handler is not None:
            try:
                self.container.event_bus.unsubscribe(DecomposedQueryEvent, self._handler)
            except Exception:
                logger.debug("Failed to unsubscribe Retriever")
            self._subscribed = False
            self._handler = None
            logger.info("Retriever stopped.")
