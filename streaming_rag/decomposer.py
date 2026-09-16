"""
streaming_rag/decomposer.py – Component 2: Multi-Intent Decomposer
==================================================================
Isolates orthogonal sub-intents from compound sentences and generates
targeted sub-queries for parallel asynchronous dispatch.
"""

from __future__ import annotations

import re
from typing import List


class MultiIntentDecomposer:
    """Dissects compound utterances into orthogonal sub-queries."""

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

    def decompose(self, utterance: str) -> List[str]:
        """
        Decomposes a compound utterance into discrete sub-queries.
        Example:
        'Pune workshop for 30 people, and I need the cancellation policy and catering options.'
        -> ['Pune workshop venue capacity 30', 'cancellation policy workshop Pune', 'catering service options workshop Pune']
        """
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
        # Check locations or capitalized entities
        proper_nouns = re.findall(r"\b[A-Z][a-z]+\b", text)
        for pn in proper_nouns:
            if pn.lower() not in {"i", "and", "or", "what", "can", "for", "the"}:
                context.append(pn)

        # Check key event nouns
        event_nouns = ["workshop", "conference", "meeting", "flight", "trip", "hotel", "reimbursement", "travel"]
        for noun in event_nouns:
            if re.search(rf"\b{noun}\b", text, re.IGNORECASE) and noun not in context:
                context.append(noun)

        return context[:2]
