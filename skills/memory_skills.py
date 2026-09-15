"""
skills/memory_skills.py – Context Memory Skills
=================================================
Deterministic skills for reading back and erasing what ULTRON remembers
about the user.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from intelligence.task import Task
from skills.base import Skill

if TYPE_CHECKING:
    from core.container import ServiceContainer


class MemorySkill(Skill):
    """
    Answers "what do you know about me?" and "forget X".

    Both branches are answered straight from the store. Recall in particular
    must never involve the model: the whole point is to report what is
    actually persisted, not what the model would guess.
    """

    name = "MemorySkill"
    description = "Recalls or erases the durable facts ULTRON knows about the user."
    version = "1.0.0"
    enabled = True

    # The container arrives through Skill.__init__; the Executor injects it into
    # every skill, so this class needs no constructor of its own. The annotation
    # only narrows the base class's Any for type checkers.
    container: ServiceContainer

    async def execute(self, task: Task) -> str:
        """
        Run the recall or forget branch for a routed task.

        Args:
            task: The routed task carrying the intent and parameters.

        Returns:
            The spoken response.

        Raises:
            ValueError: If the task carries an intent this skill cannot serve.
        """
        if task.intent == "memory_recall":
            return self._recall()

        if task.intent == "memory_forget":
            return self._forget(task)

        raise ValueError(f"MemorySkill cannot handle intent: '{task.intent}'.")

    def _recall(self) -> str:
        """
        Read back everything currently remembered.

        Returns:
            A spoken summary, or a friendly note when the store is empty.
        """
        facts = self.container.memory.facts()

        if not facts:
            return "I don't know anything about you yet."

        details = ", ".join(
            f"your {fact.key.replace('_', ' ')} is {fact.value}" for fact in facts
        )
        return f"Here's what I know about you: {details}."

    def _forget(self, task: Task) -> str:
        """
        Erase the facts matching the task's ``target`` parameter.

        Args:
            task: The routed task; ``target`` names what to forget.

        Returns:
            Confirmation naming what was removed, or a note that nothing matched.
        """
        target = str(task.parameters.get("target") or "").strip()

        if not target:
            return "Tell me what you'd like me to forget."

        removed = self.container.memory.forget(target)

        if not removed:
            return f"I don't have anything about {target} to forget."

        names = ", ".join(fact.key.replace("_", " ") for fact in removed)
        return f"Forgotten: {names}."
