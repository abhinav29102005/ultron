"""
planner/__init__.py – Planner Package
========================================
The ``planner`` package is responsible for converting a user utterance into
a structured execution plan.

Pipeline:
    raw text → IntentDetector → Planner → Task list → TaskRouter

Public surface:
    - :class:`~planner.intent_detector.IntentDetector`
    - :class:`~planner.planner.Planner`
    - :class:`~planner.router.TaskRouter`
    - :class:`~planner.parser.ResponseParser`
    - :class:`~planner.task.Task`

Team: Planner Team
Phase: 0 (Scaffold) → Phase 1 (Implementation)
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from intelligence.intent_detector import IntentDetector
    from intelligence.parser import ResponseParser
    from intelligence.planner import Planner
    from intelligence.router import TaskRouter
    from intelligence.task import Task, TaskStatus

__all__: list[str] = [
    "IntentDetector",
    "Planner",
    "TaskRouter",
    "ResponseParser",
    "Task",
    "TaskStatus",
]


def __getattr__(name: str) -> Any:
    if name == "IntentDetector":
        from intelligence.intent_detector import IntentDetector
        return IntentDetector
    if name == "ResponseParser":
        from intelligence.parser import ResponseParser
        return ResponseParser
    if name == "Planner":
        from intelligence.planner import Planner
        return Planner
    if name == "TaskRouter":
        from intelligence.router import TaskRouter
        return TaskRouter
    if name == "Task":
        from intelligence.task import Task
        return Task
    if name == "TaskStatus":
        from intelligence.task import TaskStatus
        return TaskStatus
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
