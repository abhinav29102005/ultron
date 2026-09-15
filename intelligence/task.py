"""
planner/task.py – Task Dataclass
==================================
Defines the Task structure and lifecycle status enum.
Task is a dataclass containing fields only.

Team: Planner Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class TaskStatus(str, enum.Enum):
    """
    State of task execution.
    """

    PENDING = "pending"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    READY_FOR_EXECUTION = "ready_for_execution"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """
    Represents an executable task item.
    Contains fields only. No methods.
    """

    task_id: str
    skill_name: str
    intent: str
    parameters: dict[str, Any]
    status: TaskStatus
    result: Any | None
    error: Exception | None
    created_at: datetime
    completed_at: datetime | None
    dependencies: list[str]
    metadata: dict[str, Any]
