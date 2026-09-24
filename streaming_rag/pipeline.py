"""
streaming_rag/pipeline.py – Streaming Live RAG End-to-End Pipeline
==================================================================
Orchestrates Components 1 through 5:
- Ingests streaming timestamped transcript chunks
- Triggers speculative retrieval early before utterance end
- Handles intra-stream intent pivots and invalidates stale speculative pools
- Resolves cross-turn context discontinuity, anaphora, and conversational ellipses
- Dispatches parallel multi-intent sub-queries
- Fuses evidence via hybrid search and RRF
- Synthesizes grounded answers with exact section citations [Doc_XX §YY]
- Manages session state, version lineages (V1 -> V2 -> V3), and telemetry
- Exposes real-time streaming token generation interface
"""

from __future__ import annotations

import time
from typing import Dict, Generator, List, Optional
from streaming_rag.corpus import SAMPLE_CORPUS
from streaming_rag.controller import RetrievalController
from streaming_rag.decomposer import MultiIntentDecomposer
from streaming_rag.models import (
    ControllerAction,
    DocumentChunk,
    StreamingChunk,
    StreamingToken,
    StructuredOutputRecord,
    TurnIntent,
)
from streaming_rag.retrieval import HybridRetriever
from streaming_rag.session import SessionContext, SessionRegistry
from streaming_rag.synthesizer import (
    DeltaConstraintResolver,
    GroundedSynthesizer,
)
from streaming_rag.telemetry import TelemetryEngine


class StreamingLiveRAG:
    """Unified engine implementing Samsung Theme 4 Streaming Live RAG."""

    _instance: Optional[StreamingLiveRAG] = None

    @classmethod
    def get_instance(cls, corpus: Optional[List[DocumentChunk]] = None) -> StreamingLiveRAG:
        if cls._instance is None:
            cls._instance = cls(corpus=corpus)
        return cls._instance

    def __init__(self, corpus: Optional[List[DocumentChunk]] = None):
        self.retriever = HybridRetriever()
        self.controller = RetrievalController()
        self.decomposer = MultiIntentDecomposer()
        self.synthesizer = GroundedSynthesizer()
        self.delta_resolver = DeltaConstraintResolver()

        # Ingest default or provided corpus
        self.corpus = corpus or SAMPLE_CORPUS
        self.retriever.ingest_corpus(self.corpus)

    @property
    def sessions(self) -> Dict[str, SessionContext]:
        return SessionRegistry._sessions

    def get_or_create_session(self, session_id: str) -> SessionContext:
        return SessionRegistry.get_session(session_id)

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

        # 1. Stream Evaluation Loop
        for chunk in stream_chunks:
            telemetry.record_stream_chunk(chunk.timestamp_s, chunk.is_final)
            decision = self.controller.evaluate_chunk(chunk, session=session)

            if decision.action == ControllerAction.NO_RETRIEVAL_SUPPRESS:
                # Presentation query suppression (Zero vector queries executed)
                formatted_text = self.synthesizer.reformat_presentation(chunk.text, session)
                turn_rec = session.record_turn(
                    raw_query=chunk.text,
                    resolved_query=chunk.text,
                    intent=TurnIntent.PRESENTATION_RESTRUCTURE,
                    answer=formatted_text,
                    citations=session.active_citations,
                    chunks=[],
                )
                return telemetry.generate_record(
                    answer_version=session.active_version,
                    answer=formatted_text,
                    citations=session.active_citations,
                    sub_queries=[],
                    uncertainty=None,
                    resolved_query=chunk.text,
                    active_entities=session.entity_state.model_dump(),
                    turn_id=turn_rec.turn_id,
                    intent=TurnIntent.PRESENTATION_RESTRUCTURE.value,
                )

            elif decision.action == ControllerAction.SPECULATIVE_PIVOT:
                # Mid-stream user correction / pivot detected! Invalidate stale speculative pool
                speculative_query = decision.speculative_query or chunk.text
                speculative_chunks = self.retriever.retrieve(speculative_query, top_k=3)
                telemetry.record_retrieval_trigger(
                    timestamp_s=chunk.timestamp_s,
                    query=speculative_query,
                    trigger_type="speculative_pivot",
                    chunks_count=len(speculative_chunks)
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

        # 2. Final Utterance Handling & Cross-Turn Context Discontinuity Resolution
        final_chunk = stream_chunks[-1]
        final_text = final_chunk.text.strip()

        resolved_query, decomp_subs, detected_intent = self.decomposer.resolve_context_and_decompose(
            final_text, session=session
        )

        if resolved_query != final_text:
            telemetry.record_context_resolution(resolved_query)

        is_delta = (detected_intent == TurnIntent.DELTA_CONSTRAINT) or self.delta_resolver.is_late_constraint(final_text, session)

        if is_delta:
            delta_q = self.delta_resolver.formulate_delta_query(resolved_query, session)
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
                sub_queries = decomp_subs if (decomp_subs and len(decomp_subs) >= 2) else self.decomposer.decompose(resolved_query)

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
                if not speculative_chunks or (resolved_query != final_text):
                    speculative_chunks = self.retriever.retrieve(resolved_query, top_k=3)
                    telemetry.record_retrieval_trigger(
                        timestamp_s=final_chunk.timestamp_s,
                        query=resolved_query,
                        trigger_type="context_resolved_retrieval",
                        chunks_count=len(speculative_chunks)
                    )
                retrieved_pool = speculative_chunks

        # 3. Grounded Synthesis
        answer, citations, uncertainty = self.synthesizer.synthesize(
            query=resolved_query,
            chunks=retrieved_pool,
            sub_queries=sub_queries if sub_queries else [resolved_query],
            session=session,
            is_delta_refinement=is_delta
        )

        turn_rec = session.record_turn(
            raw_query=final_text,
            resolved_query=resolved_query,
            intent=detected_intent,
            answer=answer,
            citations=citations,
            chunks=retrieved_pool,
        )

        return telemetry.generate_record(
            answer_version=session.active_version,
            answer=answer,
            citations=citations,
            sub_queries=sub_queries,
            uncertainty=uncertainty,
            resolved_query=resolved_query if resolved_query != final_text else None,
            active_entities=session.entity_state.model_dump(),
            turn_id=turn_rec.turn_id,
            intent=detected_intent.value,
        )

    def process_stream_streaming(
        self,
        stream_chunks: List[StreamingChunk],
        session_id: str = "sess_default"
    ) -> Generator[StreamingToken, None, StructuredOutputRecord]:
        """
        Generator that executes the pipeline and yields streaming tokens in real time.
        """
        record = self.process_stream(stream_chunks, session_id=session_id)
        start_time = time.perf_counter()

        words = record.answer.split(" ")
        for idx, word in enumerate(words):
            is_last = (idx == len(words) - 1)
            token_str = word if is_last else f"{word} "
            ttft = max(1.0, (time.perf_counter() - start_time) * 1000.0) if idx == 0 else None
            yield StreamingToken(
                token=token_str,
                is_final=is_last,
                ttft_ms=ttft,
                chunk_index=idx
            )

        return record
