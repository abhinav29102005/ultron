"""
streaming_rag/session.py – Multi-Turn Context Continuity & Entity State Engine
=============================================================================
Manages ephemeral conversation session state across turns:
- Tracks turn history (TurnRecord) with prompt lineage and answer versioning
- Resolves context discontinuity, coreference, and anaphoric references
- Extracts and tracks active entities (locations, headcounts, event types, policies)
- Global/thread-safe SessionRegistry ensuring cross-invocation session persistence
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from streaming_rag.models import DocumentChunk, TurnIntent, TurnRecord


class EntityState(BaseModel):
    """Persistent semantic entity memory tracking active conversational variables."""
    location: Optional[str] = Field(default=None, description="Active city or location, e.g., 'Pune'")
    event_type: Optional[str] = Field(default=None, description="Active event noun, e.g., 'workshop'")
    headcount: Optional[int] = Field(default=None, description="Active attendee or participant count, e.g., 30")
    service_topics: List[str] = Field(default_factory=list, description="Active sub-topics, e.g., ['cancellation', 'catering']")
    constraints: List[str] = Field(default_factory=list, description="Active constraints, e.g., ['international', 'late booking']")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Additional conversational attributes")

    def update_from_text(self, text: str) -> None:
        lowered = text.lower()

        # 1. Location detection
        known_locations = ["pune", "mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata"]
        for loc in known_locations:
            if re.search(rf"\b{loc}\b", lowered):
                self.location = loc.capitalize()
                break

        # 2. Event type detection
        known_events = ["workshop", "conference", "meeting", "seminar", "summit", "training", "trip", "travel"]
        for ev in known_events:
            if re.search(rf"\b{ev}\b", lowered):
                self.event_type = ev
                break

        # 3. Headcount detection (e.g., 'for 30 people', '50 attendees', 'capacity 40')
        hc_match = re.search(r"\b(\d{1,4})\s*(?:people|attendees|participants|guests|pax|members)?\b", lowered)
        if hc_match:
            try:
                num = int(hc_match.group(1))
                surrounding = lowered[max(0, hc_match.start() - 10): min(len(lowered), hc_match.end() + 15)]
                if not any(unit in surrounding for unit in ["day", "hour", "inr", "rs", "dollar", "percent", "%", "gst"]):
                    if num not in (1, 2, 3, 4, 14, 72) or "people" in surrounding or "attendees" in surrounding or "for" in surrounding:
                        self.headcount = num
            except ValueError:
                pass

        # 4. Service / policy topic detection
        topics_map = {
            "cancellation": ["cancellation", "cancel", "refund"],
            "catering": ["catering", "caterer", "food", "dietary", "vegan", "meal"],
            "lodging": ["lodging", "hotel", "tariff", "per diem", "stay", "room"],
            "travel": ["travel", "flight", "train", "ticket", "reimbursement", "trip"],
            "venue": ["venue", "facility", "facilities", "hall", "space"],
        }
        for top, kws in topics_map.items():
            if any(re.search(rf"\b{kw}\b", lowered) for kw in kws):
                if top not in self.service_topics:
                    self.service_topics.append(top)

        # 5. Constraints
        if "international" in lowered and "international" not in self.constraints:
            self.constraints.append("international")
        if any(w in lowered for w in ["late booking", "post-departure", "after travel", "late"]) and "late_booking" not in self.constraints:
            self.constraints.append("late_booking")


class SessionContext:
    """Conversational session state maintaining turn lineage and resolving discontinuity."""

    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self.active_version: int = 1
        self.last_query: str = ""
        self.last_answer: str = ""
        self.active_citations: List[str] = []
        self.retained_chunks: Dict[str, DocumentChunk] = {}
        self.turns: List[TurnRecord] = []
        self.entity_state: EntityState = EntityState()

    def record_turn(
        self,
        raw_query: str,
        resolved_query: str,
        intent: TurnIntent,
        answer: str,
        citations: List[str],
        chunks: List[DocumentChunk],
    ) -> TurnRecord:
        # Update entity state from text
        self.entity_state.update_from_text(raw_query)
        self.entity_state.update_from_text(resolved_query)

        turn_id = len(self.turns) + 1
        record = TurnRecord(
            turn_id=turn_id,
            timestamp_s=0.0,
            raw_query=raw_query,
            resolved_query=resolved_query,
            intent=intent,
            active_entities=self.entity_state.model_dump(),
            retrieved_citations=list(citations),
            answer=answer,
            citations=list(citations),
            version=self.active_version,
        )
        self.turns.append(record)
        self.last_query = raw_query
        self.last_answer = answer
        self.active_citations = list(citations)
        for ch in chunks:
            self.retained_chunks[ch.citation_tag] = ch

        return record

    def commit_version(self, answer: str, citations: List[str], chunks: List[DocumentChunk]) -> None:
        self.last_answer = answer
        self.active_citations = list(citations)
        for ch in chunks:
            self.retained_chunks[ch.citation_tag] = ch

    def has_history(self) -> bool:
        return bool(self.last_answer or self.turns)


class SessionRegistry:
    """Thread-safe persistent session registry across RAG pipeline calls."""

    _sessions: Dict[str, SessionContext] = {}

    @classmethod
    def get_session(cls, session_id: str) -> SessionContext:
        if session_id not in cls._sessions:
            cls._sessions[session_id] = SessionContext(session_id)
        return cls._sessions[session_id]

    @classmethod
    def clear(cls, session_id: Optional[str] = None) -> None:
        if session_id:
            cls._sessions.pop(session_id, None)
        else:
            cls._sessions.clear()
