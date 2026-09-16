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


def _rrf_fuse(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion across multiple ranked result lists.

    RRF score = sum(1 / (k + rank_i)) for each list that contains the doc.
    Deduplication key prioritizes doc_id §section; falls back to url or title.
    """
    scores: dict[str, float] = {}
    docs_by_key: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            if doc.get("doc_id") and doc.get("section"):
                doc_key = f"{doc['doc_id']} {doc['section']}"
            else:
                doc_key = doc.get("url") or doc.get("title") or str(rank)
            scores[doc_key] = scores.get(doc_key, 0.0) + 1.0 / (k + rank)
            if doc_key not in docs_by_key:
                docs_by_key[doc_key] = doc
    sorted_keys = sorted(scores, key=lambda key_: scores[key_], reverse=True)
    return [docs_by_key[sk] for sk in sorted_keys]


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
                    logger.exception("Web search failed for '{}'", sq)
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

            # Local BM25 sparse search over enterprise policy documents
            bm25_docs: list[dict] = []
            try:
                from streaming_rag.corpus import SAMPLE_CORPUS
                from streaming_rag.retrieval import BM25Index
                if not hasattr(self, "_bm25_index"):
                    self._bm25_index = BM25Index()
                    self._bm25_index.index_documents(SAMPLE_CORPUS)
                for sq in event.subqueries:
                    hits = self._bm25_index.search(sq, top_k=3)
                    for doc_chunk, _score in hits:
                        bm25_docs.append({
                            "title": doc_chunk.title,
                            "url": f"corpus://{doc_chunk.doc_id}",
                            "snippet": doc_chunk.text[:200],
                            "content": doc_chunk.text,
                            "source": "local_bm25",
                            "doc_id": doc_chunk.doc_id,
                            "section": doc_chunk.section,
                        })
            except Exception:
                logger.debug("Local BM25 index unavailable or skipped")

            # Placeholder vector DB hook: if configured, enrich/merge vector results
            try:
                weaviate_url = getattr(self.container.settings, "weaviate_url", None)
            except Exception:
                weaviate_url = None

            vec_groups: list[list[dict]] = []
            if weaviate_url:
                # Use the new `weaviate_client` wrapper if available via container
                try:
                    # Prefer the container-managed weaviate client (lazily created)
                    wc = getattr(self.container, "weaviate_client", None)

                    if wc is not None:
                        # If an embeddings service is available, use it to embed subqueries
                        emb = getattr(self.container, "embeddings", None)
                        for sq in event.subqueries:
                            try:
                                if emb is not None:
                                    embedding = await emb.embed_texts([sq])
                                    vec = wc.vector_search(embedding=embedding[0], top_k=3)
                                else:
                                    vec = wc.vector_search(query=sq, top_k=3)
                                # Ensure doc_id/section fields are propagated
                                for item in vec:
                                    if "doc_id" not in item:
                                        item["doc_id"] = item.get("title", "")
                                    if "section" not in item:
                                        item["section"] = "1"
                                vec_groups.append(vec)
                            except Exception:
                                logger.exception("Weaviate vector search failed for '{}'", sq)
                except Exception:
                    logger.exception("Weaviate integration failed; continuing with web/bm25 results")

            # RRF fusion: merge web docs, local bm25 docs, and all vector groups
            ranked_inputs = []
            if docs:
                ranked_inputs.append(docs)
            if bm25_docs:
                ranked_inputs.append(bm25_docs)
            ranked_inputs.extend(vec_groups)

            if ranked_inputs:
                docs = _rrf_fuse(ranked_inputs)
                logger.debug("RRF fused {} lists → {} unique docs", len(ranked_inputs), len(docs))

            # Re-rank fused candidates using cross-encoder reranker if available
            try:
                reranker = getattr(self.container, "reranker", None)
                if reranker is not None:
                    try:
                        ranked = await reranker.rerank(event.original_query, docs)
                        # Replace docs with ranked results
                        docs = ranked
                        logger.debug("Re-ranked {} documents using cross-encoder", len(docs))
                    except Exception:
                        logger.exception("Reranker failed; publishing unranked docs")
            except Exception:
                logger.exception("Failed while attempting to rerank results")

            # Publish RetrievalResultEvent with gathered documents
            result_event = RetrievalResultEvent(
                query=event.original_query,
                results=docs,
                decision="hybrid",
                session_id=session_id,
                turn_id=turn_id,
                trigger_timestamp_s=getattr(event, "trigger_timestamp_s", None),
                start_timestamp_s=getattr(event, "start_timestamp_s", None),
                timestamp_s=getattr(event, "trigger_timestamp_s", None),
            )

            # Before publishing, check cancellation: if turn is no longer current, abort.
            if not self.container.cancellation_manager.is_current(session_id, turn_id):
                logger.info("HybridRetriever aborting publish: turn no longer current")
                return

            await self.container.event_bus.publish(result_event)
            logger.info("HybridRetriever published {} documents for '{}'", len(docs), event.original_query)
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
