"""
llm/qwen.py – Local Qwen LLM Provider
======================================
Implements the BaseLLM interface using a locally running
Qwen model through Ollama.

Team: LLM Team
Phase: 1 (Implementation)
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING

from ollama import AsyncClient

from llm.base import BaseLLM
from llm.response import LLMResponse, LLMUsage
from llm.tools import ToolCall, ToolCallResponse, ToolsUnsupportedError

if TYPE_CHECKING:
    from config.settings import Settings


#: Reasoning that escaped Ollama's own parser. Qwen3 emits its chain of
#: thought terminated by ``</think>``; when the request said the model would
#: not be thinking, Ollama does not split it out and the whole trace arrives
#: in ``message.content`` -- opening tag sometimes absent, closing tag always
#: present. Everything up to the final terminator is reasoning, not answer.
_LEAKED_REASONING = re.compile(r"^.*?</think>\s*", re.DOTALL)

#: How much of a streamed reply to buffer while watching for that
#: terminator. A leak always begins at the first token, so if the marker has
#: not appeared within this many characters it is not coming -- and every
#: character held past that point is silence the user waits through.
_REASONING_SNIFF_CHARS = 400


def strip_leaked_reasoning(text: str | None) -> str | None:
    """Drop a reasoning trace that leaked into the answer.

    A backstop, not the fix -- :meth:`QwenLLM._thinking_supported` is what
    normally keeps the two apart. It matters because the failure is silent
    and downstream: the trace is spoken aloud by ChatSkill, and it turns the
    intent detector's JSON into unparseable prose.
    """
    if not text or "</think>" not in text:
        return text
    return _LEAKED_REASONING.sub("", text, count=1).lstrip() or text


class QwenLLM(BaseLLM):
    """
    Local Qwen LLM provider using Ollama.

    The model runs entirely on the local machine.
    No external API calls are required.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialise the local Qwen provider.
        """
        super().__init__(
            model=settings.qwen_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

        self._client = AsyncClient(
            host=settings.ollama_base_url,
        )

        self._timeout = settings.llm_timeout_seconds
        # See the field's comment in config/settings.py: Ollama's default
        # context silently truncates agent-mode prompts from the front.
        self._num_ctx = getattr(settings, "qwen_num_ctx", 8192)
        #: Resolved once from the server, then cached. None means "not asked
        #: yet"; see _thinking_supported.
        self._thinking: bool | None = None

    async def _thinking_supported(self) -> bool:
        """Whether this model must be called with ``think=True``.

        Neither value is safe to hardcode, and both failure modes are ugly:

        * ``think=True`` against a plain model is an outright HTTP 400
          ("qwen2.5:3b does not support thinking"), so every request dies.
        * ``think=False`` against qwen3:4b does *not* stop it reasoning. The
          model emits its trace anyway (identical ``eval_count``, measured),
          Ollama does not split it out because it was told not to expect it,
          and the raw trace lands in ``message.content`` -- which the
          assistant then speaks aloud and the intent detector fails to parse.

        So ask the server which one it is. One extra round trip per process;
        the answer is cached. A probe failure assumes False, matching the
        older non-reasoning models this provider was written against.
        """
        if self._thinking is None:
            try:
                info = await self._client.show(self.model)
                capabilities = getattr(info, "capabilities", None) or []
                self._thinking = "thinking" in capabilities
            except Exception:
                self._thinking = False
        return self._thinking

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        """
        Generate a complete response from the local Qwen model.
        """
        started_at = datetime.utcnow()

        # Natural language is the default: most callers (ChatSkill, WebSkill,
        # the emotion detector) want prose. Callers that parse the reply as
        # JSON — the intent detector, the memory fact extractor — must opt in
        # explicitly with json_mode=True.
        chat_kwargs = dict(
            model=self.model,
            messages=messages,
            think=await self._thinking_supported(),
            options={
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
                "num_ctx": self._num_ctx,
            },
        )
        if kwargs.pop("json_mode", False):
            chat_kwargs["format"] = "json"
        response = await self._client.chat(**chat_kwargs)

        finished_at = datetime.utcnow()
        latency_ms = (finished_at - started_at).total_seconds() * 1000

        prompt_tokens = getattr(response, "prompt_eval_count", 0) or 0
        completion_tokens = getattr(response, "eval_count", 0) or 0

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return LLMResponse(
            content=strip_leaked_reasoning(response.message.content),
            model=self.model,
            finish_reason="stop",
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
        """Ask the local model, offering it tools.

        Ollama accepts the OpenAI function envelope verbatim, so the schemas
        need no translation. What differs is the reply: arguments come back
        already decoded as a dict, and there are no call ids.

        Not every local model can do this. Ollama reports that by raising, and
        the message is the only thing distinguishing "this model has no tool
        support" from a real transport failure -- so it is matched, and
        re-raised as ToolsUnsupportedError for the assistant to fall back on.
        A genuine connection error is left alone, because retrying the old
        pipeline against the same dead server would not help either.
        """
        try:
            response = await self._client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                think=await self._thinking_supported(),
                options={
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                    "num_ctx": self._num_ctx,
                },
            )
        except Exception as exc:
            if "does not support tools" in str(exc).lower():
                raise ToolsUnsupportedError(
                    f"{self.model} cannot call tools: {exc}"
                ) from exc
            raise

        message = response.message

        calls = [
            ToolCall.from_raw(
                # Ollama sends no id; the transcript needs one to match each
                # result back to the call it answers.
                id=getattr(raw, "id", None) or f"call_{index}",
                name=raw.function.name,
                arguments=raw.function.arguments,
            )
            for index, raw in enumerate(getattr(message, "tool_calls", None) or [])
        ]

        return ToolCallResponse(
            content=strip_leaked_reasoning(message.content) or "", tool_calls=calls
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the local Qwen model.
        """
        chat_kwargs = dict(
            model=self.model,
            messages=messages,
            stream=True,
            think=await self._thinking_supported(),
            options={
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
                "num_ctx": self._num_ctx,
            },
        )
        if kwargs.pop("json_mode", False):
            chat_kwargs["format"] = "json"
        response = await self._client.chat(**chat_kwargs)

        # Same leak as complete(), but it cannot be cleaned after the fact:
        # a streamed trace is already on screen and half-spoken. So hold
        # everything back until the terminator has either arrived or clearly
        # is not coming, and only then start yielding.
        preamble: list[str] = []
        streaming = False

        async for chunk in response:
            content = chunk.message.content
            if not content:
                continue

            if streaming:
                yield content
                continue

            preamble.append(content)
            buffered = "".join(preamble)

            if "</think>" in buffered:
                streaming = True
                remainder = strip_leaked_reasoning(buffered)
                if remainder:
                    yield remainder
            elif len(buffered) > _REASONING_SNIFF_CHARS:
                # No terminator in the opening tokens, so this is a plain
                # answer and holding it back would only add latency.
                streaming = True
                yield buffered

        if not streaming and preamble:
            yield "".join(preamble)

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
        return "qwen"