"""Tests for the reranker module (lexical fallback mode)."""

import asyncio

from intelligence.reranker import CrossEncoderReranker


def test_reranker_lexical_basic():
    r = CrossEncoderReranker(api_key=None)
    docs = [
        {"title": "Asyncio guide", "snippet": "coroutines and event loop", "content": "Asyncio provides coroutines and event loop for concurrency."},
        {"title": "Cooking pasta", "snippet": "boil water", "content": "Step by step to boil water and cook pasta."},
    ]

    ranked = asyncio.run(r.rerank("asyncio coroutines", docs))
    assert isinstance(ranked, list)
    assert ranked[0]["title"] == "Asyncio guide"
