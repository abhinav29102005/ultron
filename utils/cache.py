"""
utils/cache.py – Response Cache
================================
Simple in-memory cache with TTL for LLM responses.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class ResponseCache:
    """
    LRU cache with TTL for caching LLM responses.
    """
    
    def __init__(self, max_size: int = 100, default_ttl: float = 300.0):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl

    def _make_key(self, prompt: str, model: str, temperature: float, max_tokens: int) -> str:
        """Create cache key from request parameters."""
        content = f"{prompt}|{model}|{temperature}|{max_tokens}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def get(self, prompt: str, model: str, temperature: float, max_tokens: int) -> Optional[Any]:
        """Get cached response if valid."""
        key = self._make_key(prompt, model, temperature, max_tokens)
        
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        
        # Check expiry
        if time.time() > entry.expires_at:
            del self._cache[key]
            return None
        
        # Move to end (LRU)
        self._cache.move_to_end(key)
        return entry.value

    def set(self, prompt: str, model: str, temperature: float, max_tokens: int, value: Any, ttl: Optional[float] = None) -> None:
        """Cache a response."""
        key = self._make_key(prompt, model, temperature, max_tokens)
        
        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._cache.popitem(last=False)
        
        self._cache[key] = CacheEntry(
            value=value,
            expires_at=time.time() + (ttl or self._default_ttl)
        )
        self._cache.move_to_end(key)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "keys": list(self._cache.keys()),
        }


# Global cache instance
_global_cache: ResponseCache | None = None


def get_cache() -> ResponseCache:
    """Get global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = ResponseCache()
    return _global_cache


class CachedLLM:
    """
    Wrapper that adds caching to any LLM.
    """
    
    def __init__(self, llm, cache: ResponseCache | None = None):
        self._llm = llm
        self._cache = cache or get_cache()

    @property
    def model(self) -> str:
        return self._llm.model

    @property
    def temperature(self) -> float:
        return self._llm.temperature

    @property
    def max_tokens(self) -> int:
        return self._llm.max_tokens

    def build_system_message(self, content: str) -> dict[str, str]:
        return self._llm.build_system_message(content)

    def build_user_message(self, content: str) -> dict[str, str]:
        return self._llm.build_user_message(content)

    def build_assistant_message(self, content: str) -> dict[str, str]:
        return self._llm.build_assistant_message(content)

    def switch(self, provider: str) -> None:
        if hasattr(self._llm, "switch"):
            self._llm.switch(provider)
        else:
            raise ValueError("Inner LLM does not support switching.")

    @property
    def current_provider(self) -> str:
        if hasattr(self._llm, "current_provider"):
            return self._llm.current_provider
        return getattr(self._llm, "provider_name", "unknown")

    @property
    def provider_name(self) -> str:
        return self._llm.provider_name

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> Any:
        # Create cache key from messages
        prompt_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        model = kwargs.get("model", self.model)
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        cached = self._cache.get(prompt_text, model, temperature, max_tokens)
        if cached is not None:
            return cached

        response = await self._llm.complete(messages, **kwargs)
        
        # Cache successful responses
        if hasattr(response, 'content') and response.content:
            self._cache.set(prompt_text, model, temperature, max_tokens, response)
        
        return response

    async def stream(self, messages: list[dict[str, str]], **kwargs):
        # Streaming bypasses cache for now
        async for chunk in self._llm.stream(messages, **kwargs):
            yield chunk

    async def complete_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> Any:
        """Pass a tool-calling turn straight through. Never cached.

        This method was missing, and its absence was invisible until the log
        filled with "Agent turn failed ('CachedLLM' object has no attribute
        'complete_with_tools')" — the container wraps every LLM in this class,
        so agent mode never ran at all and each turn quietly fell back to the
        classifier. To the user that read as "ULTRON can't reach the web",
        because web questions were answered by the chat model's own
        disclaimer instead of the research tool.

        Not cached on purpose: a tool call is a *decision to act*, not an
        answer. "Open youtube" asked twice means two tabs chosen twice;
        replaying a cached decision — or a stale transcript's decision —
        would act on a world that has moved on.
        """
        return await self._llm.complete_with_tools(messages, tools, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate anything not explicitly proxied to the wrapped LLM.

        The explicit methods above still win (``__getattr__`` only fires on a
        miss). This exists so the next method the switcher grows does not
        silently vanish behind the wrapper the way complete_with_tools did —
        a proxy that forgets a method is worse than no proxy, because the
        capability disappears without an import error anywhere.
        """
        return getattr(self._llm, name)