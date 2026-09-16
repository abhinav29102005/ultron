"""
intelligence/synthesizer.py
==========================

Session-aware response synthesizer (V1 → V2 refinement) that listens to
`RetrievalResultEvent`, composes a grounded summary with exact citations
when available, and flags uncertainty when corpus evidence is insufficient.

It publishes `SynthesizerResultEvent` on the EventBus and writes a minimal
telemetry trace via `TelemetryRecorder` when configured.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from datetime import datetime

from core.event_bus import BaseEvent
from .retrieval_handler import RetrievalResultEvent
from .models import SynthesizerResultModel, DocChunk
from .telemetry import TelemetryRecorder

logger = logging.getLogger("synthesizer")


@dataclass
class SynthesizerResultEvent(BaseEvent):
    session_id: str | None
    turn_id: int | None
    answer_version: int
    answer: str
    citations: list[str]
    uncertainty: str | None = None


class Synthesizer:
    def __init__(self, container: Any) -> None:
        self.container = container
        self._subscribed = False
        self._handler = None
        self._sessions: dict[str, dict] = {}
        self.telemetry = TelemetryRecorder(container.settings) if hasattr(container, "settings") else None

    async def start(self) -> None:
        if self._subscribed:
            return

        async def _on_retrieval(event: RetrievalResultEvent) -> None:
            try:
                session_id = getattr(event, "session_id", "anon") or "anon"
                turn_id = getattr(event, "turn_id", None)

                state = self._sessions.setdefault(session_id, {"version": 0, "last_query": None, "last_docs": []})

                # Versioning: increment when the query changes or new retrieval arrives
                state["version"] += 1
                version = state["version"]
                state["last_query"] = event.query
                state["last_docs"] = event.results

                # Build citations only when doc_id and section metadata are present
                citations = []
                lines = []
                for idx, d in enumerate(event.results):
                    # d may be a mapping; ensure keys
                    doc_id = d.get("doc_id") if isinstance(d, dict) else None
                    section = d.get("section") if isinstance(d, dict) else None
                    title = d.get("title") if isinstance(d, dict) else None
                    snippet = d.get("snippet") if isinstance(d, dict) else None

                    if doc_id and section:
                        clean_doc_id = doc_id if str(doc_id).startswith("Doc_") else f"Doc_{doc_id}"
                        clean_sec = section if str(section).startswith("§") else f"§{section}"
                        cite = f"{clean_doc_id} {clean_sec}"
                        citations.append(cite)
                        lines.append(f"{title or d.get('url', '')} [{cite}]: {snippet or ''}")
                    else:
                        # No strict citation available for this doc; include snippet but mark uncertain
                        lines.append(f"{title or d.get('url', '')}: {snippet or ''}")

                answer_text = "\n".join(lines) if lines else "No documents retrieved."

                uncertainty = None
                if not citations:
                    uncertainty = "Insufficient corpus evidence: claims could not be verified from the retrieved documents."

                # Publish SynthesizerResultEvent
                synth_event = SynthesizerResultEvent(
                    session_id=session_id,
                    turn_id=turn_id,
                    answer_version=version,
                    answer=answer_text,
                    citations=citations,
                    uncertainty=uncertainty,
                )

                await self.container.event_bus.publish(synth_event)

                # Also write minimal telemetry
                try:
                    if self.telemetry:
                        trigger_ts = getattr(event, "trigger_timestamp_s", None) or getattr(event, "timestamp_s", None)
                        start_ts = getattr(event, "start_timestamp_s", None)
                        now_ts = datetime.now().timestamp()
                        gain_ms = max(0.0, (now_ts - trigger_ts) * 1000.0) if trigger_ts else 0.0
                        total_lat_ms = max(0.0, (now_ts - start_ts) * 1000.0) if start_ts else gain_ms
                        tm_payload = {
                            "retrieval_count": len(event.results),
                            "answer_version": version,
                            "uncertainty": bool(uncertainty),
                            "retrieval_trigger_timestamp_s": trigger_ts,
                            "early_retrieval_gain_ms": round(gain_ms, 2),
                            "total_latency_ms": round(total_lat_ms, 2),
                        }
                        self.telemetry.record_minimal(session_id, turn_id, "synthesized_answer", tm_payload)
                except Exception:
                    logger.exception("Failed to write telemetry for synthesized answer")

                logger.info("Synthesizer produced answer v{} for session={} (citations={})", version, session_id, len(citations))
            except Exception:
                logger.exception("Synthesizer handler failed")

        self._handler = _on_retrieval
        try:
            self.container.event_bus.subscribe(RetrievalResultEvent, self._handler)
            self._subscribed = True
            logger.info("Synthesizer subscribed to RetrievalResultEvent")
        except Exception:
            logger.exception("Failed to subscribe Synthesizer to EventBus")

    async def close(self) -> None:
        if self._subscribed and self._handler is not None:
            try:
                self.container.event_bus.unsubscribe(RetrievalResultEvent, self._handler)
            except Exception:
                logger.debug("Failed to unsubscribe Synthesizer")
            self._subscribed = False
            self._handler = None
            logger.info("Synthesizer stopped.")
