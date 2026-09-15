"""
intelligence/tool_dispatcher.py – Running a tool call
======================================================
The join between the agent loop and everything FRIDAY could already do.

A tool call becomes an ordinary :class:`~intelligence.task.Task` carrying the
tool's intent, and that Task goes through the existing router and executor
unchanged. This is the reason the agent loop could be added without rewriting
a single skill: from a skill's point of view nothing happened, it still
receives a Task with the parameters it has always read.

Errors never escape. A skill that fails returns its message as text, which the
agent loop hands back to the model -- which can then read what went wrong and
try something else. Raising would end the turn instead, and the user would
hear "something went wrong" rather than a second attempt.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from config.logging_config import get_logger
from intelligence.task import Task, TaskStatus
from intelligence.tool_registry import TOOLS_BY_NAME

if TYPE_CHECKING:
    from core.container import ServiceContainer
    from llm.tools import ToolCall

logger = get_logger("agent.dispatch")


class ToolDispatcher:
    """Turn a tool call into a routed, executed Task."""

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container

    # ── what the agent loop asks ──────────────────────────────────────────

    def is_known(self, name: str) -> bool:
        return name in TOOLS_BY_NAME

    def needs_confirmation(self, name: str) -> bool:
        """True when this tool must be approved before it runs.

        An unknown name is not confirmable — it is refused before it reaches
        here — so this answers False rather than raising a KeyError inside the
        loop's safety check.
        """
        tool = TOOLS_BY_NAME.get(name)
        return bool(tool and tool.confirm)

    # ── running one ───────────────────────────────────────────────────────

    async def run(self, call: ToolCall, utterance: str = "") -> str:
        """Execute ``call`` and return whatever the skill produced, as text."""
        tool = TOOLS_BY_NAME.get(call.name)
        if tool is None:
            return (
                f"Error: unknown tool '{call.name}'. Use one of the tools you "
                f"were given."
            )

        task = self._build_task(tool.intent, self._parameters(tool, call), utterance)

        routed = await self._container.router.route([task])
        task = routed[0] if routed else task

        success, message = await self._container.executor.execute(task)

        if not success:
            logger.info(f"Tool {call.name} reported failure: {message}")
            return f"{call.name} failed: {message}"

        # The Task carries the skill's real return value, which for the
        # research skill is a rich object whose __str__ is the full cited
        # answer. Preferring it over the executor's stringified copy keeps
        # that intact.
        result = task.result if task.result is not None else message
        return str(result)

    # ── building the task ─────────────────────────────────────────────────

    @staticmethod
    def _parameters(tool, call: ToolCall) -> dict[str, Any]:
        """The model's arguments, plus any legacy names the skill reads.

        An alias never overwrites a value the model supplied explicitly: if it
        sent both, the model's own choice wins.
        """
        params = dict(call.arguments)

        # The tool's own fixed parameters, where the model did not set one.
        for key, value in tool.fixed.items():
            params.setdefault(key, value)

        for argument, alias in tool.aliases.items():
            if argument in params and alias not in params:
                params[alias] = params[argument]

        return params

    @staticmethod
    def _build_task(intent: str, parameters: dict[str, Any], utterance: str) -> Task:
        """A Task shaped exactly like one the Planner would have produced.

        ``raw_utterance`` appears in both places because the skills disagree
        about where to look: ChatSkill and WebSkill read the parameter, the
        vision and research skills read the metadata. The Planner sets both
        for the same reason.
        """
        return Task(
            task_id=str(uuid.uuid4()),
            skill_name="",
            intent=intent,
            parameters={**parameters, "raw_utterance": utterance},
            status=TaskStatus.PENDING,
            result=None,
            error=None,
            created_at=datetime.now(),
            completed_at=None,
            dependencies=[],
            metadata={"raw_utterance": utterance, "via_tool_call": True},
        )
