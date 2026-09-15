"""
utils/__init__.py – Utilities Package
======================================
The ``utils`` package provides shared, framework-agnostic helpers that are
used across all JARVIS / FRIDAY modules.

Contents:
    - :mod:`~utils.helpers` – General-purpose utility functions
    - :mod:`~utils.decorators` – Reusable function/class decorators
    - :mod:`~utils.exceptions` – Custom exception hierarchy
    - :mod:`~utils.validators` – Input validation helpers
"""

from utils.exceptions import (
    AssistantNotInitialisedError,
    FridayBaseError,
    LLMError,
    PlannerError,
    SkillError,
    SpeechError,
    WakeWordError,
)

__all__: list[str] = [
    "FridayBaseError",
    "AssistantNotInitialisedError",
    "LLMError",
    "SpeechError",
    "WakeWordError",
    "PlannerError",
    "SkillError",
]
