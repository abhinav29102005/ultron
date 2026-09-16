"""
streaming_rag/pipeline.py – Streaming Live RAG End-to-End Pipeline
==================================================================
Orchestrates Components 1 through 5:
- Ingests streaming timestamped transcript chunks
- Triggers speculative retrieval early before utterance end
- Dispatches parallel multi-intent sub-queries
- Fuses evidence via hybrid search and RRF
- Synthesizes grounded answers with exact section citations [Doc_XX §YY]
- Manages session state, delta constraints, and telemetry
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional
from streaming_rag.corpus import SAMPLE_CORPUS
from streaming_rag.controller import RetrievalController
from streaming_rag.decomposer import MultiIntentDecomposer
from streaming_rag.models import (
    ControllerAction,
    DocumentChunk,
    StreamingChunk,
    StructuredOutputRecord,
)
from streaming_rag.retrieval import HybridRetriever
from streaming_rag.synthesizer import (
    DeltaConstraintResolver,
    GroundedSynthesizer,
    SessionContext,
)
from streaming_rag.telemetry import TelemetryEngine


class StreamingLiveRAG:
    """Unified engine implementing Samsung Theme 4 Streaming Live RAG."""

    def __init__(self, corpus: Optional[List[DocumentChunk]] = None):
        self.retriever = HybridRetriever()
        self.controller = RetrievalController()
        self.decomposer = MultiIntentDecomposer()
        self.synthesizer = GroundedSynthesizer()
        self.delta_resolver = DeltaConstraintResolver()
        self.sessions: Dict[str, SessionContext] = {}

        # Ingest default or provided corpus
        self.corpus = corpus or SAMPLE_CORPUS
        self.retriever.ingest_corpus(self.corpus)

    def get_or_create_session(self, session_id: str) -> SessionContext:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionContext(session_id)
        return self.sessions[session_id]

    def process_stream(
        self,
        stream_chunks: List[StreamingChunk],
        session_id: str = "sess_default"
    ) -> StructuredOutputRecord:
        """Processes an incoming sequence of timestamped transcript chunks."""
        session = self.get_or_create_session(session_id)
        telemetry = TelemetryEngine(session_id)
        self.controller.reset()

        speculative_chunks: List[DocumentChunk] = []
        speculative_query: Optional[str] = None
        sub_queries: List[str] = []
        has_session = bool(session.last_answer)

        # 1. Stream Evaluation Loop
        for chunk in stream_chunks:
            telemetry.record_stream_chunk(chunk.timestamp_s, chunk.is_final)
            decision = self.controller.evaluate_chunk(chunk, has_session_context=has_session)

            if decision.action == ControllerAction.NO_RETRIEVAL_SUPPRESS:
                # Presentation query suppression (Zero vector queries executed)
                formatted_text = self.synthesizer.reformat_presentation(chunk.text, session)
                return telemetry.generate_record(
                    answer_version=session.active_version,
                    answer=formatted_text,
                    citations=session.active_citations,
                    sub_queries=[],
                    uncertainty=None,
                )

            elif decision.action == ControllerAction.RETRIEVE_EARLY and not speculative_chunks:
                # Speculative early retrieval triggered before final utterance
                speculative_query = decision.speculative_query or chunk.text
                speculative_chunks = self.retriever.retrieve(speculative_query, top_k=3)
                telemetry.record_retrieval_trigger(
                    timestamp_s=chunk.timestamp_s,
                    query=speculative_query,
                    trigger_type="speculative_early",
                    chunks_count=len(speculative_chunks)
                )

            elif decision.action == ControllerAction.DECOMPOSE_AND_PARALLEL_RETRIEVE:
                # Compound multi-intent utterance detected
                sub_queries = self.decomposer.decompose(chunk.text)

        # 2. Final Utterance Handling
        final_chunk = stream_chunks[-1]
        final_text = final_chunk.text.strip()

        # Check if follow-up turn is a delta constraint
        is_delta = self.delta_resolver.is_late_constraint(final_text, session)
        if is_delta:
            delta_q = self.delta_resolver.formulate_delta_query(final_text, session)
            delta_chunks = self.retriever.retrieve(delta_q, top_k=2)
            telemetry.record_retrieval_trigger(
                timestamp_s=final_chunk.timestamp_s,
                query=delta_q,
                trigger_type="delta_query",
                chunks_count=len(delta_chunks)
            )
            retrieved_pool = list({c.citation_tag: c for c in (speculative_chunks + delta_chunks)}.values())
            sub_queries = [delta_q]
        else:
            if not sub_queries:
                sub_queries = self.decomposer.decompose(final_text)

            # If multi-intent sub-queries exist, parallel retrieve
            if len(sub_queries) >= 2:
                for sq in sub_queries:
                    telemetry.record_retrieval_trigger(
                        timestamp_s=final_chunk.timestamp_s,
                        query=sq,
                        trigger_type="multi_intent"
                    )
                multi_chunks = self.retriever.retrieve_parallel(sub_queries)
                retrieved_pool = list({c.citation_tag: c for c in (speculative_chunks + multi_chunks)}.values())
            else:
                if not speculative_chunks:
                    speculative_chunks = self.retriever.retrieve(final_text, top_k=3)
                    telemetry.record_retrieval_trigger(
                        timestamp_s=final_chunk.timestamp_s,
                        query=final_text,
                        trigger_type="sequential_fallback",
                        chunks_count=len(speculative_chunks)
                    )
                retrieved_pool = speculative_chunks

        # 3. Grounded Synthesis
        answer, citations, uncertainty = self.synthesizer.synthesize(
            query=final_text,
            chunks=retrieved_pool,
            sub_queries=sub_queries if sub_queries else [final_text],
            session=session,
            is_delta_refinement=is_delta
        )

        session.last_query = final_text
        return telemetry.generate_record(
            answer_version=session.active_version,
            answer=answer,
            citations=citations,
            sub_queries=sub_queries,
            uncertainty=uncertainty
        )
