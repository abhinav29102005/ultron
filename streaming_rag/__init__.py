"""
streaming_rag – Samsung Theme 4: Streaming Live RAG Package
===========================================================
High-performance streaming retrieval-augmented generation engine:
- Speculative early retrieval triggering
- Multi-intent compound decomposition
- Grounded synthesis with strict section citations [Doc_XX §YY]
- Ephemeral session refinement via delta queries (Version 1 -> Version 2)
- Zero-retrieval presentation suppression
"""

from streaming_rag.models import (
    ControllerAction,
    ControllerDecision,
    DocumentChunk,
    RetrievalEvent,
    StreamingChunk,
    StructuredOutputRecord,
    TelemetryLog,
)
from streaming_rag.pipeline import StreamingLiveRAG
from streaming_rag.corpus import SAMPLE_CORPUS

__all__ = [
    "StreamingLiveRAG",
    "ControllerAction",
    "ControllerDecision",
    "DocumentChunk",
    "RetrievalEvent",
    "StreamingChunk",
    "StructuredOutputRecord",
    "TelemetryLog",
    "SAMPLE_CORPUS",
]
