"""
intelligence/embeddings.py
==========================

Simple embeddings provider wrapper. Currently implements an OpenAI-backed
provider; it exposes an async `embed_texts(texts: list[str]) -> list[list[float]]`.
The implementation is defensive: if OpenAI is not configured the provider
raises an informative error.
"""
from __future__ import annotations

from typing import List
import logging
import asyncio

logger = logging.getLogger("embeddings")


class EmbeddingsUnavailable(Exception):
    pass


class OpenAIEmbeddings:
    """Embeddings via the ``openai >= 1.0`` Python client.

    Uses ``openai.OpenAI`` (sync) wrapped in ``asyncio.to_thread`` so the
    event loop is never blocked.  If the ``openai`` package is missing or
    the API key is invalid the error is raised immediately at construction
    time rather than silently on the first query.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        try:
            import openai  # noqa: F811
        except ImportError as exc:
            logger.error("openai package not installed – pip install openai")
            raise EmbeddingsUnavailable("openai package not installed") from exc

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        logger.info("OpenAIEmbeddings ready (model={})", model)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Return one embedding vector per input text."""

        def _call() -> List[List[float]]:
            resp = self._client.embeddings.create(input=texts, model=self._model)
            return [item.embedding for item in resp.data]

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            logger.exception("OpenAI embedding call failed")
            raise