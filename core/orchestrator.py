"""
core/orchestrator.py – Task Orchestrator
=========================================
Coordinates orchestration of application startup and shutdown events.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from config.logging_config import get_logger

logger = get_logger("orchestrator")

if TYPE_CHECKING:
    from core.container import ServiceContainer
    from core.event_bus import EventBus
    from core.state import AssistantRuntimeState


class Orchestrator:
    """
    Coordinates application orchestration for startup/shutdown.
    No speech, planning, or routing is performed in Phase 0.
    """

    def __init__(
        self,
        container: ServiceContainer,
        event_bus: EventBus,
        state: AssistantRuntimeState,
    ) -> None:
        self._container = container
        self._event_bus = event_bus
        self._state = state

    async def run(self, user_input: str) -> str:
        """
        Run orchestration pipeline. Not implemented in Phase 0.
        """
        logger.warning("Pipeline run requested but voice/intelligence modules are not active.")
        return "System is in Phase 0 testing mode."
