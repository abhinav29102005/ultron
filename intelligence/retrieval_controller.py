"""
intelligence/retrieval_controller.py
==================================

Stub for a Retrieval Controller that listens to partial transcript events
and decides whether to WAIT, RETRIEVE_EARLY, or SUPPRESS retrieval. The
implementation is intentionally minimal: it exposes a `Decision` enum and a
`RetrievalController` class with a synchronous `decide` method and an
`async start()` method placeholder for event subscription.

Later: hook into the EventBus to receive `UserInputEvent` partials and
publish `retrieval_events` as structured telemetry.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
import logging
from dataclasses import dataclass

from core.event_bus import UserInputEvent, BaseEvent

logger = logging.getLogger("retrieval")


class Decision(Enum):
    WAIT = "wait"
    RETRIEVE_EARLY = "retrieve_early"
    SUPPRESS = "suppress"


class RetrievalController:
    """Simple rule-based controller for early retrieval decisions.

    This is a scaffold: replace `decide` with a model-backed classifier
    or token-entropy estimator later.
    """

    def __init__(self, container: Any) -> None:
        self.container = container
        self._subscribed = False
        self._handler = None

    def decide(self, partial_text: str) -> Decision:
        """Return a Decision for the given partial transcript.

        Current heuristic rules:
        - If partial_text contains presentation keywords, return SUPPRESS.
        - If length exceeds 6 words, return RETRIEVE_EARLY.
        - Otherwise return WAIT.
        """
        if not partial_text or not partial_text.strip():
            return Decision.WAIT

        import re
        import math

        text = partial_text.strip()
        if not text:
            return Decision.WAIT

        lower = text.lower()

        # Presentation suppression tokens (formatting / presentation requests)
        presentation_tokens = ["bullet", "short", "summar", "translate", "repeat"]
        if any(tok in lower for tok in presentation_tokens):
            return Decision.SUPPRESS

        # Tokenize into word tokens (simple alphanumeric tokens)
        tokens = re.findall(r"\w+", lower)
        n = len(tokens)

        # Semantic stability S(t): based on token entropy (lower entropy => more stable)
        if n <= 1:
            stability = 0.0
        else:
            from collections import Counter

            counts = Counter(tokens)
            probs = [c / n for c in counts.values()]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            max_entropy = math.log2(n) if n > 1 else 1.0
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
            stability = 1.0 - normalized_entropy

        # Trailing-preposition and partial-word penalties
        prepositions = {
            "in", "on", "at", "for", "with", "about", "of", "to", "from",
            "by", "as", "like", "through", "during", "before", "after",
            "between", "into", "over", "under", "around", "among", "against"
        }
        last_tok = tokens[-1] if tokens else ""
        # If the partial ends with a preposition, reduce stability
        if last_tok in prepositions:
            stability = max(0.0, stability - 0.25)

        # If the user appears to be mid-word (no trailing whitespace), slightly lower stability
        if partial_text and not partial_text.endswith(" ") and partial_text[-1].isalnum():
            stability = max(0.0, stability - 0.10)

        # Debug log
        logger.debug("Semantic stability={:.3f} for partial='{}'", stability, partial_text)

        # Threshold for early retrieval
        if stability >= 0.80:
            return Decision.RETRIEVE_EARLY

        return Decision.WAIT

    async def start(self) -> None:
        """Placeholder to subscribe to event bus and run controller loop.

        The container's EventBus should be used to receive partial voice
        events and publish retrieval_events. Implement once EventBus
        subscription conventions are finalised.
        """
        # Subscribe to UserInputEvent to receive partial voice transcripts.
        if self._subscribed:
            return

        import time

        async def _on_user_input(event: UserInputEvent) -> None:
            try:
                # Only consider partial voice transcripts here
                if getattr(event, "source", "") != "voice_partial":
                    return

                decision = self.decide(event.text)

                if decision == Decision.WAIT:
                    return

                now = time.time()
                start_ts = getattr(event, "start_timestamp_s", None) or getattr(event, "timestamp", None) or now

                # Publish a lightweight RetrievalEvent for listeners.
                retrieval = RetrievalEvent(
                    decision=decision.value,
                    text=event.text,
                    session_id=getattr(event, "session_id", None),
                    turn_id=getattr(event, "turn_id", None),
                    timestamp_s=now,
                    trigger_timestamp_s=now,
                    start_timestamp_s=start_ts,
                )
                await self.container.event_bus.publish(retrieval)
                logger.debug("Published retrieval event: {} for '{}'", decision.value, event.text)
            except Exception:
                logger.exception("RetrievalController handler failed")

        # Register handler
        self._handler = _on_user_input
        try:
            self.container.event_bus.subscribe(UserInputEvent, self._handler)
            self._subscribed = True
            logger.info("RetrievalController started and subscribed to UserInputEvent.")
        except Exception:
            logger.exception("Failed to subscribe RetrievalController to EventBus")

    async def close(self) -> None:
        """Unsubscribe from the EventBus."""
        if self._subscribed and self._handler is not None:
            try:
                self.container.event_bus.unsubscribe(UserInputEvent, self._handler)
            except Exception:
                logger.debug("Failed to unsubscribe RetrievalController handler")
            self._subscribed = False
            self._handler = None
            logger.info("RetrievalController stopped.")


@dataclass
class RetrievalEvent(BaseEvent):
    """Event published when the controller wants retrieval or suppression.

    Fields:
        decision: one of 'wait'|'retrieve_early'|'suppress'
        text: the partial transcript that triggered the decision
        session_id: optional session identifier
        turn_id: optional turn sequence number
        timestamp_s: epoch timestamp when early retrieval was triggered
        trigger_timestamp_s: timestamp when early retrieval was triggered
        start_timestamp_s: timestamp when utterance / turn began
    """
    decision: str
    text: str
    session_id: str | None = None
    turn_id: int | None = None
    timestamp_s: float | None = None
    trigger_timestamp_s: float | None = None
    start_timestamp_s: float | None = None
