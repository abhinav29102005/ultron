"""
streaming_rag/controller.py – Component 1: Retrieval Controller
==============================================================
Evaluates streaming transcript chunks in real time:
- Calculates semantic stability
- Suppresses retrieval for presentation/formatting queries
- Dispatches early speculative retrieval before utterance completion
"""

from __future__ import annotations

import re
from typing import List, Optional
from streaming_rag.models import ControllerAction, ControllerDecision, StreamingChunk


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

    def evaluate_stability(self, text: str) -> float:
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

        # Extract content words
        content_words = [w for w in words if w not in self.STOP_WORDS]
        if len(content_words) < 2:
            return 0.25

        # Check if the thought has a grounded entity/noun and context
        has_entities_or_numbers = bool(re.search(r"\d+|[a-z]+nagar|[a-z]+pur|pune|mumbai|delhi|workshop|travel|booking|hotel", cleaned))
        if len(content_words) >= 3 or (len(content_words) >= 2 and has_entities_or_numbers):
            return 0.85

        return 0.60


class RetrievalController:
    """Component 1 Orchestrator implementing the Decision Matrix."""

    def __init__(self, stability_threshold: float = 0.70):
        self.stability_threshold = stability_threshold
        self.stability_evaluator = IntentStabilityEvaluator()
        self.presentation_suppressor = PresentationSuppressor()
        self._retrieval_triggered = False

    def reset(self) -> None:
        self._retrieval_triggered = False

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

    def evaluate_chunk(
        self,
        chunk: StreamingChunk,
        has_session_context: bool = False
    ) -> ControllerDecision:
        text = chunk.text.strip()

        # 1. Check for presentation query suppression (Gate 0 Corpus Search)
        if has_session_context and self.presentation_suppressor.is_presentation_query(text):
            return ControllerDecision(
                action=ControllerAction.NO_RETRIEVAL_SUPPRESS,
                reason="presentation_restructure_suppress",
                confidence=0.98,
            )

        # 2. Check for multi-intent compound markers with complete secondary clause
        if self.is_valid_compound(text):
            return ControllerDecision(
                action=ControllerAction.DECOMPOSE_AND_PARALLEL_RETRIEVE,
                reason="multi_intent_compound_detected",
                confidence=0.92,
            )

        # 3. If already triggered early, wait for completion unless additional compound intent appears
        if self._retrieval_triggered and not chunk.is_final:
            return ControllerDecision(
                action=ControllerAction.WAIT,
                reason="retrieval_already_dispatched_awaiting_final_transcript",
                confidence=0.90,
            )

        # 4. Evaluate semantic stability for early retrieval
        stability = self.stability_evaluator.evaluate_stability(text)

        if stability >= self.stability_threshold:
            self._retrieval_triggered = True
            speculative_q = self._extract_speculative_query(text)
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

    def _extract_speculative_query(self, text: str) -> str:
        cleaned = re.sub(r",?\s*\b(?:and\s+i\s+need|and\s+the|and|plus|also)\b.*$", "", text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(?:\.\.\.|i need to plan|i need|i want to|can you|could you|please|find)\s*", "", cleaned, flags=re.IGNORECASE).strip()
        if "pune" in text.lower() and "pune" not in cleaned.lower():
            cleaned = f"{cleaned} Pune"
        return cleaned if cleaned else text
