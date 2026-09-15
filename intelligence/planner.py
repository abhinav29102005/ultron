"""
planner/planner.py – Task Planner
===================================
Defines the task decomposition engine interface.

Team: Planner Team
Phase: 2 (Planning & Routing)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from intelligence.task import Task, TaskStatus

if TYPE_CHECKING:
    from llm.base import BaseLLM
    from intelligence.intent_detector import DetectedIntent


class Planner:
    """
    Decomposes intents into structured tasks.
    """

    def __init__(self, llm: BaseLLM | None = None, max_steps: int = 10) -> None:
        """
        Initialise Planner.
        """
        self.llm = llm
        self.max_steps = max_steps

    async def plan(self, intents: list[DetectedIntent], raw_utterance: str = "") -> list[Task]:
        """
        Generate a sequence of tasks from one or more detected intents.
        Each intent becomes one Task. When there are multiple intents
        (a compound request), tasks are chained in order via
        dependencies so they execute sequentially.
        Includes raw_utterance in parameters for LLM tasks.
        """
        tasks: list[Task] = []
        previous_task_id: str | None = None

        for intent in intents:
            dependencies = [previous_task_id] if previous_task_id else []

            # Copy entities and add the raw utterance for chat/search tasks
            params = intent.entities.copy()
            params["raw_utterance"] = raw_utterance
            
            # For chat/greeting/general tasks, include the text
            if intent.intent in ("greeting", "general_chat", "help", "news", "search_web", "weather"):
                params["text"] = raw_utterance

            task = self._create_task(
                intent=intent.intent,
                parameters=params,
                dependencies=dependencies,
                # Conversational skills need the words the user actually said,
                # not just the extracted entities.
                metadata={"raw_utterance": intent.raw_utterance},
            )
            tasks.append(task)
            previous_task_id = task.task_id

        return tasks

    def _create_task(
        self,
        intent: str,
        parameters: dict[str, Any],
        dependencies: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Helper to instantiate a Task dataclass."""
        return Task(
            task_id=str(uuid.uuid4()),
            skill_name="",  # Router will populate this
            intent=intent,
            parameters=parameters,
            status=TaskStatus.PENDING,
            result=None,
            error=None,
            created_at=datetime.utcnow(),
            completed_at=None,
            dependencies=dependencies,
            metadata=metadata if metadata is not None else {},
        )
