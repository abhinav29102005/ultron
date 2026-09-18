"""
llm/nebius.py – Nebius Token Factory & Nebius AI Cloud Provider
================================================================
First-class integration with Nebius Token Factory for running NVIDIA open-source
models (Nemotron-3-Nano, Nemotron-3-Super, Nemotron-3-Ultra, and Llama-3.1-Nemotron).
Provides two-tier hierarchical routing: Nano for fast, low-latency streaming calls
and Ultra/Super for deep reasoning, tool synthesis, and Live RAG.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from openai import AsyncOpenAI

from llm.base import BaseLLM
from llm.response import LLMResponse, LLMUsage
from llm.tools import ToolCall, ToolCallResponse

if TYPE_CHECKING:
    from config.settings import Settings


class NebiusLLM(BaseLLM):
    """
    Nebius Token Factory LLM provider powering NVIDIA open-source models.
    """

    def __init__(self, settings: Settings) -> None:
        resolved_model = getattr(settings, "nebius_model", None) or "nvidia/nemotron-3-super-120b-a12b"
        resolved_fast_model = getattr(settings, "nebius_fast_model", None) or "nvidia/nemotron-3-nano-30b-a3b"

        super().__init__(
            model=resolved_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

        self._fast_model = resolved_fast_model
        self._fast_max_tokens = getattr(settings, "llm_fast_max_tokens", 150)
        self._agent_max_tokens = getattr(settings, "agent_max_tokens", 2048)
        self._timeout = getattr(settings, "llm_timeout", 30.0)

        base_url = getattr(settings, "nebius_base_url", None) or "https://api.tokenfactory.nebius.com/v1"
        api_key = getattr(settings, "nebius_api_key", None) or "dummy-token"

        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )

    @property
    def fast_model(self) -> str:
        return self._fast_model

    async def complete(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Send chat completion request to Nebius Token Factory."""
        use_fast = kwargs.pop("use_fast_model", False)
        model = self._fast_model if use_fast else self.model
        max_tokens = kwargs.get("max_tokens", self._fast_max_tokens if use_fast else self.max_tokens)
        temperature = kwargs.get("temperature", 0.0 if use_fast else self.temperature)

        started_at = datetime.now(timezone.utc)

        response = await self._with_retry(
            lambda: self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._timeout,
            )
        )

        finished_at = datetime.now(timezone.utc)
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
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> ToolCallResponse:
        """Ask the model, offering it tools it may call via OpenAI-compatible schema."""
        response = await self._with_retry(
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=self._serialise_tool_arguments(messages),
                tools=tools,
                tool_choice="auto",
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self._agent_max_tokens),
                timeout=self._timeout,
            )
        )

        message = response.choices[0].message

        calls = [
            ToolCall.from_raw(
                id=getattr(raw, "id", "") or f"call_{index}",
                name=raw.function.name,
                arguments=raw.function.arguments,
            )
            for index, raw in enumerate(getattr(message, "tool_calls", None) or [])
        ]

        return ToolCallResponse(content=message.content or "", tool_calls=calls)

    @staticmethod
    def _serialise_tool_arguments(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        import json
        converted: List[Dict[str, Any]] = []
        for message in messages:
            calls = message.get("tool_calls") if isinstance(message, dict) else None
            if not calls:
                converted.append(message)
                continue

            converted.append({
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
            })
        return converted

    _MAX_ATTEMPTS = 3
    _RETRY_DELAY = 0.6

    @staticmethod
    def _is_transient(exc: BaseException) -> bool:
        text = str(exc)
        return any(code in text for code in ("500", "502", "503", "504")) or (
            "timeout" in text.lower() and "410" not in text
        )

    async def _with_retry(self, make_request):
        last: Optional[BaseException] = None
        for attempt in range(self._MAX_ATTEMPTS):
            try:
                return await make_request()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                last = exc
                if not self._is_transient(exc) or attempt == self._MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(self._RETRY_DELAY * (attempt + 1))
        raise last

    async def quick_complete(self, prompt: str, system_prompt: str = "") -> str:
        """Ultra-fast completion using Nemotron-3-Nano."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = await self.complete(messages, use_fast_model=True)
        return response.content.strip()

    async def stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream tokens directly from Nebius Token Factory."""
        use_fast = kwargs.pop("use_fast_model", False)
        model = self._fast_model if use_fast else self.model
        max_tokens = kwargs.get("max_tokens", self._fast_max_tokens if use_fast else self.max_tokens)
        temperature = kwargs.get("temperature", 0.0 if use_fast else self.temperature)

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=self._timeout,
        )

        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    def build_system_message(self, content: str) -> Dict[str, str]:
        return {"role": "system", "content": content}

    def build_user_message(self, content: str) -> Dict[str, str]:
        return {"role": "user", "content": content}

    def build_assistant_message(self, content: str) -> Dict[str, str]:
        return {"role": "assistant", "content": content}

    @property
    def provider_name(self) -> str:
        return "nebius"
