"""
core/__init__.py – Core Package
================================
The ``core`` package is the heart of the JARVIS / FRIDAY assistant.
It owns the top-level orchestration, lifecycle management, event routing,
dependency injection container, and shared state.

Public surface:
    - :class:`~core.assistant.Assistant`
    - :class:`~core.orchestrator.Orchestrator`
    - :class:`~core.lifecycle.ApplicationLifecycle`
    - :class:`~core.state.AssistantState`
    - :class:`~core.event_bus.EventBus`
    - :class:`~core.container.ServiceContainer`
"""

from core.assistant import Assistant
from core.container import ServiceContainer
from core.event_bus import EventBus
from core.lifecycle import ApplicationLifecycle
from core.orchestrator import Orchestrator
from core.state import AssistantState

__all__: list[str] = [
    "Assistant",
    "Orchestrator",
    "ApplicationLifecycle",
    "AssistantState",
    "EventBus",
    "ServiceContainer",
]
