"""
intelligence/hybrid_retriever.py
================================

Hybrid retriever that combines live web search (via `WebSkill`) with an
optional vector store backend (Weaviate/Milvus) when configured. It fetches
and extracts page text, constructs light-weight document objects with
provenance, and publishes `RetrievalResultEvent` for downstream consumption.

This implementation is intentionally dependency-light: if a configured
vector backend client is not available, it gracefully falls back to web-only
retrieval so the pipeline remains functional.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .decomposer import DecomposedQueryEvent
from .retrieval_handler import RetrievalResultEvent

logger = logging.getLogger("hybrid_retriever")


class HybridRetriever:
    """Hybrid retriever combining web search and optional vector DB lookups.

    Behaviour:
      - On `DecomposedQueryEvent`, perform web search(s) for each subquery;
      - Fetch page text for top results and build document payloads;
      - If a vector DB client is configured, perform a vector search too and
        merge results (not implemented fully here — placeholder hook).
      - Publish `RetrievalResultEvent` containing documents and provenance.
    """

    def __init__(self, container: Any) -> None:
        self.container = container
        self._subscribed = False
        self._handler = None

    async def start(self) -> None:
        if self._subscribed:
            return

        async def _on_decomposed(event: DecomposedQueryEvent) -> None:
            # Run the retrieval in a cancellable background task and register
            # it with the cancellation manager so newer turns cancel older work.
            task = asyncio.create_task(self._run_retrieval(event))
            self.container.cancellation_manager.register_task(
                getattr(event, "session_id", None), getattr(event, "turn_id", None), task
            )

        self._handler = _on_decomposed
        try:
            self.container.event_bus.subscribe(DecomposedQueryEvent, self._handler)
            self._subscribed = True
            logger.info("HybridRetriever subscribed to DecomposedQueryEvent.")
        except Exception:
            logger.exception("Failed to subscribe HybridRetriever to EventBus")

    async def _run_retrieval(self, event: DecomposedQueryEvent) -> None:
        try:
            session_id = getattr(event, "session_id", None)
            turn_id = getattr(event, "turn_id", None)

            docs: list[dict] = []

            # Perform web searches in parallel for subqueries
            web = self.container.web_skill

            async def _fetch_for_subquery(sq: str):
                try:
                    results = await web.search(sq, max_results=3)
                except Exception:
                    logger.exception("Web search failed for '%s'", sq)
                    return []

                out = []
                for r in results:
                    try:
                        text = await web.fetch_page(r.url, max_chars=4000)
                    except Exception:
                        text = ""
                    out.append({
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet,
                        "content": text,
                        "source": r.source or "web",
                    })
                return out

            coros = [ _fetch_for_subquery(sq) for sq in event.subqueries ]
            groups = await asyncio.gather(*coros, return_exceptions=True)
            for grp in groups:
                if isinstance(grp, Exception):
                    continue
                docs.extend(grp)

            # Placeholder vector DB hook: if configured, enrich/merge vector results
            try:
                weaviate_url = getattr(self.container.settings, "weaviate_url", None)
            except Exception:
                weaviate_url = None

            if weaviate_url:
                # Attempt to import client lazily; if it fails, log and continue.
                try:
                    import weaviate  # type: ignore

                    # TODO: implement vector search and merge with `docs`.
                    logger.debug("Weaviate configured; vector search hook available.")
                except Exception:
                    logger.exception("Weaviate client import failed; skipping vector search")

            # Publish RetrievalResultEvent with gathered documents
            result_event = RetrievalResultEvent(
                query=event.original_query,
                results=docs,
                decision="hybrid",
                session_id=session_id,
                turn_id=turn_id,
            )

            # Before publishing, check cancellation: if turn is no longer current, abort.
            if not self.container.cancellation_manager.is_current(session_id, turn_id):
                logger.info("HybridRetriever aborting publish: turn no longer current")
                return

            await self.container.event_bus.publish(result_event)
            logger.info("HybridRetriever published %d documents for '%s'", len(docs), event.original_query)
        except asyncio.CancelledError:
            logger.info("HybridRetriever retrieval task cancelled")
        except Exception:
            logger.exception("HybridRetriever failed during retrieval run")

    async def close(self) -> None:
        if self._subscribed and self._handler is not None:
            try:
                self.container.event_bus.unsubscribe(DecomposedQueryEvent, self._handler)
            except Exception:
                logger.debug("Failed to unsubscribe HybridRetriever")
            self._subscribed = False
            self._handler = None
            logger.info("HybridRetriever stopped.")
