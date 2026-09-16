"""
core/session_manager.py – Multi-Session Context Windows & Turn Continuity
========================================================================
Manages persistent conversation sessions, unique session IDs, context window
sliding buffers, citations, and token consumption metrics backed by the database.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import DatabaseManager

logger = logging.getLogger("ultron.session")


@dataclass
class SessionInfo:
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class SessionManager:
    """Manages active chat sessions, context switching, and token auditing."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.active_session: Optional[SessionInfo] = None

    async def initialize(self, default_title: str = "Main Chat") -> SessionInfo:
        """Load the most recent session from the database or create a new one."""
        sessions = await self.db.list_sessions()
        if sessions:
            first = sessions[0]
            self.active_session = SessionInfo(
                id=first["id"],
                title=first["title"],
                created_at=first["created_at"],
                updated_at=first["updated_at"],
                prompt_tokens=first["prompt_tokens"],
                completion_tokens=first["completion_tokens"],
                metadata=first["metadata"],
            )
            logger.info(f"Loaded active session: {self.active_session.id} ('{self.active_session.title}')")
        else:
            self.active_session = await self.create_session(title=default_title)
        return self.active_session

    async def create_session(self, title: Optional[str] = None) -> SessionInfo:
        """Generate a new session ID and register it in the database."""
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        session_id = f"chat_{timestamp_str}_{short_id}"
        session_title = title or f"Chat {timestamp_str[:8]}"

        await self.db.create_or_update_session(
            session_id=session_id,
            title=session_title,
            prompt_tokens=0,
            completion_tokens=0,
        )

        self.active_session = SessionInfo(
            id=session_id,
            title=session_title,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            prompt_tokens=0,
            completion_tokens=0,
        )
        logger.info(f"Created new session: {session_id} ('{session_title}')")
        return self.active_session

    async def switch_session(self, session_id: str) -> Optional[SessionInfo]:
        """Switch context to another existing session."""
        sess_dict = await self.db.get_session(session_id)
        if not sess_dict:
            return None
        self.active_session = SessionInfo(
            id=sess_dict["id"],
            title=sess_dict["title"],
            created_at=sess_dict["created_at"],
            updated_at=sess_dict["updated_at"],
            prompt_tokens=sess_dict["prompt_tokens"],
            completion_tokens=sess_dict["completion_tokens"],
            metadata=sess_dict["metadata"],
        )
        logger.info(f"Switched context to session: {session_id} ('{self.active_session.title}')")
        return self.active_session

    async def list_sessions(self) -> List[SessionInfo]:
        """Return all available sessions with token counts and dates."""
        raw_list = await self.db.list_sessions()
        return [
            SessionInfo(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                prompt_tokens=r["prompt_tokens"],
                completion_tokens=r["completion_tokens"],
                metadata=r["metadata"],
            )
            for r in raw_list
        ]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its message records."""
        deleted = await self.db.delete_session(session_id)
        if self.active_session and self.active_session.id == session_id:
            # Switch to next available or create fresh
            sessions = await self.list_sessions()
            if sessions:
                self.active_session = sessions[0]
            else:
                await self.create_session("Main Chat")
        return deleted

    async def record_turn(
        self,
        role: str,
        content: str,
        citations: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Record an utterance turn into the active session context."""
        if not self.active_session:
            await self.create_session()

        assert self.active_session is not None
        total_turn_tokens = prompt_tokens + completion_tokens
        await self.db.add_message(
            session_id=self.active_session.id,
            role=role,
            content=content,
            citations=citations or [],
            latency_ms=latency_ms,
            tokens=total_turn_tokens,
        )

        # Update session totals
        self.active_session.prompt_tokens += prompt_tokens
        self.active_session.completion_tokens += completion_tokens
        await self.db.create_or_update_session(
            session_id=self.active_session.id,
            title=self.active_session.title,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def get_context_window(self, max_turns: int = 20) -> List[Dict[str, str]]:
        """Retrieve recent turns formatted for the LLM context window."""
        if not self.active_session:
            return []
        msgs = await self.db.get_messages(self.active_session.id, limit=max_turns)
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    async def get_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve message records with full metadata."""
        if not self.active_session:
            return []
        return await self.db.get_messages(self.active_session.id, limit=limit)

    async def update_title(self, new_title: str) -> None:
        if self.active_session:
            self.active_session.title = new_title
            await self.db.create_or_update_session(
                session_id=self.active_session.id,
                title=new_title,
            )
