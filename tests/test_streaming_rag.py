"""
tests/test_streaming_rag.py
===========================
Real-data integration and unit tests for the Streaming Live RAG pipeline.
ZERO MOCKS: Tested entirely on real corpus documents, real BM25 lexical inverted
index, real dense semantic embedding vectors, real Reciprocal Rank Fusion,
real multi-intent decomposition, and real session state management.
"""
from __future__ import annotations

import pytest
from streaming_rag.models import ControllerAction, StreamingChunk, DocumentChunk
from streaming_rag.pipeline import StreamingLiveRAG
from streaming_rag.corpus import SAMPLE_CORPUS
from streaming_rag.retrieval import HybridRetriever, BM25Index, DenseSemanticIndex
from streaming_rag.controller import RetrievalController


@pytest.fixture
def rag():
    return StreamingLiveRAG()


def test_corpus_indexing_and_structure(rag):
    assert len(rag.corpus) >= 6
    for doc in rag.corpus:
        assert doc.doc_id.startswith('Doc_')
        assert doc.section.startswith('§')
        assert len(doc.text) > 20
        assert doc.citation_tag == f'{doc.doc_id} {doc.section}'


def test_real_bm25_and_dense_retrieval():
    retriever = HybridRetriever()
    retriever.ingest_corpus(SAMPLE_CORPUS)
    
    # Exact keyword query on travel policy
    results = retriever.retrieve('travel reimbursement rule for employee trip', top_k=2)
    assert len(results) > 0
    assert any('Doc_45' in r.doc_id for r in results)


def test_early_retrieval_triggering(rag):
    # Stream from Theme 4 Guide Example 1
    stream = [
        StreamingChunk(timestamp_s=0.0, text='I need to plan a customer workshop in...'),
        StreamingChunk(timestamp_s=0.8, text='...Pune for 30 people, and I need...'),
        StreamingChunk(timestamp_s=1.6, text='...the cancellation policy and the catering options.'),
        StreamingChunk(timestamp_s=2.1, text='I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy and the catering options.', is_final=True),
    ]
    record = rag.process_stream(stream, session_id='test_early_gain')
    assert record.telemetry.retrieval_trigger_timestamp_s == 0.8
    assert record.telemetry.early_retrieval_gain_ms == 1300.0
    assert len(record.citations) > 0
    assert any('Doc_12' in c for c in record.citations)


def test_multi_intent_decomposition(rag):
    stream = [
        StreamingChunk(
            timestamp_s=2.1,
            text='I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy and the catering options.',
            is_final=True
        )
    ]
    record = rag.process_stream(stream, session_id='test_multi_intent')
    assert len(record.sub_queries) >= 2
    assert any('workshop' in sq or 'Pune' in sq for sq in record.sub_queries)


def test_session_refinement_delta_query(rag):
    # Turn 1: Base request
    turn_1 = [
        StreamingChunk(timestamp_s=1.0, text='Summarize the travel reimbursement rule for an employee trip.', is_final=True)
    ]
    rec_1 = rag.process_stream(turn_1, session_id='sess_refine')
    assert rec_1.answer_version == 1
    assert any('Doc_45' in c for c in rec_1.citations)

    # Turn 2: Late-arriving constraint
    turn_2 = [
        StreamingChunk(timestamp_s=1.0, text='The trip was international and the booking was made after travel.', is_final=True)
    ]
    rec_2 = rag.process_stream(turn_2, session_id='sess_refine')
    assert rec_2.answer_version == 2
    # Preserves Turn 1 base citations and includes Turn 2 delta citation
    assert 'Doc_45 §1' in rec_2.citations
    assert 'Doc_45 §3' in rec_2.citations


def test_presentation_query_suppression(rag):
    # Step 1: Base turn
    turn_1 = [
        StreamingChunk(timestamp_s=1.0, text='Summarize the travel reimbursement rule for an employee trip.', is_final=True)
    ]
    rag.process_stream(turn_1, session_id='sess_pres')

    # Step 2: Presentation-only turn
    turn_2 = [
        StreamingChunk(timestamp_s=0.5, text='Please repeat your last answer in two bullets.', is_final=True)
    ]
    record = rag.process_stream(turn_2, session_id='sess_pres')
    assert '•' in record.answer
    assert len(record.retrieval_events) == 0  # 0 vector searches executed
    assert record.citations == ['Doc_45 §1']  # Citations preserved without fabrication


def test_uncertainty_flagging_missing_evidence(rag):
    stream = [
        StreamingChunk(timestamp_s=1.0, text='What is the submarine maintenance protocol for naval fleets?', is_final=True)
    ]
    record = rag.process_stream(stream, session_id='sess_unknown')
    # Since naval fleets are not in the corpus, uncertainty must be raised
    assert record.uncertainty is not None


def test_telemetry_trace_recording(rag):
    stream = [
        StreamingChunk(timestamp_s=0.0, text='I need to plan a customer workshop in...'),
        StreamingChunk(timestamp_s=0.8, text='...Pune for 30 people, and I need...'),
        StreamingChunk(timestamp_s=2.1, text='...the cancellation policy and the catering options.', is_final=True),
    ]
    record = rag.process_stream(stream, session_id='sess_telem')
    assert record.telemetry.total_latency_ms > 0
    assert record.session_id == 'sess_telem'
    assert len(record.retrieval_events) > 0
