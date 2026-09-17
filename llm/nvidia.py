"""
llm/nvidia.py – NVIDIA NIM LLM Implementation
===========================================
NVIDIA NIM LLM integration using OpenAI-compatible API.
Supports fast model for quick responses.

Team: LLM Team
Phase: 1 (Implementation)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from llm.base import BaseLLM
from llm.response import LLMResponse, LLMUsage
from llm.tools import ToolCall, ToolCallResponse

if TYPE_CHECKING:
    from config.settings import Settings


class NvidiaLLM(BaseLLM):
    """
    NVIDIA NIM LLM provider using OpenAI-compatible API.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialise the NVIDIA NIM provider.
        """
        # Guard against retired models from older/stale .env files (returns HTTP 410 Gone)
        retired_models = (
            "meta/llama-3.1-8b-instruct",
            "meta/llama3-8b-instruct",
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.3-70b-instruct",
            "nvidia/nemotron-3-nano-30b-a3b",
        )
        resolved_model = settings.nvidia_model
        if resolved_model in retired_models:
            resolved_model = "nvidia/nemotron-3-super-120b-a12b"

        resolved_fast_model = settings.nvidia_fast_model
        if resolved_fast_model in retired_models:
            resolved_fast_model = "nvidia/nemotron-3-super-120b-a12b"

        super().__init__(
            model=resolved_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

        api_key = settings.nvidia_api_key.get_secret_value()
        if not api_key:
            raise ValueError("NVIDIA_API_KEY not set in configuration")

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.nvidia_base_url,
        )

        self._timeout = settings.llm_timeout_seconds
        self._fast_model = resolved_fast_model
        self._fast_max_tokens = 128  # Very short for quick responses
        # Tool-calling turns need their own, much larger budget; see the note
        # on agent_max_tokens in config/settings.py.
        self._agent_max_tokens = int(getattr(settings, "agent_max_tokens", 2048))

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        """
        Generate a complete response from the NVIDIA NIM model.
        """
        started_at = datetime.utcnow()

        # Use fast model if requested
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
            content=response.choices[0].message.content,
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
        """Ask the model, offering it tools it may call.

        ``tool_choice="auto"`` rather than forcing a call: most turns are
        answered without one, and a forced call on "good morning" would send
        ULTRON off to read the screen.
        """
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
            # from_raw, not the constructor: OpenAI sends the arguments as a
            # JSON string, and a model that emits a broken one must degrade to
            # empty arguments rather than taking the turn down with it.
            ToolCall.from_raw(
                id=getattr(raw, "id", "") or f"call_{index}",
                name=raw.function.name,
                arguments=raw.function.arguments,
            )
            for index, raw in enumerate(getattr(message, "tool_calls", None) or [])
        ]

        # content is None whenever the model only called tools.
        return ToolCallResponse(content=message.content or "", tool_calls=calls)

    @staticmethod
    def _serialise_tool_arguments(messages: list[dict]) -> list[dict]:
        """Convert echoed tool-call arguments from dict to a JSON string.

        The agent loop keeps arguments as a dict because Ollama's Message
        model requires one. This API requires a string. Rather than make the
        loop know which provider it is talking to, the conversion happens on
        the way out, here.

        Copies only the messages it changes -- the caller's transcript is
        reused across rounds and must not be mutated underneath it.
        """
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

    #: Attempts for one request, including the first.
    #:
    #: NIM returns sporadic 500s -- one live run of three identical requests
    #: had two of them fail this way. A 500 carries no state (nothing ran on
    #: their side), so retrying is safe. Three attempts, because a fourth is
    #: no longer a blip and the user is waiting.
    _MAX_ATTEMPTS = 3

    #: Backoff between attempts, in seconds. Short: this is inside a turn
    #: somebody is listening to, not a batch job.
    _RETRY_DELAY = 0.6

    @staticmethod
    def _is_transient(exc: BaseException) -> bool:
        """True for errors worth trying again.

        Deliberately narrow. A 410 (model retired) and a 404 (model not
        available on this key) are permanent facts about the request -- both
        have happened here -- and retrying them only spends the user's turn
        discovering the same thing twice.
        """
        text = str(exc)
        return any(code in text for code in ("500", "502", "503", "504")) or (
            "timeout" in text.lower() and "410" not in text
        )

    async def _with_retry(self, make_request):
        """Run ``make_request``, retrying only transient server failures."""
        import asyncio

        last: BaseException | None = None

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

        raise last  # pragma: no cover - loop always returns or raises

    async def quick_complete(self, prompt: str, system_prompt: str = "") -> str:
        """
        Ultra-fast completion for simple queries.
        Uses minimal tokens and zero temperature.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.complete(messages, use_fast_model=True)
        return response.content.strip()

    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the NVIDIA NIM model.
        """
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

    def build_system_message(self, content: str) -> dict[str, str]:
        """Build a system message."""
        return {"role": "system", "content": content}

    def build_user_message(self, content: str) -> dict[str, str]:
        """Build a user message."""
        return {"role": "user", "content": content}

    def build_assistant_message(self, content: str) -> dict[str, str]:
        """Build an assistant message."""
        return {"role": "assistant", "content": content}

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "nvidia"