"""
memory/__init__.py – Memory Package
=====================================
The ``memory`` package gives FRIDAY context retention: durable facts the
user states about themselves survive a restart and are injected back into
conversation.

Architecture:
    - :class:`~memory.models.MemoryFact` is the stored record.
    - :class:`~memory.store.MemoryStore` owns the JSON document on disk.
    - :class:`~memory.extractor.FactExtractor` turns an utterance into facts.
    - :class:`~memory.service.MemoryService` composes the two and is what the
      :class:`~core.container.ServiceContainer` exposes.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from memory.extractor import FactExtractor
from memory.models import MemoryFact, from_dict, to_dict
from memory.service import MemoryService
from memory.store import MemoryStore

__all__: list[str] = [
    "FactExtractor",
    "MemoryFact",
    "MemoryService",
    "MemoryStore",
    "from_dict",
    "to_dict",
]
