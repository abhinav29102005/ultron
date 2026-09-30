"""
streaming_rag – Samsung Theme 4: Streaming Live RAG Package
===========================================================
High-performance streaming retrieval-augmented generation engine:
- Continuous conversational session state & context discontinuity engine
- Speculative early retrieval triggering with intra-stream pivot invalidation
- Multi-intent compound decomposition & coreference resolution
- Grounded synthesis with strict section citations [Doc_XX §YY]
- Ephemeral session refinement via delta queries (Version 1 -> Version 2 -> Version 3)
- Zero-retrieval presentation suppression
- Streaming token generator with TTFT observability
"""

from streaming_rag.models import (
    ControllerAction,
    ControllerDecision,
    DocumentChunk,
    RetrievalEvent,
    StreamingChunk,
    StreamingToken,
    StructuredOutputRecord,
    TelemetryLog,
    TurnIntent,
    TurnRecord,
)
from streaming_rag.session import EntityState, SessionContext, SessionRegistry
from streaming_rag.pipeline import StreamingLiveRAG
from streaming_rag.corpus import SAMPLE_CORPUS

__all__ = [
    "StreamingLiveRAG",
    "ControllerAction",
    "ControllerDecision",
    "DocumentChunk",
    "RetrievalEvent",
    "StreamingChunk",
    "StreamingToken",
    "StructuredOutputRecord",
    "TelemetryLog",
    "TurnIntent",
    "TurnRecord",
    "EntityState",
    "SessionContext",
    "SessionRegistry",
    "SAMPLE_CORPUS",
]
