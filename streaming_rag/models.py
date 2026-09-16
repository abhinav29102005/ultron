"""
streaming_rag/models.py – Core Data Schemas for Streaming Live RAG
==================================================================
Defines rigid JSON schemas and Pydantic models for controller decisions,
streaming events, retrieved document chunks, answer versions, and telemetry.
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


class StreamingChunk(BaseModel):
    timestamp_s: float = Field(..., description="Timestamp of the chunk relative to utterance start")
    text: str = Field(..., description="Cumulative or incremental transcript text")
    is_final: bool = Field(default=False, description="True if this is the final utterance chunk")


class ControllerDecision(BaseModel):
    action: ControllerAction = Field(..., description="Selected controller action")
    reason: str = Field(..., description="Deterministic rationale or classifier trigger")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    speculative_query: Optional[str] = Field(default=None, description="Early query if action is RETRIEVE_EARLY")
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
    trigger: str = Field(..., description="Trigger type, e.g., 'speculative_early', 'multi_intent', 'delta_query'")
    chunks_retrieved: int = Field(default=0)


class TelemetryLog(BaseModel):
    stream_duration_s: float = Field(..., description="Total time from utterance start to finish")
    retrieval_trigger_timestamp_s: float = Field(..., description="Timestamp of first early retrieval commenced")
    early_retrieval_gain_ms: float = Field(..., description="(t_final - t_trigger) * 1000 in ms")
    total_latency_ms: float = Field(..., description="End-to-end latency from start to synthesis completion")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)


class StructuredOutputRecord(BaseModel):
    session_id: str = Field(..., description="Unique ephemeral session identifier")
    answer_version: int = Field(default=1, description="Version index, e.g., 1 -> 2 upon late-arriving detail refinement")
    telemetry: TelemetryLog
    retrieval_events: List[RetrievalEvent] = Field(default_factory=list)
    sub_queries: List[str] = Field(default_factory=list)
    answer: str = Field(..., description="Grounded response text with exact section citations")
    citations: List[str] = Field(default_factory=list, description="List of cited tags, e.g. ['Doc_12 §2']")
    uncertainty: Optional[str] = Field(default=None, description="Explicit uncertainty note if aspects are missing")
