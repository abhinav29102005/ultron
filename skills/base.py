"""
skills/base.py – Abstract Skill Base Class
============================================
Defines the Skill abstract base class.
Uses ABC abstract method signatures.

Team: Skills Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from intelligence.task import Task


class Skill(ABC):
    """
    Abstract Base Class representing a modular skill.
    """

    name: str
    description: str
    version: str
    enabled: bool

    def __init__(self, container: Any = None) -> None:
        """
        Gives skills access to shared services (the LLM, runtime state, the
        event bus, memory) through a single injected ServiceContainer.

        Every skill accepts a container. Skills that need nothing shared simply
        ignore it, so the Executor can construct all skills uniformly.
        """
        self.container = container

    @abstractmethod
    async def execute(self, task: Task) -> Any:
        """
        Execute skill logic.
        TODO: Implement in concrete skill.
        """
        ...

    async def on_load(self) -> None:
        """
        Lifecycle startup hook.
        TODO: Implement custom startup logic.
        """
        raise NotImplementedError

    async def on_unload(self) -> None:
        """
        Lifecycle teardown hook.
        TODO: Implement custom teardown logic.
        """
        raise NotImplementedError

    def validate_parameters(self, parameters: dict[str, Any]) -> bool:
        """
        Validate task parameters.
        TODO: Implement custom parameter validation.
        """
        raise NotImplementedError

    @property
    def skill_id(self) -> str:
        """
        Get identifier.
        TODO: Implement skill ID retrieval.
        """
        raise NotImplementedError
