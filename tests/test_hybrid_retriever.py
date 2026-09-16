"""
tests/test_hybrid_retriever.py
==============================
Tests for intelligence/hybrid_retriever.py:
- Local BM25 sparse search fallback over enterprise policy documents
- Reciprocal Rank Fusion (RRF) with doc_id and section deduplication
- Timing and telemetry metadata propagation
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from intelligence.hybrid_retriever import HybridRetriever, _rrf_fuse
from intelligence.decomposer import DecomposedQueryEvent
from intelligence.retrieval_handler import RetrievalResultEvent


def test_rrf_fuse_preserves_doc_id_and_section_keys():
    """Verify RRF deduplicates by doc_id and section while fusing ranks."""
    list_a = [
        {"doc_id": "Doc_12", "section": "§2", "title": "Pune Workshop", "score": 10},
        {"doc_id": "Doc_45", "section": "§1", "title": "Travel Domestic", "score": 8},
    ]
    list_b = [
        {"doc_id": "Doc_45", "section": "§1", "title": "Travel Domestic", "score": 9},
        {"doc_id": "Doc_31", "section": "§4", "title": "Cancellation Policy", "score": 7},
    ]

    fused = _rrf_fuse([list_a, list_b], k=60)
    assert len(fused) == 3

    # Doc_45 §1 appeared in both lists, so its reciprocal rank score is highest
    assert fused[0]["doc_id"] == "Doc_45"
    assert fused[0]["section"] == "§1"

    doc_keys = {f"{d['doc_id']} {d['section']}" for d in fused}
    assert doc_keys == {"Doc_12 §2", "Doc_45 §1", "Doc_31 §4"}


@pytest.mark.asyncio
async def test_hybrid_retriever_local_bm25_offline():
    """Verify that when web and vector DB are absent or fail, local BM25 returns grounded docs."""
    mock_container = MagicMock()
    mock_container.settings.weaviate_url = None
    mock_container.cancellation_manager.is_current.return_value = True

    # Web search returns empty (offline/mock)
    mock_web = MagicMock()
    mock_web.search = AsyncMock(return_value=[])
    mock_container.web_skill = mock_web

    published_events = []
    async def _capture_publish(evt):
        published_events.append(evt)

    mock_container.event_bus.publish = AsyncMock(side_effect=_capture_publish)
    mock_container.reranker = None

    retriever = HybridRetriever(mock_container)

    event = DecomposedQueryEvent(
        original_query="Pune workshop cancellation policy and catering",
        subqueries=["cancellation policy workshop", "catering options"],
        session_id="test_sess_01",
        turn_id=1,
        trigger_timestamp_s=100.0,
        start_timestamp_s=98.0,
    )

    await retriever._run_retrieval(event)

    assert len(published_events) == 1
    res_evt: RetrievalResultEvent = published_events[0]
    assert res_evt.decision == "hybrid"
    assert res_evt.session_id == "test_sess_01"
    assert res_evt.turn_id == 1
    assert res_evt.trigger_timestamp_s == 100.0
    assert res_evt.start_timestamp_s == 98.0

    # Ensure local BM25 returned results with doc_id and section
    assert len(res_evt.results) > 0
    doc_ids = {r.get("doc_id") for r in res_evt.results}
    assert any("Doc_" in str(d) for d in doc_ids)
    assert any("§" in str(r.get("section", "")) for r in res_evt.results)
