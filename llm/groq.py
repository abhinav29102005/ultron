"""
llm/groq.py – Groq Cloud High-Speed LLM Implementation
======================================================
Groq Cloud LLM integration using OpenAI-compatible API.
Supports ultra-fast inference (~500+ tokens/second).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Callable, TypeVar

from openai import AsyncOpenAI

from llm.base import BaseLLM
from llm.response import LLMResponse, LLMUsage
from llm.tools import ToolCall, ToolCallResponse

if TYPE_CHECKING:
    from config.settings import Settings

T = TypeVar("T")


class GroqLLM(BaseLLM):
    @staticmethod
    def _serialise_tool_arguments(messages: list[dict]) -> list[dict]:
        """Convert echoed tool-call arguments from dict to a JSON string for OpenAI/Groq API compatibility."""
        import json
        converted: list[dict] = []
        for message in messages:
            calls = message.get("tool_calls") if isinstance(message, dict) else None
            if not calls:
                converted.append(message)
                continue
            converted.append(
                {
                    **message,
                    "tool_calls": [
                        {
                            **call,
                            "function": {
                                **call["function"],
                                "arguments": (
                                    arguments
                                    if isinstance(arguments := call["function"].get("arguments"), str)
                                    else json.dumps(arguments or {})
                                ),
                            },
                        }
                        for call in calls
                    ],
                }
            )
        return converted


    """
    Groq Cloud LLM provider using OpenAI-compatible API.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            model=settings.groq_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

        api_key = settings.groq_api_key.get_secret_value() if hasattr(settings.groq_api_key, "get_secret_value") else str(settings.groq_api_key)
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in configuration")

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.groq_base_url,
        )

        self._timeout = settings.llm_timeout_seconds
        self._fast_model = settings.groq_fast_model
        self._fast_max_tokens = 128
        self._agent_max_tokens = int(getattr(settings, "agent_max_tokens", 2048))

    @property
    def provider_name(self) -> str:
        return "groq"

    def build_system_message(self, content: str) -> dict[str, str]:
        return {"role": "system", "content": content}

    def build_user_message(self, content: str) -> dict[str, str]:
        return {"role": "user", "content": content}

    def build_assistant_message(self, content: str) -> dict[str, str]:
        return {"role": "assistant", "content": content}

    async def _with_retry(self, call: Callable[[], T], max_attempts: int = 2) -> T:
        for attempt in range(max_attempts):
            try:
                return await call()
            except Exception:
                if attempt == max_attempts - 1:
                    raise
        raise RuntimeError("Unreachable retry state")

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        started_at = datetime.utcnow()
        use_fast = kwargs.pop("use_fast_model", False)
        model = self._fast_model if use_fast else self.model
        max_tokens = kwargs.get("max_tokens", self._fast_max_tokens if use_fast else self.max_tokens)
        temperature = kwargs.get("temperature", 0.0 if use_fast else self.temperature)

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self._timeout,
        )

        finished_at = datetime.utcnow()
        latency_ms = (finished_at - started_at).total_seconds() * 1000

        usage_data = response.usage
        prompt_tokens = usage_data.prompt_tokens if usage_data else 0
        completion_tokens = usage_data.completion_tokens if usage_data else 0

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=model,
            finish_reason=response.choices[0].finish_reason or "stop",
            usage=usage,
            provider=self.provider_name,
            latency_ms=latency_ms,
            timestamp=finished_at,
            raw=response,
        )

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        **kwargs: object,
    ) -> ToolCallResponse:
        started_at = datetime.utcnow()
        temperature = kwargs.get("temperature", self.temperature)

        serialised = self._serialise_tool_arguments(messages)
        response = await self._with_retry(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=serialised,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=self._agent_max_tokens,
                timeout=self._timeout,
            )
        )

        finished_at = datetime.utcnow()
        latency_ms = (finished_at - started_at).total_seconds() * 1000

        message = response.choices[0].message
        raw_tool_calls = getattr(message, "tool_calls", None) or []

        parsed_calls: list[ToolCall] = []
        for call in raw_tool_calls:
            call_id = getattr(call, "id", "") or f"call_{len(parsed_calls)}"
            fn = getattr(call, "function", None)
            if not fn:
                continue
            name = getattr(fn, "name", "")
            raw_args = getattr(fn, "arguments", "") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {"raw": raw_args}
            parsed_calls.append(ToolCall(id=call_id, name=name, arguments=args))

        usage_data = response.usage
        prompt_tokens = usage_data.prompt_tokens if usage_data else 0
        completion_tokens = usage_data.completion_tokens if usage_data else 0

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return ToolCallResponse(
            content=message.content or "",
            tool_calls=parsed_calls,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        response_stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            timeout=self._timeout,
        )

        async for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
