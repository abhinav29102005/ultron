"""
intelligence/embeddings.py
==========================

Simple embeddings provider wrapper. Currently implements an OpenAI-backed
provider; it exposes an async `embed_texts(texts: list[str]) -> list[list[float]]`.
The implementation is defensive: if OpenAI is not configured the provider
raises an informative error.
"""
from __future__ import annotations

from typing import List, Optional
import logging
import asyncio

logger = logging.getLogger("embeddings")


class EmbeddingsUnavailable(Exception):
    pass


class OpenAIEmbeddings:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        try:
            import openai
        except Exception as exc:
            logger.exception("OpenAI package not installed: %s", exc)
            raise EmbeddingsUnavailable("openai package not installed") from exc

        self._openai = openai
        self._api_key = api_key
        self._model = model
        self._openai.api_key = api_key

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # OpenAI's client is synchronous; run in thread to avoid blocking loop
        def _call():
            resp = self._openai.Embedding.create(input=texts, model=self._model)
            return [r["embedding"] for r in resp["data"]]

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            logger.exception("OpenAI embedding call failed")
            raise
*** End Patch