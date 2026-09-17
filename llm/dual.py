"""
llm/dual.py – Simultaneous Dual LLM Engine
===========================================
Coordinates two active LLM providers simultaneously (e.g. Groq for ultra-fast
speculation + NVIDIA NIM / Local Qwen for heavy reasoning & resilient failover).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from llm.base import BaseLLM
from llm.response import LLMResponse
from llm.tools import ToolCallResponse, ToolsUnsupportedError

logger = logging.getLogger("ultron.llm.dual")


class DualLLM(BaseLLM):
    """
    Simultaneous Dual-LLM orchestrator.
    Dispatches prompts to two models concurrently, enabling speculative race,
    resilient zero-downtime failover, and dual-layer verification.
    """

    def __init__(
        self,
        primary: BaseLLM,
        secondary: BaseLLM,
        strategy: str = "speculative_race",
    ) -> None:
        super().__init__(
            model=f"dual({primary.model} + {secondary.model})",
            temperature=primary.temperature,
            max_tokens=primary.max_tokens,
        )
        self.primary = primary
        self.secondary = secondary
        self.strategy = strategy

    @property
    def provider_name(self) -> str:
        return f"dual({self.primary.provider_name}+{self.secondary.provider_name})"

    @property
    def current_provider(self) -> str:
        return "dual"

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        """
        Execute completion across both LLMs simultaneously.
        In speculative_race mode, runs both concurrently. The fastest valid
        responder returns immediately; if one fails (e.g. 429 rate limit or timeout),
        the other seamlessly provides the response without dropping the turn.
        """
        task_primary = asyncio.create_task(self.primary.complete(messages, **kwargs))
        task_secondary = asyncio.create_task(self.secondary.complete(messages, **kwargs))

        # Race tasks: wait for the first to finish
        done, pending = await asyncio.wait(
            [task_primary, task_secondary],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Check if any finished task succeeded
        for task in done:
            exc = task.exception()
            if exc is None:
                # Cancel pending task to conserve resources/tokens
                for p in pending:
                    p.cancel()
                return task.result()
            else:
                logger.warning(
                    f"One Dual LLM worker encountered an error ({exc}). "
                    f"Awaiting secondary worker..."
                )

        # If the first finished task failed, wait for the pending one
        if pending:
            done_second, _ = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
            for task in done_second:
                exc = task.exception()
                if exc is None:
                    return task.result()
                else:
                    logger.error(f"Both Dual LLM workers failed. Secondary error: {exc}")
                    raise exc

        raise RuntimeError("All Dual LLM workers failed to return a response.")

    async def complete_with_tools(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        **kwargs: object,
    ) -> ToolCallResponse:
        """
        Run simultaneous tool-calling with failover.
        Concurrently attempts tool execution on primary while falling back
        to secondary if tool-calling is unsupported or encounters an error.
        """
        task_primary = asyncio.create_task(self.primary.complete_with_tools(messages, tools, **kwargs))
        task_secondary = asyncio.create_task(self.secondary.complete_with_tools(messages, tools, **kwargs))

        done, pending = await asyncio.wait(
            [task_primary, task_secondary],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            exc = task.exception()
            if exc is None:
                for p in pending:
                    p.cancel()
                return task.result()
            elif isinstance(exc, ToolsUnsupportedError):
                logger.info("Primary worker does not support tools; awaiting secondary worker...")
            else:
                logger.warning(f"Dual LLM worker failed tool call ({exc}); awaiting secondary...")

        if pending:
            done_second, _ = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
            for task in done_second:
                exc = task.exception()
                if exc is None:
                    return task.result()
                else:
                    raise exc

        raise RuntimeError("Dual LLM could not complete tool call on any configured provider.")

    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """Stream tokens using primary with seamless secondary fallback."""
        try:
            async for chunk in self.primary.stream(messages, **kwargs):
                yield chunk
        except Exception as e:
            logger.warning(f"Primary streaming failed ({e}); switching to secondary stream...")
            async for chunk in self.secondary.stream(messages, **kwargs):
                yield chunk
