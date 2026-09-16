"""
streaming_rag/synthesizer.py – Component 4: Session-Aware Synthesizer & Refinement
==================================================================================
Produces grounded responses backed strictly by retrieved document chunks.
- Manages answer version lineage (Version 1 -> Version 2)
- Handles late-arriving constraints via delta queries without restarting
- Guarantees zero parametric hallucination with exact [Doc_XX §YY] citations
- Emits explicit uncertainty when required aspects are missing from corpus
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple
from streaming_rag.models import DocumentChunk, StructuredOutputRecord, TelemetryLog


class SessionContext:
    """Ephemeral session storage scoped strictly to the active conversation."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.active_version = 1
        self.last_query = ""
        self.last_answer = ""
        self.active_citations: List[str] = []
        self.retained_chunks: Dict[str, DocumentChunk] = {}
        self.version_history: List[Dict[str, Any]] = []

    def commit_version(self, answer: str, citations: List[str], chunks: List[DocumentChunk]) -> None:
        self.version_history.append({
            "version": self.active_version,
            "answer": answer,
            "citations": list(citations),
        })
        self.last_answer = answer
        self.active_citations = list(citations)
        for ch in chunks:
            self.retained_chunks[ch.citation_tag] = ch


class DeltaConstraintResolver:
    """Identifies delta constraints in follow-up turns without wiping prior base context."""

    FOLLOW_UP_TRIGGERS = [
        r"\b(?:actually|wait|by\s+the\s+way|in\s+addition|furthermore)\b",
        r"\b(?:the\s+trip\s+was|the\s+booking\s+was|it\s+was|this\s+is)\b",
        r"\b(?:what\s+if|except\s+that|note\s+that)\b",
    ]

    def is_late_constraint(self, text: str, session: Optional[SessionContext]) -> bool:
        if not session or not session.last_answer:
            return False
        lowered = text.strip().lower()
        if any(re.search(pat, lowered) for pat in self.FOLLOW_UP_TRIGGERS):
            return True
        # If short sentence adding a constraint (e.g. "International travel and late booking")
        return len(lowered.split()) <= 12 and not lowered.startswith(("what", "who", "where", "how"))

    def formulate_delta_query(self, text: str, session: SessionContext) -> str:
        """Extracts the delta constraint to query only newly added requirements."""
        # Strip follow-up conversational prefixes
        cleaned = re.sub(r"^(?:actually|wait|by the way|note that)[,\s]*", "", text, flags=re.IGNORECASE).strip()
        return f"{cleaned} policy exception rule"


class GroundedSynthesizer:
    """Grounded synthesis engine enforcing exact citations and zero hallucination."""

    def synthesize(
        self,
        query: str,
        chunks: List[DocumentChunk],
        sub_queries: List[str],
        session: SessionContext,
        is_delta_refinement: bool = False
    ) -> Tuple[str, List[str], Optional[str]]:
        """
        Synthesizes grounded text citing [Doc_XX §YY].
        Returns (answer, citations, uncertainty).
        """
        if not chunks:
            return (
                "The provided corpus does not contain documented guidelines covering this request.",
                [],
                "No supporting documentation located in retrieved corpus."
            )

        citations_used: List[str] = []
        answer_parts: List[str] = []
        unverified_topics: List[str] = []

        stopwords = {"the", "a", "an", "is", "are", "was", "were", "for", "to", "in", "on", "at", "of", "and", "or", "what", "how", "who", "with", "it", "this", "that", "i", "need", "plan"}
        # Analyze sub-queries against available evidence chunks using scored alignment
        for sq in sub_queries:
            sq_terms = set(re.findall(r"\b\w+\b", sq.lower())) - stopwords
            best_chunk = None
            best_score = 0

            for ch in chunks:
                ch_terms = set(re.findall(r"\b\w+\b", f"{ch.title} {ch.text}".lower())) - stopwords
                overlap = sq_terms.intersection(ch_terms)
                score = len(overlap)
                if any(w in overlap for w in ["cancellation", "refund", "catering", "caterer", "venue", "attendees", "trains", "flights", "international", "waiver"]):
                    score += 3
                if score > best_score:
                    best_score = score
                    best_chunk = ch

            if best_chunk and best_score >= 1:
                tag = best_chunk.citation_tag
                if tag not in citations_used:
                    citations_used.append(tag)
                sentences = re.split(r"(?<=[.!?])\s+", best_chunk.text.strip())
                core_sentence = sentences[0] if sentences else best_chunk.text.strip()
                ans_snippet = f"{core_sentence} [{tag}]"
                if ans_snippet not in answer_parts:
                    answer_parts.append(ans_snippet)
            else:
                unverified_topics.append(sq)

        # Build unified answer
        if is_delta_refinement and session.last_answer:
            # Preserve base answer, increment version, append delta assertions
            session.active_version += 1
            all_citations = list(dict.fromkeys(session.active_citations + citations_used))
            delta_answer = " ".join(answer_parts)
            full_answer = f"{session.last_answer} Additionally, for the updated constraints: {delta_answer}"
            citations_used = all_citations
        else:
            if not answer_parts:
                # Fallback to top chunk
                top_ch = chunks[0]
                citations_used.append(top_ch.citation_tag)
                full_answer = f"{top_ch.text.strip()} [{top_ch.citation_tag}]"
            else:
                full_answer = " ".join(answer_parts)

        # Flag uncertainty if any sub-intent had no supporting chunk in corpus
        uncertainty = None
        if unverified_topics:
            topics_str = ", ".join([f"'{t}'" for t in unverified_topics[:2]])
            uncertainty = f"Policies or options for {topics_str} could not be verified from the retrieved corpus."

        session.commit_version(full_answer, citations_used, chunks)
        return full_answer, citations_used, uncertainty

    def reformat_presentation(self, instruction: str, session: SessionContext) -> str:
        """
        Reformats existing session answer without running any corpus retrieval.
        Preserves original citations strictly.
        """
        if not session.last_answer:
            return "No prior answer exists in session to format."

        # Extract sentences from prior answer
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", session.last_answer) if s.strip()]

        if "bullet" in instruction.lower():
            bullets = [f"• {s}" for s in sentences[:3]]
            return "\n".join(bullets)

        if "short" in instruction.lower() or "concise" in instruction.lower():
            return sentences[0] if sentences else session.last_answer

        return session.last_answer
