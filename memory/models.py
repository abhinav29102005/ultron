"""
memory/models.py – Memory Fact Model
======================================
Defines the MemoryFact dataclass and its JSON serialisation helpers.
MemoryFact is a dataclass containing fields only.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class MemoryFact:
    """
    A single durable fact FRIDAY remembers about the user.

    Contains fields only. No methods.
    """

    key: str
    value: str
    source_utterance: str
    created_at: datetime
    updated_at: datetime


def to_dict(fact: MemoryFact) -> dict[str, Any]:
    """
    Serialise a fact into a JSON-safe dictionary.

    Args:
        fact: The fact to serialise.

    Returns:
        A dictionary with ISO-8601 timestamps, safe for ``json.dump``.
    """
    return {
        "key": fact.key,
        "value": fact.value,
        "source_utterance": fact.source_utterance,
        "created_at": fact.created_at.isoformat(),
        "updated_at": fact.updated_at.isoformat(),
    }


def from_dict(data: dict[str, Any]) -> MemoryFact:
    """
    Rebuild a fact from its dictionary form.

    Args:
        data: A dictionary previously produced by :func:`to_dict`.

    Returns:
        The reconstructed :class:`MemoryFact`.

    Raises:
        KeyError: If a required field is absent.
        ValueError: If a timestamp is not valid ISO-8601.
    """
    return MemoryFact(
        key=str(data["key"]),
        value=str(data["value"]),
        source_utterance=str(data.get("source_utterance", "")),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )
