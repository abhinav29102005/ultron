"""
intelligence/reranker.py
========================

Cross-encoder style reranker. Primary mode: OpenAI chat-based pairwise scoring
that returns a relevance score in [0,1]. If OpenAI is not configured the
module falls back to a cheap lexical overlap scorer so the pipeline remains
usable without API keys (you said you'll add keys later).
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging
import asyncio
import math

logger = logging.getLogger("reranker")


class RerankerUnavailable(Exception):
    pass


class CrossEncoderReranker:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo") -> None:
        self.api_key = api_key
        self.model = model
        if api_key is None:
            logger.info("No OpenAI API key configured; reranker will use lexical fallback")

    async def _openai_score(self, query: str, doc_text: str) -> float:
        try:
            import openai
        except Exception:
            raise RerankerUnavailable("openai package not available")

        if self.api_key:
            openai.api_key = self.api_key

        prompt = (
            f"Rate how relevant the following document is to the query on a scale 0-1. "
            f"Return only a JSON object: {{\"score\": <float between 0 and 1>}}.\n\n"
            f"Query:\n{query}\n\nDocument:\n{doc_text}\n"
        )

        def _call():
            # Use ChatCompletion synchronously in a thread.
            resp = openai.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=20,
            )
            txt = resp["choices"][0]["message"]["content"].strip()
            # Extract a float by scanning for digits/decimal
            import re

            m = re.search(r"([-+]?[0-9]*\.?[0-9]+)", txt)
            if not m:
                raise ValueError(f"Could not parse score from model output: {txt}")
            val = float(m.group(1))
            # Clamp to 0..1
            return max(0.0, min(1.0, val))

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            logger.exception("OpenAI reranker call failed; falling back to lexical score")
            raise

    def _lexical_score(self, query: str, doc_text: str) -> float:
        q_tokens = set(x.lower() for x in query.split())
        d_tokens = set(x.lower() for x in doc_text.split())
        if not q_tokens or not d_tokens:
            return 0.0
        overlap = q_tokens.intersection(d_tokens)
        score = len(overlap) / max(1, len(q_tokens))
        # dampen with log of doc length to prefer concise matches
        length_factor = 1.0 / (1.0 + math.log1p(len(doc_text.split())))
        return float(max(0.0, min(1.0, score * length_factor)))

    async def rerank(self, query: str, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return docs annotated with a `score` key and sorted descending."""
        out = []
        for d in docs:
            txt = (d.get("title", "") + "\n" + d.get("snippet", "") + "\n" + d.get("content", "")).strip()
            score = 0.0
            # Try OpenAI when API key present
            if self.api_key is not None:
                try:
                    score = await self._openai_score(query, txt)
                except Exception:
                    score = self._lexical_score(query, txt)
            else:
                score = self._lexical_score(query, txt)

            nd = dict(d)
            nd["score"] = score
            out.append(nd)

        out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return out
