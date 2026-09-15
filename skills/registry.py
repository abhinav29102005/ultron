"""
skills/registry.py – Skill Registry
======================================
Defines the registry store mapping skill names to instances.
All methods raise NotImplementedError.

Team: Skills Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from skills.base import Skill


class SkillRegistry:
    """
    Registry for mapping skill names to instances.
    All methods raise NotImplementedError.
    """

    def __init__(self) -> None:
        """
        Initialise SkillRegistry.
        """
        raise NotImplementedError

    def register(self, skill: Skill) -> None:
        """
        Register a new skill.
        TODO: Implement registry insertion.
        """
        raise NotImplementedError

    def replace(self, skill: Skill) -> None:
        """
        Force-replace a skill registration.
        TODO: Implement registry replacement.
        """
        raise NotImplementedError

    def unregister(self, name: str) -> None:
        """
        Deregister a skill.
        TODO: Implement registry removal.
        """
        raise NotImplementedError

    def get(self, name: str) -> Skill:
        """
        Retrieve a registered skill.
        TODO: Implement registry lookup.
        """
        raise NotImplementedError

    def has(self, name: str) -> bool:
        """
        Check registration presence.
        TODO: Implement lookup presence check.
        """
        raise NotImplementedError

    def all_skills(self) -> list[Skill]:
        """
        Get all registered skill instances.
        TODO: Implement skill listing.
        """
        raise NotImplementedError

    def enabled_skills(self) -> list[Skill]:
        """
        Get only active skill instances.
        TODO: Implement active skill filtering.
        """
        raise NotImplementedError

    def skill_names(self) -> list[str]:
        """
        Get sorted names of all skills.
        TODO: Implement name listing.
        """
        raise NotImplementedError

    def __iter__(self) -> Iterator[Skill]:
        """
        Iterate over registered skills.
        """
        raise NotImplementedError

    def __len__(self) -> int:
        """
        Get registry size.
        """
        raise NotImplementedError

    def __contains__(self, name: str) -> bool:
        """
        Check name presence.
        """
        raise NotImplementedError
