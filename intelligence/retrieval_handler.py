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
    timestamp_s: float | None = None
    trigger_timestamp_s: float | None = None
    start_timestamp_s: float | None = None


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

                # Delegate to hybrid retriever when configured
                if getattr(self.container.settings, "weaviate_url", None):
                    # If hybrid retriever is available it will subscribe to DecomposedQueryEvent
                    logger.debug("Weaviate configured; RetrievalHandler acting as pass-through stub.")
                    # Publish a minimal result so the pipeline continues while hybrid retriever runs
                    result_event = RetrievalResultEvent(
                        query=event.text,
                        results=[],
                        decision=event.decision,
                        session_id=getattr(event, "session_id", None),
                        turn_id=getattr(event, "turn_id", None),
                        timestamp_s=getattr(event, "timestamp_s", None),
                    )
                    await self.container.event_bus.publish(result_event)
                else:
                    # No vector DB configured: keep stub behaviour but include web search hints
                    logger.debug("No Weaviate configured; performing web-only quick pass.")
                    web = self.container.web_skill
                    docs = []
                    try:
                        results = await web.search(event.text, max_results=3)
                        for r in results:
                            try:
                                text = await web.fetch_page(r.url, max_chars=1600)
                            except Exception:
                                text = ""
                            docs.append({
                                "title": r.title,
                                "url": r.url,
                                "snippet": r.snippet,
                                "content": text,
                                "source": r.source or "web",
                            })
                    except Exception:
                        logger.exception("Quick web pass failed in RetrievalHandler")

                    result_event = RetrievalResultEvent(
                        query=event.text,
                        results=docs,
                        decision=event.decision,
                        session_id=getattr(event, "session_id", None),
                        turn_id=getattr(event, "turn_id", None),
                        timestamp_s=getattr(event, "timestamp_s", None),
                    )
                    await self.container.event_bus.publish(result_event)
                    logger.debug("Published RetrievalResultEvent with {} web docs.", len(docs))
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
