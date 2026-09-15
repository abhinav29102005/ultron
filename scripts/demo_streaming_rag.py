#!/usr/bin/env python3
"""
scripts/demo_streaming_rag.py
==============================
Interactive live demo of all 5 operational flows for video recording.
Runs headlessly without requiring live Weaviate/OpenAI keys.
"""
from __future__ import annotations
import asyncio, json, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

BOLD = "\033[1m"; CYAN = "\033[96m"; GREEN = "\033[92m"; RED = "\033[91m"; RESET = "\033[0m"

def banner(title: str):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

def ok(msg: str):  print(f"  {GREEN}[OK]{RESET} {msg}")
def info(msg: str): print(f"  {CYAN}[--]{RESET} {msg}")

async def demo_flow_1_early_trigger():
    banner("Flow 1: Speculative Early Retrieval (G2)")
    from intelligence.retrieval_controller import RetrievalController, Decision
    ctrl = RetrievalController(container=MagicMock())
    chunks = ["What", "What is", "What is the venue", "What is the venue capacity venue capacity"]
    for i, chunk in enumerate(chunks):
        t = i * 0.8
        decision = ctrl.decide(chunk)
        info(f"t={t:.1f}s  chunk='{chunk}'  -> {decision.value}")
        if decision == Decision.RETRIEVE_EARLY:
            ok(f"RETRIEVE_EARLY at t={t:.1f}s! Speculative gain = {int((2.1 - t)*1000)}ms")
            break
        time.sleep(0.05)

async def demo_flow_2_multi_intent():
    banner("Flow 2: Multi-Intent Compound Decomposition (G3)")
    query = "What is the venue capacity, cancellation policy, and catering options?"
    info(f"Input: '{query}'")
    parts = [p.strip() for seg in query.split(" and ") for p in seg.split(",") if p.strip()]
    for i, p in enumerate(parts, 1):
        ok(f"Sub-query {i}: {p}")

async def demo_flow_3_grounded_citation(tmp):
    banner("Flow 3: Grounded Citation Synthesis (G4)")
    from intelligence.synthesizer import Synthesizer
    from intelligence.retrieval_handler import RetrievalResultEvent
    container = MagicMock()
    container.settings = SimpleNamespace(log_dir=tmp, openai_api_key=None)
    published = []
    container.event_bus.publish = AsyncMock(side_effect=lambda e: published.append(e))
    synth = Synthesizer(container=container)
    await synth.start()
    docs = [{"title": "Venue Policy", "url": "http://example.com", "snippet": "Max 500 guests.", "doc_id": "12", "section": "2"}]
    await synth._handler(RetrievalResultEvent(query="venue capacity", results=docs, decision="retrieve_early", session_id="demo", turn_id=1))
    r = published[-1]
    info(f"Answer V{r.answer_version}:")
    print(f"    {r.answer[:200]}")
    ok(f"Citation: {r.citations}")
    ok(f"Uncertainty: {r.uncertainty}")

async def demo_flow_4_delta_refinement(tmp):
    banner("Flow 4: Delta Refinement V1 -> V2 (G5)")
    from intelligence.synthesizer import Synthesizer
    from intelligence.retrieval_handler import RetrievalResultEvent
    container = MagicMock()
    container.settings = SimpleNamespace(log_dir=tmp, openai_api_key=None)
    published = []
    container.event_bus.publish = AsyncMock(side_effect=lambda e: published.append(e))
    synth = Synthesizer(container=container)
    await synth.start()
    docs = [{"title": "Policy", "url": "u", "snippet": "s", "doc_id": "45", "section": "3"}]
    await synth._handler(RetrievalResultEvent(query="venue options", results=docs, decision="retrieve_early", session_id="demo2", turn_id=1))
    await synth._handler(RetrievalResultEvent(query="Actually, make it international", results=docs, decision="retrieve_early", session_id="demo2", turn_id=2))
    for r in published:
        ok(f"Version {r.answer_version} | citations: {r.citations}")

async def demo_flow_5_telemetry(tmp):
    banner("Flow 5: Telemetry & Observability (G6)")
    from intelligence.telemetry import TelemetryRecorder
    settings = SimpleNamespace(log_dir=tmp, openai_api_key=None)
    r = TelemetryRecorder(settings)
    r.record_minimal("demo_session", 1, "synthesized_answer", {
        "retrieval_count": 3, "answer_version": 2, "early_retrieval_gain_ms": 1300,
        "retrieval_trigger_timestamp_s": 0.8, "total_latency_ms": 2100,
    })
    f = tmp / "telemetry_demo_session.jsonl"
    parsed = json.loads(f.read_text().strip().splitlines()[0])
    ok(f"JSONL written: {f.name}")
    print(f"    {json.dumps(parsed, indent=4, default=str)[:600]}")

async def main():
    print(f"\n{BOLD}ULTRON Streaming Live RAG - Interactive Demo{RESET}")
    tmp = Path("logs/demo")
    tmp.mkdir(parents=True, exist_ok=True)
    await demo_flow_1_early_trigger()
    await demo_flow_2_multi_intent()
    await demo_flow_3_grounded_citation(tmp)
    await demo_flow_4_delta_refinement(tmp)
    await demo_flow_5_telemetry(tmp)
    banner("All 5 demo flows completed successfully")

if __name__ == "__main__":
    asyncio.run(main())
