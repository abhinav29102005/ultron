"""
streaming_rag/decomposer.py – Component 2: Multi-Intent Decomposer & Context Discontinuity Engine
=============================================================================================
Isolates orthogonal sub-intents from compound sentences and generates targeted sub-queries.
Resolves cross-turn context discontinuity, anaphoric references, and conversational ellipses.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from streaming_rag.models import TurnIntent
from streaming_rag.session import SessionContext


class MultiIntentDecomposer:
    """Dissects compound utterances and bridges cross-turn context discontinuity."""

    SPLIT_PATTERNS = [
        r"\band\s+also\b",
        r"\bas\s+well\s+as\b",
        r"\bplus\b",
        r"\balong\s+with\b",
        r"\band\s+(?:i\s+need|i\s+want|what\s+about|check)\b",
        r"\band\s+the\b",
        r"\band\b",
        r";",
    ]

    CONVERSATIONAL_FILLERS = [
        r"^(?:i need to plan|i need|i want to|can you tell me|can you check|please find)\s+",
        r"^(?:also|and|plus)\s+",
    ]

    PRONOUNS_OR_DEICTIC = [
        r"\bthere\b",
        r"\bit\b",
        r"\bthat\b",
        r"\bthose\b",
        r"\bthis\b",
    ]

    FOLLOW_UP_TRIGGERS = [
        r"\b(?:actually|wait|by\s+the\s+way|in\s+addition|furthermore)\b",
        r"\b(?:the\s+trip\s+was|the\s+booking\s+was|it\s+was|this\s+is)\b",
        r"\b(?:what\s+if|except\s+that|note\s+that)\b",
    ]

    PRESENTATION_PATTERNS = [
        r"\b(?:repeat|rephrase|rewrite|format|summarize|shorten|expand|explain)\b.*?\b(?:bullet|table|point|sentence|word|paragraph|tone|simpler)\b",
        r"\b(?:in|into)\s+(?:\d+|two|three|four)\s+bullets?\b",
        r"\b(?:give\s+me|make\s+it)\s+(?:shorter|briefer|concise|bulleted)\b",
        r"\b(?:translate|convert)\s+(?:that|this|the\s+last\s+answer)\b",
        r"\b(?:repeat|reiterate)\s+(?:that|your\s+last\s+answer)\b",
        r"\b(?:just\s+list\s+them)\b",
    ]

    def resolve_context_and_decompose(
        self,
        utterance: str,
        session: Optional[SessionContext] = None
    ) -> Tuple[str, List[str], TurnIntent]:
        """
        Resolves context discontinuity across turns and decomposes multi-intent compounds.
        Returns: (resolved_canonical_query, sub_queries, turn_intent)
        """
        raw_text = utterance.strip()
        lowered = raw_text.lower()

        # 1. Determine TurnIntent
        intent = TurnIntent.NEW_QUERY
        resolved_text = raw_text

        has_history = session.has_history() if session else False

        if has_history:
            # Check for presentation query
            if any(re.search(pat, lowered) for pat in self.PRESENTATION_PATTERNS):
                intent = TurnIntent.PRESENTATION_RESTRUCTURE
                return raw_text, [raw_text], intent

            # Check for delta constraint (e.g., travel international / late booking)
            if any(re.search(pat, lowered) for pat in self.FOLLOW_UP_TRIGGERS) or (
                len(lowered.split()) <= 12 and not lowered.startswith(("what", "who", "where", "how", "can"))
                and any(w in lowered for w in ["international", "late", "after", "waiver", "vegan"])
            ):
                intent = TurnIntent.DELTA_CONSTRAINT
            # Check for anaphoric or elliptical follow-up
            elif any(re.search(p, lowered) for p in self.PRONOUNS_OR_DEICTIC) or lowered.startswith(("what if", "what about", "can", "how about", "is", "are")):
                intent = TurnIntent.ANAPHORIC_FOLLOW_UP

        # 2. Context Discontinuity Resolution (Coreference & Ellipsis Bridging)
        if session and has_history and intent in (TurnIntent.ANAPHORIC_FOLLOW_UP, TurnIntent.DELTA_CONSTRAINT):
            ent = session.entity_state
            loc = ent.location or "Pune"
            ev = ent.event_type or "workshop"

            # Check for attendee/headcount change (e.g., 'What if for 50 people?' / 'Can 50 people fit?')
            hc_match = re.search(r"\b(\d{1,4})\s*(?:people|attendees|participants|guests)?\b", lowered)
            if hc_match and any(w in lowered for w in ["people", "attendees", "participants", "for", "fit", "capacity"]):
                count = hc_match.group(1)
                resolved_text = f"{loc} {ev} venue capacity for {count} attendees"
            # Check for lodging/hotel inquiry (e.g., 'What about hotel rates there?')
            elif any(w in lowered for w in ["hotel", "lodging", "tariff", "stay", "per diem"]):
                resolved_text = f"Hotel lodging caps and per diem limits in {loc} Tier-1"
            # Check for deictic 'there'
            elif "there" in lowered:
                resolved_text = re.sub(r"\bthere\b", f"in {loc}", raw_text, flags=re.IGNORECASE)
            # Check for delta constraint
            elif intent == TurnIntent.DELTA_CONSTRAINT:
                clean_delta = re.sub(r"^(?:actually|wait|by the way|note that)[,\s]*", "", raw_text, flags=re.IGNORECASE).strip()
                resolved_text = f"{clean_delta} policy exception rule"
            else:
                if loc.lower() not in lowered:
                    resolved_text = f"{raw_text} {loc} {ev}"

        # 3. Multi-intent decomposition on the resolved query
        sub_queries = self.decompose(resolved_text)

        return resolved_text, sub_queries, intent

    def decompose(self, utterance: str) -> List[str]:
        """Decomposes a compound utterance into discrete sub-queries."""
        text = utterance.strip()
        # Clean opening fillers
        for filler in self.CONVERSATIONAL_FILLERS:
            text = re.sub(filler, "", text, flags=re.IGNORECASE).strip()

        # Identify shared context (e.g. Location 'Pune', Event 'workshop')
        context_keywords = self._extract_context(text)

        # Split into raw segments
        segments = [text]
        for pattern in self.SPLIT_PATTERNS:
            new_segments = []
            for seg in segments:
                parts = re.split(pattern, seg, flags=re.IGNORECASE)
                new_segments.extend([p.strip() for p in parts if p.strip()])
            segments = new_segments

        # Filter and augment segments with shared context
        sub_queries = []
        for seg in segments:
            # Remove trailing commas and fillers
            cleaned_seg = re.sub(r"^[,\s]+|[,\s]+$", "", seg)
            cleaned_seg = re.sub(r"^(?:the\s+|and\s+|also\s+)", "", cleaned_seg, flags=re.IGNORECASE).strip()
            if not cleaned_seg or len(cleaned_seg.split()) < 1:
                continue

            # If segment lacks context keyword, enrich it
            enriched = cleaned_seg
            if context_keywords:
                missing_ctx = [kw for kw in context_keywords if kw.lower() not in enriched.lower()]
                if missing_ctx:
                    enriched = f"{enriched} {' '.join(missing_ctx)}"

            sub_queries.append(enriched.strip())

        # If decomposition failed to produce >= 2 sub-queries, return original query
        if len(sub_queries) <= 1:
            return [utterance.strip()]

        return sub_queries

    def _extract_context(self, text: str) -> List[str]:
        """Identifies key contextual anchors (locations, topics, numbers) to bind sub-queries."""
        context = []
        proper_nouns = re.findall(r"\b[A-Z][a-z]+\b", text)
        for pn in proper_nouns:
            if pn.lower() not in {"i", "and", "or", "what", "can", "for", "the"}:
                context.append(pn)

        event_nouns = ["workshop", "conference", "meeting", "flight", "trip", "hotel", "reimbursement", "travel"]
        for noun in event_nouns:
            if re.search(rf"\b{noun}\b", text, re.IGNORECASE) and noun not in context:
                context.append(noun)

        return context[:2]
