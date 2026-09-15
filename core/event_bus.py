"""
core/event_bus.py – Application Event Bus
==========================================
Implements a lightweight asynchronous publish-subscribe event system.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Type, TypeVar
from utils.exceptions import EventBusError
from config.logging_config import get_logger

logger = get_logger("event_bus")

E = TypeVar("E", bound="BaseEvent")
EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


@dataclass
class BaseEvent:
    """Base class for all application events."""
    timestamp: datetime = field(default_factory=datetime.utcnow, kw_only=True)



@dataclass
class AssistantStartedEvent(BaseEvent):
    """Published when the Assistant has fully started."""
    pass


@dataclass
class AssistantStoppedEvent(BaseEvent):
    """Published when the Assistant has fully stopped."""
    pass


@dataclass
class StateChangedEvent(BaseEvent):
    """Published when the Assistant's operating state changes."""
    old_state: str
    new_state: str


@dataclass
class UserInputEvent(BaseEvent):
    """Published when the user provides text or spoken input."""
    text: str
    source: str
    session_id: str | None = None
    turn_id: int | None = None


@dataclass
class ResponseReadyEvent(BaseEvent):
    """Published when the assistant has a response ready."""
    response: str


@dataclass
class ExitRequestedEvent(BaseEvent):
    """Published when the user dismisses the assistant ("bye bye", "good night").

    A goodbye means goodbye: the app shuts down rather than hiding to the
    tray. It used to hide and keep the wake word listening, which left an
    assistant the user thought they had closed still holding the microphone,
    and made "bye bye" indistinguishable from minimising.

    The UI waits for the spoken farewell to finish before acting, so the
    goodbye is never cut off mid-word.
    """
    reason: str = "farewell"


@dataclass
class ErrorEvent(BaseEvent):
    """Published when an error occurs."""
    error: Exception
    context: str


class EventBus:
    """
    Lightweight asynchronous publish-subscribe event bus.
    Allows decoupling of components via event typing.
    """

    def __init__(self) -> None:
        self._handlers: dict[Type[BaseEvent], list[EventHandler]] = {}

    def subscribe(self, event_type: Type[E], handler: Callable[[E], Coroutine[Any, Any, None]]) -> None:
        """
        Register a handler for a specific event type.

        Args:
            event_type: The class of the event to subscribe to.
            handler: An async callable to invoke when the event is published.
        """
        if not asyncio.iscoroutinefunction(handler):
            raise EventBusError("Event handler must be an async coroutine function.")

        if event_type not in self._handlers:
            self._handlers[event_type] = []

        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug(f"Subscribed handler '{handler.__name__}' to event '{event_type.__name__}'")

    def unsubscribe(self, event_type: Type[E], handler: Callable[[E], Coroutine[Any, Any, None]]) -> None:
        """
        Remove a registered handler for a specific event type.

        Args:
            event_type: The class of the event to unsubscribe from.
            handler: The registered async callable.
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(f"Unsubscribed handler '{handler.__name__}' from event '{event_type.__name__}'")
            except ValueError:
                logger.warning(f"Handler '{handler.__name__}' was not subscribed to event '{event_type.__name__}'")

    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to all subscribed handlers.
        Handlers are executed concurrently.

        Args:
            event: The event instance to publish.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        logger.debug(f"Publishing event '{event_type.__name__}' to {len(handlers)} handler(s)")

        # Create tasks for all handlers to run them concurrently
        tasks = []
        for handler in handlers:
            tasks.append(self._run_handler(handler, event))

        await asyncio.gather(*tasks)

    async def _run_handler(self, handler: EventHandler, event: BaseEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            logger.exception(f"Error in event handler '{handler.__name__}' for event '{type(event).__name__}': {exc}")

    def handler_count(self, event_type: Type[BaseEvent]) -> int:
        """
        Return the number of handlers subscribed to a given event type.
        """
        return len(self._handlers.get(event_type, []))
