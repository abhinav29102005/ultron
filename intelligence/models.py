"""
intelligence/models.py
======================

Pydantic schemas for structured events and telemetry used across the
streaming RAG pipeline. These models are independent of the EventBus
dataclasses and used for JSON tracing and telemetry export.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime


class DocChunk(BaseModel):
    title: Optional[str]
    url: Optional[str]
    snippet: Optional[str]
    content: Optional[str]
    source: Optional[str]
    doc_id: Optional[str] = None
    section: Optional[str] = None


class RetrievalResultModel(BaseModel):
    session_id: Optional[str]
    turn_id: Optional[int]
    query: str
    decision: str
    timestamp: datetime
    results: List[DocChunk] = Field(default_factory=list)


class SynthesizerResultModel(BaseModel):
    session_id: Optional[str]
    turn_id: Optional[int]
    answer_version: int
    answer: str
    citations: List[str] = Field(default_factory=list)
    uncertainty: Optional[str] = None
    timestamp: datetime


class TelemetryEntry(BaseModel):
    session_id: Optional[str]
    turn_id: Optional[int]
    event_name: str
    timestamp: datetime
    payload: Optional[Any]


class TelemetryTrace(BaseModel):
    session_id: Optional[str]
    trace_id: Optional[str]
    created_at: datetime
    stream_duration_s: Optional[float] = None
    retrieval_trigger_timestamp_s: Optional[float] = None
    early_retrieval_gain_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    events: List[TelemetryEntry] = Field(default_factory=list)
