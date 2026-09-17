"""
llm/dual.py – Simultaneous Dual LLM Engine with Resilient Multi-Model Pool
=========================================================================
Coordinates two active LLM providers simultaneously (e.g. Groq for ultra-fast
speculation + NVIDIA NIM / Local Qwen for heavy reasoning & resilient failover).
Features active circuit-breaking/cooldowns and multi-model rotation across healthy candidates.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from llm.base import BaseLLM
from llm.response import LLMResponse
from llm.tools import ToolCallResponse, ToolsUnsupportedError

logger = logging.getLogger("ultron.llm.dual")


class DualLLM(BaseLLM):
    """
    Simultaneous Dual-LLM orchestrator with circular multi-model failover.
    Dispatches prompts to two models concurrently, enabling speculative race,
    resilient zero-downtime failover, and multi-model pool cycling.
    """

    def __init__(
        self,
        primary: BaseLLM,
        secondary: BaseLLM,
        strategy: str = "speculative_race",
        fallbacks: list[BaseLLM] | None = None,
        cooldown_seconds: float = 60.0,
    ) -> None:
        super().__init__(
            model=f"dual({primary.model} + {secondary.model})",
            temperature=primary.temperature,
            max_tokens=primary.max_tokens,
        )
        self.primary = primary
        self.secondary = secondary
        self.strategy = strategy
        self.fallbacks = fallbacks or []
        self._cooldown_seconds = cooldown_seconds
        self._cooldowns: dict[str, float] = {}

    @property
    def provider_name(self) -> str:
        return f"dual({self.primary.provider_name}+{self.secondary.provider_name})"

    @property
    def current_provider(self) -> str:
        return "dual"

    def _is_cooling_down(self, worker: BaseLLM) -> bool:
        key = getattr(worker, "provider_name", str(worker))
        return time.monotonic() < self._cooldowns.get(key, 0.0)

    def _mark_failure(self, worker: BaseLLM, exc: BaseException) -> None:
        key = getattr(worker, "provider_name", str(worker))
        self._cooldowns[key] = time.monotonic() + self._cooldown_seconds
        logger.warning(
            f"Dual LLM marked worker '{key}' in cooldown for {self._cooldown_seconds}s "
            f"after error: {exc}"
        )

    def _candidate_pool(self) -> list[BaseLLM]:
        pool = [self.primary, self.secondary] + self.fallbacks
        seen = set()
        unique = []
        for w in pool:
            p = getattr(w, "provider_name", str(w))
            if p not in seen:
                seen.add(p)
                unique.append(w)
        return unique

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        """
        Execute completion with multi-model speculation and circular failover.
        """
        pool = self._candidate_pool()
        active_candidates = [w for w in pool if not self._is_cooling_down(w)]
        if not active_candidates:
            active_candidates = pool

        if len(active_candidates) >= 2 and self.strategy == "speculative_race":
            worker_a = active_candidates[0]
            worker_b = active_candidates[1]
            task_a = asyncio.create_task(worker_a.complete(messages, **kwargs))
            task_b = asyncio.create_task(worker_b.complete(messages, **kwargs))

            done, pending = await asyncio.wait(
                [task_a, task_b],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                exc = task.exception()
                if exc is None:
                    for p in pending:
                        p.cancel()
                    return task.result()
                else:
                    failed_worker = worker_a if task is task_a else worker_b
                    self._mark_failure(failed_worker, exc)

            if pending:
                done_second, _ = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
                for task in done_second:
                    exc = task.exception()
                    if exc is None:
                        return task.result()
                    else:
                        remaining_worker = worker_b if task is task_b else worker_a
                        self._mark_failure(remaining_worker, exc)

            remaining_pool = [w for w in pool if w not in (worker_a, worker_b)]
            for backup in remaining_pool:
                try:
                    logger.info(f"Dual LLM cycling to fallback model/provider: {backup.provider_name}")
                    return await backup.complete(messages, **kwargs)
                except Exception as e:
                    self._mark_failure(backup, e)

            raise RuntimeError("All models in Dual LLM circular pool failed.")

        for worker in active_candidates:
            try:
                return await worker.complete(messages, **kwargs)
            except Exception as e:
                self._mark_failure(worker, e)

        for worker in pool:
            if worker not in active_candidates:
                try:
                    return await worker.complete(messages, **kwargs)
                except Exception as e:
                    self._mark_failure(worker, e)

        raise RuntimeError("All Dual LLM workers failed to return a response.")

    async def complete_with_tools(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        **kwargs: object,
    ) -> ToolCallResponse:
        """
        Run simultaneous tool-calling with circular multi-model failover.
        """
        pool = self._candidate_pool()
        active_candidates = [w for w in pool if not self._is_cooling_down(w)]
        if not active_candidates:
            active_candidates = pool

        if len(active_candidates) >= 2 and self.strategy == "speculative_race":
            worker_a = active_candidates[0]
            worker_b = active_candidates[1]
            task_a = asyncio.create_task(worker_a.complete_with_tools(messages, tools, **kwargs))
            task_b = asyncio.create_task(worker_b.complete_with_tools(messages, tools, **kwargs))

            done, pending = await asyncio.wait(
                [task_a, task_b],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                exc = task.exception()
                if exc is None:
                    for p in pending:
                        p.cancel()
                    return task.result()
                elif isinstance(exc, ToolsUnsupportedError):
                    logger.info("Worker does not support tools; awaiting peer worker...")
                else:
                    failed_worker = worker_a if task is task_a else worker_b
                    self._mark_failure(failed_worker, exc)

            if pending:
                done_second, _ = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
                for task in done_second:
                    exc = task.exception()
                    if exc is None:
                        return task.result()
                    else:
                        remaining_worker = worker_b if task is task_b else worker_a
                        self._mark_failure(remaining_worker, exc)

            remaining_pool = [w for w in pool if w not in (worker_a, worker_b)]
            for backup in remaining_pool:
                try:
                    logger.info(f"Dual LLM tool-calling cycling to fallback model/provider: {backup.provider_name}")
                    return await backup.complete_with_tools(messages, tools, **kwargs)
                except Exception as e:
                    self._mark_failure(backup, e)

            raise RuntimeError("All models in Dual LLM circular pool failed tool call.")

        for worker in active_candidates:
            try:
                return await worker.complete_with_tools(messages, tools, **kwargs)
            except Exception as e:
                self._mark_failure(worker, e)

        for worker in pool:
            if worker not in active_candidates:
                try:
                    return await worker.complete_with_tools(messages, tools, **kwargs)
                except Exception as e:
                    self._mark_failure(worker, e)

        raise RuntimeError("Dual LLM could not complete tool call on any configured provider.")

    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """Stream tokens using primary with seamless fallback across circular pool."""
        pool = self._candidate_pool()
        active = [w for w in pool if not self._is_cooling_down(w)] or pool

        last_exc: BaseException | None = None
        for worker in active:
            try:
                async for chunk in worker.stream(messages, **kwargs):
                    yield chunk
                return
            except Exception as e:
                last_exc = e
                self._mark_failure(worker, e)
                logger.warning(
                    f"Dual LLM worker '{worker.provider_name}' stream failed ({e}); "
                    f"circling to next model..."
                )

        if last_exc:
            raise last_exc
