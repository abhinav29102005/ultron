"""Tests for utils/cache.py's CachedLLM wrapper.

The wrapper sits between the container and every LLM call, so anything it
fails to pass through is a capability the whole assistant silently loses.
That is not hypothetical: it proxied complete/stream but not
complete_with_tools, so every agent turn since the wrapper was introduced
died with AttributeError and fell back to the classifier — the log was a
wall of "Agent turn failed ('CachedLLM' object has no attribute
'complete_with_tools')", and to the user it looked like ULTRON could not
reach the web.
"""

from __future__ import annotations

import asyncio

import pytest

from utils.cache import CachedLLM, ResponseCache


class _InnerLLM:
    """Records what reaches it; answers differently each call."""

    model = "test-model"
    temperature = 0.2
    max_tokens = 64
    provider_name = "test"

    def __init__(self) -> None:
        self.tool_calls = 0
        self.completions = 0

    async def complete(self, messages, **kwargs):
        self.completions += 1

        class R:
            content = f"answer {self.completions}"

        return R()

    async def complete_with_tools(self, messages, tools, **kwargs):
        self.tool_calls += 1
        return {"call": self.tool_calls, "tools_seen": len(tools)}

    def some_future_method(self) -> str:
        return "delegated"


@pytest.fixture
def inner():
    return _InnerLLM()


@pytest.fixture
def cached(inner):
    return CachedLLM(inner, cache=ResponseCache(max_size=8, default_ttl=60))


class TestToolCallsPassThrough:
    def test_complete_with_tools_reaches_the_inner_llm(self, cached, inner):
        result = asyncio.run(
            cached.complete_with_tools(
                [{"role": "user", "content": "open youtube"}],
                [{"type": "function", "function": {"name": "open_website"}}],
            )
        )

        assert inner.tool_calls == 1
        assert result["tools_seen"] == 1

    def test_tool_calls_are_never_cached(self, cached, inner):
        """A cached tool decision would replay a stale action.

        The transcript grows every step of the agent loop, but even two
        identical prompts must not share an answer: "open youtube" twice
        means two tabs on purpose, chosen twice — not one decision replayed.
        """
        messages = [{"role": "user", "content": "open youtube"}]
        tools = [{"type": "function", "function": {"name": "open_website"}}]

        first = asyncio.run(cached.complete_with_tools(messages, tools))
        second = asyncio.run(cached.complete_with_tools(messages, tools))

        assert inner.tool_calls == 2
        assert first != second

    def test_unknown_attributes_delegate_to_the_inner_llm(self, cached):
        """The wrapper must never again be the reason a capability vanishes.

        Explicit proxies cover what exists today; delegation covers the next
        method the switcher grows.
        """
        assert cached.some_future_method() == "delegated"

    def test_missing_attributes_still_raise(self, cached):
        with pytest.raises(AttributeError):
            cached.definitely_not_a_method


class TestPlainCompletionStillCaches:
    def test_identical_prompts_hit_the_cache(self, cached, inner):
        messages = [{"role": "user", "content": "hello"}]

        first = asyncio.run(cached.complete(messages))
        second = asyncio.run(cached.complete(messages))

        assert inner.completions == 1
        assert first.content == second.content
