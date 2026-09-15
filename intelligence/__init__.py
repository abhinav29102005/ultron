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
