"""
utils/__init__.py – Utilities Package
======================================
The ``utils`` package provides shared, framework-agnostic helpers that are
used across all ULTRON modules.

Contents:
    - :mod:`~utils.helpers` – General-purpose utility functions
    - :mod:`~utils.decorators` – Reusable function/class decorators
    - :mod:`~utils.exceptions` – Custom exception hierarchy
    - :mod:`~utils.validators` – Input validation helpers
"""

from utils.exceptions import (
    AssistantNotInitialisedError,
    UltronError,
    LLMError,
    PlannerError,
    SkillError,
    SpeechError,
    WakeWordError,
)

__all__: list[str] = [
    "UltronError",
    "AssistantNotInitialisedError",
    "LLMError",
    "SpeechError",
    "WakeWordError",
    "PlannerError",
    "SkillError",
]
