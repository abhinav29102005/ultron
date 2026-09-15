"""
core/permissions.py – Permission Manager
========================================
Stub permission manager for Phase 2 executor.

Team: Core Platform Team
Phase: 2 (Executor)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intelligence.task import Task

logger = logging.getLogger("permissions")

class PermissionManager:
    """
    Manages task execution permissions.
    Currently a stub that universally grants permission.
    """

    def check_permission(self, task: Task) -> bool:
        """
        Check if the system is allowed to execute the given task.
        """
        logger.debug(f"Permission granted for task: {task.intent}")
        return True
