"""
streaming_rag/models.py – Core Data Schemas for Streaming Live RAG
==================================================================
Defines rigid JSON schemas and Pydantic models for controller decisions,
streaming events, retrieved document chunks, answer versions, multi-turn
conversational turns, token streams, and telemetry.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ControllerAction(str, Enum):
    WAIT = "WAIT"
    RETRIEVE_EARLY = "RETRIEVE_EARLY"
    DECOMPOSE_AND_PARALLEL_RETRIEVE = "DECOMPOSE_AND_PARALLEL_RETRIEVE"
    NO_RETRIEVAL_SUPPRESS = "NO_RETRIEVAL_SUPPRESS"
    SPECULATIVE_PIVOT = "SPECULATIVE_PIVOT"


class TurnIntent(str, Enum):
    NEW_QUERY = "NEW_QUERY"
    ANAPHORIC_FOLLOW_UP = "ANAPHORIC_FOLLOW_UP"
    DELTA_CONSTRAINT = "DELTA_CONSTRAINT"
    PRESENTATION_RESTRUCTURE = "PRESENTATION_RESTRUCTURE"
    INTRA_STREAM_CORRECTION = "INTRA_STREAM_CORRECTION"


class StreamingChunk(BaseModel):
    timestamp_s: float = Field(..., description="Timestamp of the chunk relative to utterance start")
    text: str = Field(..., description="Cumulative or incremental transcript text")
    is_final: bool = Field(default=False, description="True if this is the final utterance chunk")


class StreamingToken(BaseModel):
    token: str = Field(..., description="Generated token or text fragment")
    is_final: bool = Field(default=False, description="True if this is the end of generation")
    ttft_ms: Optional[float] = Field(default=None, description="Time to first token in milliseconds")
    chunk_index: int = Field(default=0, description="Sequential token index")


class ControllerDecision(BaseModel):
    action: ControllerAction = Field(..., description="Selected controller action")
    reason: str = Field(..., description="Deterministic rationale or classifier trigger")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    speculative_query: Optional[str] = Field(default=None, description="Early query if action is RETRIEVE_EARLY or SPECULATIVE_PIVOT")
    sub_queries: List[str] = Field(default_factory=list, description="Sub-queries if action is DECOMPOSE")


class DocumentChunk(BaseModel):
    doc_id: str = Field(..., description="Unique Document Identifier, e.g., 'Doc_12'")
    section: str = Field(..., description="Section identifier, e.g., '§2'")
    title: str = Field(default="", description="Document title")
    text: str = Field(..., description="Factual text content")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def citation_tag(self) -> str:
        sec = self.section if self.section.startswith("§") else f"§{self.section}"
        return f"{self.doc_id} {sec}"


class RetrievalEvent(BaseModel):
    timestamp_s: float
    query: str
    trigger: str = Field(..., description="Trigger type, e.g., 'speculative_early', 'speculative_pivot', 'multi_intent', 'delta_query'")
    chunks_retrieved: int = Field(default=0)


class TurnRecord(BaseModel):
    turn_id: int = Field(..., description="Turn sequence index in session")
    timestamp_s: float = Field(default=0.0)
    raw_query: str = Field(..., description="Original user utterance")
    resolved_query: str = Field(..., description="Canonical query with resolved cross-turn context and anaphora")
    intent: TurnIntent = Field(default=TurnIntent.NEW_QUERY)
    active_entities: Dict[str, Any] = Field(default_factory=dict)
    retrieved_citations: List[str] = Field(default_factory=list)
    answer: str = Field(..., description="Grounded synthesized response")
    citations: List[str] = Field(default_factory=list)
    version: int = Field(default=1)


class TelemetryLog(BaseModel):
    stream_duration_s: float = Field(..., description="Total time from utterance start to finish")
    retrieval_trigger_timestamp_s: float = Field(..., description="Timestamp of first early retrieval commenced")
    early_retrieval_gain_ms: float = Field(..., description="(t_final - t_trigger) * 1000 in ms")
    total_latency_ms: float = Field(..., description="End-to-end latency from start to synthesis completion")
    ttft_ms: Optional[float] = Field(default=None, description="Time to first token in ms")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    context_discontinuity_resolved: bool = Field(default=False, description="True if cross-turn anaphora/context was resolved")
    resolved_query: Optional[str] = Field(default=None, description="Rewritten canonical query with resolved entities")


class StructuredOutputRecord(BaseModel):
    session_id: str = Field(..., description="Unique ephemeral session identifier")
    turn_id: int = Field(default=1, description="Index of this conversational turn")
    answer_version: int = Field(default=1, description="Version index, e.g., 1 -> 2 upon late-arriving detail refinement")
    intent: Optional[str] = Field(default=None, description="Identified turn intent type")
    telemetry: TelemetryLog
    retrieval_events: List[RetrievalEvent] = Field(default_factory=list)
    sub_queries: List[str] = Field(default_factory=list)
    resolved_query: Optional[str] = Field(default=None, description="Rewritten canonical query with resolved context")
    active_entities: Dict[str, Any] = Field(default_factory=dict, description="Active entity memory across turns")
    answer: str = Field(..., description="Grounded response text with exact section citations")
    citations: List[str] = Field(default_factory=list, description="List of cited tags, e.g. ['Doc_12 §2']")
    uncertainty: Optional[str] = Field(default=None, description="Explicit uncertainty note if aspects are missing")
