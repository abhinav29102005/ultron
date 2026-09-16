"""
intelligence/telemetry.py
=========================

Simple telemetry recorder that writes structured JSON traces using
`intelligence.models.TelemetryTrace`. Traces are appended to a per-session
JSONL file under the configured `log_dir` (from settings).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from .models import TelemetryTrace

logger = logging.getLogger("telemetry")


class TelemetryRecorder:
    def __init__(self, settings) -> None:
        raw_log_dir = getattr(settings, "log_dir", None) or Path("logs")
        self.log_dir = Path(raw_log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_trace(self, trace: TelemetryTrace) -> None:
        # Write one file per session for easy inspection
        name = trace.session_id or "anon"
        fname = self.log_dir / f"telemetry_{name}.jsonl"
        try:
            with fname.open("a", encoding="utf-8") as fh:
                data = trace.model_dump() if hasattr(trace, "model_dump") else trace.dict()
                fh.write(json.dumps(data, default=str) + "\n")
            logger.debug("Telemetry trace written to {}", fname)
        except Exception:
            logger.exception("Failed to write telemetry trace to {}", fname)

    def record_minimal(self, session_id: Optional[str], turn_id: Optional[int], event_name: str, payload: Optional[dict] = None) -> None:
        trace = TelemetryTrace(
            session_id=session_id,
            trace_id=None,
            created_at=datetime.utcnow(),
            stream_duration_s=None,
            retrieval_trigger_timestamp_s=payload.get("retrieval_trigger_timestamp_s") if payload else None,
            early_retrieval_gain_ms=payload.get("early_retrieval_gain_ms") if payload else None,
            total_latency_ms=payload.get("total_latency_ms") if payload else None,
            prompt_tokens=payload.get("prompt_tokens") if payload else None,
            completion_tokens=payload.get("completion_tokens") if payload else None,
            events=[{
                "session_id": session_id,
                "turn_id": turn_id,
                "event_name": event_name,
                "timestamp": datetime.utcnow(),
                "payload": payload,
            }],
        )

        self.write_trace(trace)
