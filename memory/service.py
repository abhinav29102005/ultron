"""
memory/service.py – Memory Service Facade
===========================================
Composes the fact store and the fact extractor into the single service the
ServiceContainer exposes to skills and to the Assistant.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

import re

from config.logging_config import get_logger
from memory.extractor import FactExtractor
from memory.models import MemoryFact
from memory.store import MemoryStore

logger = get_logger("memory.service")

#: An utterance without any first-person marker is a command or a question,
#: not a statement about the user, so there is nothing durable to extract.
_FIRST_PERSON = re.compile(
    r"\b(i|i'm|im|i've|ive|my|mine|me|myself|we|our)\b",
    re.IGNORECASE,
)


class MemoryService:
    """
    Captures, recalls, and forgets durable facts about the user.
    """

    def __init__(
        self,
        store: MemoryStore,
        extractor: FactExtractor,
        enabled: bool = True,
    ) -> None:
        """
        Initialise MemoryService.

        Args:
            store: The persistent fact store.
            extractor: The LLM-backed fact extractor.
            enabled: When False, capture is a no-op.
        """
        self._store = store
        self._extractor = extractor
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether background capture is switched on."""
        return self._enabled

    @property
    def store(self) -> MemoryStore:
        """Get the underlying fact store."""
        return self._store

    async def capture(self, utterance: str) -> list[MemoryFact]:
        """
        Extract durable facts from an utterance and persist them.

        Runs as a fire-and-forget background task, so every failure is
        swallowed and logged rather than surfaced to the user.

        Args:
            utterance: The words the user actually said.

        Returns:
            The facts written, or an empty list when nothing was remembered.
        """
        if not self._enabled:
            return []

        if not utterance or not utterance.strip():
            return []

        # Ollama serialises requests per model, so skipping command utterances
        # keeps a background extraction from delaying the user's next turn.
        if not _FIRST_PERSON.search(utterance):
            return []

        try:
            pairs = await self._extractor.extract(utterance)

            return [
                self._store.upsert(key=key, value=value, source_utterance=utterance)
                for key, value in pairs
            ]
        except Exception as exc:
            logger.debug(f"Memory capture failed for {utterance!r}: {exc}")
            return []

    def facts(self) -> list[MemoryFact]:
        """
        List everything currently remembered about the user.

        Returns:
            The stored facts, newest-updated first.
        """
        return self._store.all()

    def forget(self, target: str) -> list[MemoryFact]:
        """
        Delete every fact matching a target phrase.

        Args:
            target: What the user asked to be forgotten.

        Returns:
            The facts that were removed; empty when nothing matched.
        """
        matches = self._store.find(target)

        for fact in matches:
            self._store.delete(fact.key)

        return matches

    def render_block(self) -> str:
        """
        Render remembered facts as a compact block for prompt injection.

        Returns:
            The rendered block, or an empty string when nothing is known.
        """
        facts = self._store.all()

        if not facts:
            return ""

        lines = ["What you know about the user:"]
        lines.extend(f"- {fact.key}: {fact.value}" for fact in facts)
        return "\n".join(lines)
