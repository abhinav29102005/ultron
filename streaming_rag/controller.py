"""
streaming_rag/controller.py – Component 1: Retrieval Controller
==============================================================
Evaluates streaming transcript chunks in real time:
- Calculates semantic stability and detects sentence completeness
- Detects intra-stream corrections / pivots (invalidating stale speculative retrievals)
- Resolves cross-turn context continuity and boosts stability for grounded follow-ups
- Suppresses retrieval for presentation/formatting queries (Gate 0 Corpus Search)
- Dispatches early speculative retrieval before utterance completion
"""

from __future__ import annotations

import re
from typing import List, Optional
from streaming_rag.models import ControllerAction, ControllerDecision, StreamingChunk
from streaming_rag.session import SessionContext


class PresentationSuppressor:
    """Detects presentation restructuring, formatting, summarization, or translation."""

    PRESENTATION_PATTERNS = [
        r"\b(?:repeat|rephrase|rewrite|format|summarize|shorten|expand|explain)\b.*?\b(?:bullet|table|point|sentence|word|paragraph|tone|simpler)\b",
        r"\b(?:in|into)\s+(?:\d+|two|three|four)\s+bullets?\b",
        r"\b(?:give\s+me|make\s+it)\s+(?:shorter|briefer|concise|bulleted)\b",
        r"\b(?:translate|convert)\s+(?:that|this|the\s+last\s+answer)\b",
        r"\b(?:repeat|reiterate)\s+(?:that|your\s+last\s+answer)\b",
        r"\b(?:just\s+list\s+them)\b",
    ]

    def is_presentation_query(self, text: str) -> bool:
        lowered = text.strip().lower()
        return any(re.search(pattern, lowered) for pattern in self.PRESENTATION_PATTERNS)


class IntentStabilityEvaluator:
    """Evaluates semantic entropy and boundary stabilization of partial transcripts."""

    INCOMPLETE_PREFIXES = {
        "i need to", "i want to", "can you", "could you", "please", "i am looking for",
        "tell me about", "what is", "how do i", "summarize", "find", "where is",
        "i need", "looking to"
    }

    TRAILING_HANGERS = {
        "in", "to", "for", "with", "on", "at", "by", "of", "from", "about", "and", "or", "into"
    }

    STOP_WORDS = {
        "i", "me", "my", "we", "our", "you", "your", "the", "a", "an", "and", "or",
        "to", "in", "for", "with", "on", "at", "by", "of", "from", "up", "about",
        "into", "over", "after", "is", "are", "was", "were", "be", "been", "being"
    }

    PIVOT_TRIGGERS = [
        r"\b(?:wait|actually|scratch that|no\b|instead|rather|make that|change that to)\b",
    ]

    def evaluate_stability(self, text: str, has_prior_context: bool = False) -> float:
        cleaned = re.sub(r"[\.\s,]+$", "", text.strip().lower())
        words = [w for w in re.findall(r"\b\w+\b", cleaned)]
        if not words:
            return 0.0

        # If sentence ends abruptly on a trailing preposition or conjunction, it is semantically incomplete
        if words[-1] in self.TRAILING_HANGERS:
            return 0.20

        # Incomplete opening clause
        if cleaned in self.INCOMPLETE_PREFIXES:
            return 0.10

        # If conversational session exists, short follow-up questions are semantically grounded
        if has_prior_context and len(words) >= 3:
            if any(cleaned.startswith(p) for p in ["what if", "what about", "how about", "can", "could", "is", "are", "how much"]):
                return 0.85
            if any(w in cleaned for w in ["people", "attendees", "international", "mumbai", "delhi", "tariff", "rate", "hotel"]):
                return 0.85

        # Extract content words
        content_words = [w for w in words if w not in self.STOP_WORDS]
        if len(content_words) < 2:
            return 0.25

        # Check if the thought has a grounded entity/noun and context
        has_entities_or_numbers = bool(re.search(
            r"\d+|[a-z]+nagar|[a-z]+pur|pune|mumbai|delhi|bangalore|workshop|travel|booking|hotel|tariff|cancellation|catering",
            cleaned
        ))
        if len(content_words) >= 3 or (len(content_words) >= 2 and has_entities_or_numbers):
            return 0.85

        return 0.60


class RetrievalController:
    """Component 1 Orchestrator implementing the Speculative Decision Matrix."""

    def __init__(self, stability_threshold: float = 0.70):
        self.stability_threshold = stability_threshold
        self.stability_evaluator = IntentStabilityEvaluator()
        self.presentation_suppressor = PresentationSuppressor()
        self._retrieval_triggered = False
        self._speculative_query: Optional[str] = None

    def reset(self) -> None:
        self._retrieval_triggered = False
        self._speculative_query = None

    def is_valid_compound(self, text: str) -> bool:
        """Returns True only when clauses on BOTH sides of conjunction have complete content."""
        parts = re.split(r"\b(?:and\s+also|as\s+well\s+as|plus|and)\b", text, flags=re.IGNORECASE)
        if len(parts) >= 2:
            words_after = [
                w for w in re.findall(r"\b\w+\b", parts[-1].lower())
                if w not in self.stability_evaluator.STOP_WORDS
            ]
            return len(words_after) >= 2
        return False

    def detect_intra_stream_pivot(self, text: str) -> Optional[str]:
        """Detects mid-utterance topic pivots or self-corrections."""
        lowered = text.lower()
        for pat in self.stability_evaluator.PIVOT_TRIGGERS:
            match = re.search(pat, lowered)
            if match:
                pivot_clause = text[match.end():].strip()
                if len(pivot_clause.split()) >= 2:
                    return pivot_clause
        if self._speculative_query:
            spec_lower = self._speculative_query.lower()
            for city in ["mumbai", "delhi", "bangalore", "pune"]:
                if city in lowered and city not in spec_lower:
                    return text
        return None

    def evaluate_chunk(
        self,
        chunk: StreamingChunk,
        session: Optional[SessionContext] = None,
        has_session_context: Optional[bool] = None
    ) -> ControllerDecision:
        text = chunk.text.strip()
        has_history = (session.has_history() if session else False) or bool(has_session_context)

        # 1. Check for presentation query suppression (Gate 0 Corpus Search)
        if has_history and self.presentation_suppressor.is_presentation_query(text):
            return ControllerDecision(
                action=ControllerAction.NO_RETRIEVAL_SUPPRESS,
                reason="presentation_restructure_suppress",
                confidence=0.98,
            )

        # 2. Check for intra-stream pivot / self-correction (invalidating previous speculation)
        if self._retrieval_triggered and not chunk.is_final:
            pivot_clause = self.detect_intra_stream_pivot(text)
            if pivot_clause:
                new_speculative_q = self._extract_speculative_query(pivot_clause, session)
                self._speculative_query = new_speculative_q
                return ControllerDecision(
                    action=ControllerAction.SPECULATIVE_PIVOT,
                    reason="intra_stream_intent_pivot",
                    confidence=0.95,
                    speculative_query=new_speculative_q,
                )

        # 3. Check for multi-intent compound markers with complete secondary clause
        if self.is_valid_compound(text):
            return ControllerDecision(
                action=ControllerAction.DECOMPOSE_AND_PARALLEL_RETRIEVE,
                reason="multi_intent_compound_detected",
                confidence=0.92,
            )

        # 4. If already triggered early, wait for completion unless pivot was detected
        if self._retrieval_triggered and not chunk.is_final:
            return ControllerDecision(
                action=ControllerAction.WAIT,
                reason="retrieval_already_dispatched_awaiting_final_transcript",
                confidence=0.90,
            )

        # 5. Evaluate semantic stability for early retrieval
        stability = self.stability_evaluator.evaluate_stability(text, has_prior_context=has_history)

        if stability >= self.stability_threshold:
            self._retrieval_triggered = True
            speculative_q = self._extract_speculative_query(text, session)
            self._speculative_query = speculative_q
            return ControllerDecision(
                action=ControllerAction.RETRIEVE_EARLY,
                reason=f"intent_semantically_stable (score={stability:.2f})",
                confidence=stability,
                speculative_query=speculative_q,
            )

        return ControllerDecision(
            action=ControllerAction.WAIT,
            reason=f"intent_unstable_or_incomplete (score={stability:.2f})",
            confidence=1.0 - stability,
        )

    def _extract_speculative_query(self, text: str, session: Optional[SessionContext] = None) -> str:
        cleaned = re.sub(r",?\s*\b(?:and\s+i\s+need|and\s+the|and|plus|also)\b.*$", "", text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(?:\.\.\.|i need to plan|i need|i want to|can you|could you|please|find)\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(?:wait|actually|scratch that|no|instead|rather)[,\s]*", "", cleaned, flags=re.IGNORECASE).strip()

        if "pune" in text.lower() and "pune" not in cleaned.lower():
            cleaned = f"{cleaned} Pune"

        if session and session.entity_state.location and session.entity_state.location.lower() not in cleaned.lower():
            if any(w in cleaned.lower() for w in ["hotel", "venue", "people", "attendees", "tariff", "stay"]):
                cleaned = f"{cleaned} {session.entity_state.location}"

        return cleaned if cleaned else text
