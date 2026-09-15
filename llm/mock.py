"""
llm/mock.py – Mock LLM Implementation
=======================================
Deterministic in-process LLM used by the test suite so extractors and
skills can be exercised without a running model server.

Team: LLM Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

from llm.base import BaseLLM
from llm.response import LLMResponse, LLMUsage


class MockLLM(BaseLLM):
    """
    Returns a canned response and records how often it was asked.

    The call counter is what lets tests assert that a code path skipped the
    model entirely rather than merely ignoring its answer.
    """

    def __init__(
        self,
        default_response: str = "",
        response_delay_ms: float = 0.0,
    ) -> None:
        """
        Initialise MockLLM.

        Args:
            default_response: Text every completion returns until overridden.
            response_delay_ms: Artificial latency, in milliseconds.
        """
        super().__init__(model="mock", temperature=0.0, max_tokens=512)

        self._default_response = default_response
        self._response = default_response
        self._response_delay_ms = response_delay_ms
        self._call_count = 0
        self.last_messages: list[dict[str, str]] = []

    @property
    def call_count(self) -> int:
        """Number of completions and streams requested since the last reset."""
        return self._call_count

    @property
    def response(self) -> str:
        """The text the next completion will return."""
        return self._response

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        """
        Return the canned response in a well-formed envelope.

        Args:
            messages: The conversation to "complete"; recorded, not read.
            **kwargs: Accepted and ignored, matching the provider contract.

        Returns:
            An :class:`LLMResponse` carrying the canned text.
        """
        started_at = datetime.utcnow()

        self._call_count += 1
        self.last_messages = list(messages)

        await self._simulate_latency()

        finished_at = datetime.utcnow()
        latency_ms = (finished_at - started_at).total_seconds() * 1000

        prompt_tokens = sum(len(message.get("content", "").split()) for message in messages)
        completion_tokens = len(self._response.split())

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return LLMResponse(
            content=self._response,
            model=self.model,
            finish_reason="stop",
            usage=usage,
            provider=self.provider_name,
            latency_ms=latency_ms,
            timestamp=finished_at,
            raw={"messages": self.last_messages, "response": self._response},
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """
        Yield the canned response one whitespace-delimited token at a time.

        Args:
            messages: The conversation to "complete"; recorded, not read.
            **kwargs: Accepted and ignored, matching the provider contract.

        Yields:
            Successive chunks of the canned response.
        """
        self._call_count += 1
        self.last_messages = list(messages)

        await self._simulate_latency()

        for index, token in enumerate(self._response.split()):
            yield token if index == 0 else f" {token}"

    def set_response(self, response: str) -> None:
        """
        Replace the text returned by subsequent completions.

        Args:
            response: The new canned response.
        """
        self._response = response

    def reset(self) -> None:
        """Restore the default response and zero the call counter."""
        self._response = self._default_response
        self._call_count = 0
        self.last_messages = []

    def build_system_message(self, content: str) -> dict[str, str]:
        """Build a system message."""
        return {
            "role": "system",
            "content": content,
        }

    def build_user_message(self, content: str) -> dict[str, str]:
        """Build a user message."""
        return {
            "role": "user",
            "content": content,
        }

    def build_assistant_message(self, content: str) -> dict[str, str]:
        """Build an assistant message."""
        return {
            "role": "assistant",
            "content": content,
        }

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "mock"

    async def _simulate_latency(self) -> None:
        """Sleep for the configured artificial delay, if any."""
        if self._response_delay_ms > 0:
            await asyncio.sleep(self._response_delay_ms / 1000)
