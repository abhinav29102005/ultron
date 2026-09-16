"""
core/database.py – Unified Hybrid Database Engine (PostgreSQL / SQLite)
========================================================================
Provides unified ACID persistence for:
  1. Chat sessions and multi-turn context windows
  2. Message histories, citations, latency, and token metrics
  3. Per-user settings (voice, guardrails, response limiters, execution mode)

Supports Dockerized PostgreSQL (via asyncpg) and automatically falls back
to local SQLite (via aiosqlite in data/ultron.db) for standalone/offline runs.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
    insert,
    update,
    delete,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("ultron.database")

metadata = MetaData()

# Table: sessions
sessions_table = Table(
    "sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("title", String(255), nullable=False, default="New Chat"),
    Column("created_at", DateTime, default=lambda: datetime.now(timezone.utc)),
    Column("updated_at", DateTime, default=lambda: datetime.now(timezone.utc)),
    Column("prompt_tokens", Integer, default=0),
    Column("completion_tokens", Integer, default=0),
    Column("metadata_json", Text, default="{}"),
)

# Table: messages
messages_table = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("role", String(32), nullable=False),
    Column("content", Text, nullable=False),
    Column("citations_json", Text, default="[]"),
    Column("timestamp", DateTime, default=lambda: datetime.now(timezone.utc)),
    Column("latency_ms", Float, default=0.0),
    Column("tokens", Integer, default=0),
)

# Table: user_settings
user_settings_table = Table(
    "user_settings",
    metadata,
    Column("key", String(128), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime, default=lambda: datetime.now(timezone.utc)),
)


class DatabaseManager:
    """Manages async database connections, migrations, and operations."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._is_postgres = False

    async def initialize(self) -> None:
        """Initialize engine, test connection, and create schema tables."""
        if self.db_url and ("postgres" in self.db_url or "postgresql" in self.db_url):
            try:
                # Ensure asyncpg dialect is specified
                if not self.db_url.startswith("postgresql+asyncpg"):
                    self.db_url = self.db_url.replace("postgresql://", "postgresql+asyncpg://")
                self._engine = create_async_engine(self.db_url, echo=False)
                # Test connection
                async with self._engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)
                self._is_postgres = True
                logger.info(f"Connected to Dockerized PostgreSQL: {self.db_url.split('@')[-1]}")
            except Exception as e:
                logger.warning(f"PostgreSQL connection failed ({e}); falling back to local SQLite.")
                self._engine = None

        if self._engine is None:
            if not self.db_url or not self.db_url.startswith("sqlite"):
                data_dir = Path("data")
                data_dir.mkdir(parents=True, exist_ok=True)
                sqlite_path = data_dir / "ultron.db"
                self.db_url = f"sqlite+aiosqlite:///{sqlite_path.resolve()}"
            self._engine = create_async_engine(self.db_url, echo=False)
            async with self._engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
            self._is_postgres = False
            logger.info(f"Connected to SQLite database at {self.db_url}")

        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    @property
    def is_postgres(self) -> bool:
        return self._is_postgres

    # ── Sessions ─────────────────────────────────────────────────────────────

    async def create_or_update_session(
        self,
        session_id: str,
        title: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._session_factory() as session:
            now = datetime.now(timezone.utc)
            meta_str = json.dumps(metadata_dict or {})
            stmt = select(sessions_table).where(sessions_table.c.id == session_id)
            res = await session.execute(stmt)
            existing = res.fetchone()

            if existing:
                upd = (
                    update(sessions_table)
                    .where(sessions_table.c.id == session_id)
                    .values(
                        title=title,
                        updated_at=now,
                        prompt_tokens=sessions_table.c.prompt_tokens + prompt_tokens,
                        completion_tokens=sessions_table.c.completion_tokens + completion_tokens,
                        metadata_json=meta_str,
                    )
                )
                await session.execute(upd)
            else:
                ins = insert(sessions_table).values(
                    id=session_id,
                    title=title,
                    created_at=now,
                    updated_at=now,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    metadata_json=meta_str,
                )
                await session.execute(ins)
            await session.commit()

    async def list_sessions(self) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(sessions_table).order_by(sessions_table.c.updated_at.desc())
            res = await session.execute(stmt)
            rows = res.fetchall()
            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "metadata": json.loads(r.metadata_json or "{}"),
                }
                for r in rows
            ]

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(sessions_table).where(sessions_table.c.id == session_id)
            res = await session.execute(stmt)
            r = res.fetchone()
            if not r:
                return None
            return {
                "id": r.id,
                "title": r.title,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "metadata": json.loads(r.metadata_json or "{}"),
            }

    async def delete_session(self, session_id: str) -> bool:
        async with self._session_factory() as session:
            del_msgs = delete(messages_table).where(messages_table.c.session_id == session_id)
            await session.execute(del_msgs)
            del_sess = delete(sessions_table).where(sessions_table.c.id == session_id)
            res = await session.execute(del_sess)
            await session.commit()
            return res.rowcount > 0

    # ── Messages ─────────────────────────────────────────────────────────────

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        tokens: int = 0,
    ) -> int:
        async with self._session_factory() as session:
            now = datetime.now(timezone.utc)
            ins = insert(messages_table).values(
                session_id=session_id,
                role=role,
                content=content,
                citations_json=json.dumps(citations or []),
                timestamp=now,
                latency_ms=latency_ms,
                tokens=tokens,
            )
            res = await session.execute(ins)
            # Update session timestamp
            upd = (
                update(sessions_table)
                .where(sessions_table.c.id == session_id)
                .values(updated_at=now)
            )
            await session.execute(upd)
            await session.commit()
            return res.inserted_primary_key[0] if res.inserted_primary_key else 0

    async def get_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = (
                select(messages_table)
                .where(messages_table.c.session_id == session_id)
                .order_by(messages_table.c.id.asc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            rows = res.fetchall()
            return [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "role": r.role,
                    "content": r.content,
                    "citations": json.loads(r.citations_json or "[]"),
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "latency_ms": r.latency_ms,
                    "tokens": r.tokens,
                }
                for r in rows
            ]

    # ── Settings ─────────────────────────────────────────────────────────────

    async def get_setting(self, key: str, default: Any = None) -> Any:
        async with self._session_factory() as session:
            stmt = select(user_settings_table).where(user_settings_table.c.key == key)
            res = await session.execute(stmt)
            r = res.fetchone()
            if not r:
                return default
            try:
                return json.loads(r.value)
            except Exception:
                return r.value

    async def set_setting(self, key: str, value: Any) -> None:
        async with self._session_factory() as session:
            now = datetime.now(timezone.utc)
            val_str = json.dumps(value)
            stmt = select(user_settings_table).where(user_settings_table.c.key == key)
            res = await session.execute(stmt)
            if res.fetchone():
                upd = (
                    update(user_settings_table)
                    .where(user_settings_table.c.key == key)
                    .values(value=val_str, updated_at=now)
                )
                await session.execute(upd)
            else:
                ins = insert(user_settings_table).values(
                    key=key, value=val_str, updated_at=now
                )
                await session.execute(ins)
            await session.commit()

    async def get_all_settings(self) -> Dict[str, Any]:
        async with self._session_factory() as session:
            stmt = select(user_settings_table)
            res = await session.execute(stmt)
            result = {}
            for r in res.fetchall():
                try:
                    result[r.key] = json.loads(r.value)
                except Exception:
                    result[r.key] = r.value
            return result

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()


# Global default database instance
_global_db: Optional[DatabaseManager] = None

async def get_database() -> DatabaseManager:
    global _global_db
    if _global_db is None:
        _global_db = DatabaseManager()
        await _global_db.initialize()
    return _global_db
