"""
intelligence/executor.py – Task Executor
==========================================
Defines the execution module for Phase 2.

Team: Core Platform Team
Phase: 2 (Executor)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from intelligence.task import Task, TaskStatus

if TYPE_CHECKING:
    from core.container import ServiceContainer
    from skills.base import Skill

logger = logging.getLogger("executor")

class Executor:
    """
    Lightweight execution layer that dispatches tasks to their assigned skills.
    """

    def __init__(self, container: ServiceContainer) -> None:
        """
        Initialise Executor.
        """
        self._container = container
        self._skill_instances: dict[str, Skill] = {}

    async def execute(self, task: Task) -> tuple[bool, str]:
        """
        Execute a routed task using the mapped skill class.
        Returns a tuple of (success, output_message).
        """
        skill_class = task.metadata.get("skill_class")
        
        if not skill_class:
            task.status = TaskStatus.FAILED
            return False, f"No skill mapped for intent: {task.intent}"

        skill_name = skill_class.name
        
        # Instantiate skill lazily
        if skill_name not in self._skill_instances:
            self._skill_instances[skill_name] = skill_class(container=self._container)
        
        skill = self._skill_instances[skill_name]
        
        try:
            task.status = TaskStatus.RUNNING
            result = await skill.execute(task)
            task.status = TaskStatus.COMPLETED
            task.result = result
            return True, str(result)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = e
            logger.error(f"Execution failed for {task.intent}: {e}")
            return False, f"Error: {str(e)}"
