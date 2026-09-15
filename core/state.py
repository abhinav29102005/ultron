"""
core/state.py – Shared Assistant State
========================================
Defines the AssistantState enum and runtime state dataclasses.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from vision.screen_context import ScreenContext


class AssistantState(str, enum.Enum):
    """
    Enum representing the operating state of the assistant.
    """

    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    SHUTTING_DOWN = "SHUTTING_DOWN"


@dataclass
class ConversationTurn:
    """
    Represents a single turn in the conversation history.
    """

    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantRuntimeState:
    """
    Mutable state container for runtime metadata, conversation logs, and active skills.
    """

    mode: AssistantState = AssistantState.OFFLINE
    conversation_history: list[ConversationTurn] = field(default_factory=list)
    active_skills: set[str] = field(default_factory=set)
    session_id: str = ""
    last_user_input: str = ""
    last_response: str = ""
    error_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    # The last look at the screen, so a follow-up question ("what does the
    # second one say?") has something to be a follow-up to. In memory only,
    # one look at a time, and self-expiring — see vision/screen_context.py.
    screen_context: ScreenContext = field(default_factory=ScreenContext)
