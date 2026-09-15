"""
skills/__init__.py – Skills Package
=====================================
The ``skills`` package implements the extensible skill system for
ULTRON.

A **skill** is a self-contained unit of capability (e.g., open an app,
search the web, set a timer). Skills are registered at startup and
dispatched to by the :class:`~planner.router.TaskRouter`.

Architecture:
    - :class:`~skills.base.Skill` defines the abstract contract.
    - :class:`~skills.registry.SkillRegistry` stores skill instances by name.
    - :class:`~skills.manager.SkillManager` manages the registry lifecycle
      and provides the router with a lookup API.

Team: Skills Team
Phase: 0 (Scaffold) → Phase 1+ (Individual Skills)
"""

from skills.base import Skill
from skills.manager import SkillManager
from skills.registry import SkillRegistry

__all__: list[str] = [
    "Skill",
    "SkillManager",
    "SkillRegistry",
]
