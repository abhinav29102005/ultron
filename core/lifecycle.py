"""
core/lifecycle.py – Application Lifecycle Manager
==================================================
Coordinates initialization and teardown of application resources.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from core.state import AssistantState
from config.logging_config import get_logger

logger = get_logger("lifecycle")

if TYPE_CHECKING:
    from core.container import ServiceContainer


class ApplicationLifecycle:
    """
    Manages the application lifecycle, including startup and shutdown procedures.
    Only initializes infrastructural components.
    """

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._startup_hooks: list[Callable[[], Any]] = []
        self._shutdown_hooks: list[Callable[[], Any]] = []
        self._is_active = False

    def add_startup_hook(self, hook: Callable[[], Any]) -> None:
        """Register a hook to run during startup."""
        self._startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: Callable[[], Any]) -> None:
        """Register a hook to run during shutdown."""
        self._shutdown_hooks.append(hook)

    async def startup(self) -> None:
        """
        Start the application infrastructure.
        Runs registered startup hooks.
        """
        if self._is_active:
            logger.warning("Application lifecycle already started.")
            return

        logger.info("Starting application lifecycle...")
        self._container.state.mode = AssistantState.STARTING

        # Eagerly initialize the container services
        await self._container.initialise()

        # Run startup hooks
        for hook in self._startup_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as exc:
                logger.error(f"Error in startup hook '{hook.__name__}': {exc}")
                raise

        self._is_active = True
        logger.info("Application lifecycle started successfully.")

    async def shutdown(self) -> None:
        """
        Teardown application infrastructure.
        Runs registered shutdown hooks.
        """
        if not self._is_active:
            logger.warning("Application lifecycle is not active.")
            return

        logger.info("Shutting down application lifecycle...")
        self._container.state.mode = AssistantState.SHUTTING_DOWN

        # Run shutdown hooks in reverse order of registration
        for hook in reversed(self._shutdown_hooks):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as exc:
                logger.error(f"Error in shutdown hook '{hook.__name__}': {exc}")

        # Shutdown service container
        await self._container.shutdown()

        self._container.state.mode = AssistantState.OFFLINE
        self._is_active = False
        logger.info("Application lifecycle shut down complete.")
