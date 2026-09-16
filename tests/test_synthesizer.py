"""
tests/test_synthesizer.py
=========================
Integration tests for intelligence/synthesizer.py:
- Grounded answer synthesis and versioning (V1 -> V2)
- Telemetry recording with early_retrieval_gain_ms and total_latency_ms
- Uncertainty flagging on missing evidence
"""
import time
import pytest
from unittest.mock import MagicMock, AsyncMock

from intelligence.synthesizer import Synthesizer, SynthesizerResultEvent
from intelligence.retrieval_handler import RetrievalResultEvent


@pytest.mark.asyncio
async def test_synthesizer_versioning_and_telemetry(tmp_path):
    mock_container = MagicMock()
    mock_settings = MagicMock()
    mock_settings.log_dir = tmp_path
    mock_container.settings = mock_settings

    published_events = []
    async def _capture(evt):
        published_events.append(evt)

    mock_container.event_bus.publish = AsyncMock(side_effect=_capture)

    synth = Synthesizer(mock_container)
    await synth.start()

    # Trigger turn 1
    t0 = time.time() - 1.2
    event_v1 = RetrievalResultEvent(
        query="travel reimbursement policy",
        results=[
            {
                "title": "Travel Policy",
                "doc_id": "Doc_45",
                "section": "§1",
                "snippet": "100% reimbursement on domestic travel.",
                "source": "corpus",
            }
        ],
        decision="hybrid",
        session_id="sess_synth_01",
        turn_id=1,
        trigger_timestamp_s=t0,
        start_timestamp_s=t0 - 0.5,
    )

    await synth._handler(event_v1)

    assert len(published_events) == 1
    res1: SynthesizerResultEvent = published_events[0]
    assert res1.answer_version == 1
    assert "Doc_45 §1" in res1.citations
    assert res1.uncertainty is None

    # Check telemetry file
    telemetry_file = tmp_path / "telemetry_sess_synth_01.jsonl"
    assert telemetry_file.exists()
    content = telemetry_file.read_text(encoding="utf-8")
    assert "synthesized_answer" in content
    assert "early_retrieval_gain_ms" in content

    # Trigger turn 2 (Refinement / V2)
    event_v2 = RetrievalResultEvent(
        query="international travel policy post-departure",
        results=[
            {
                "title": "International Travel Waiver",
                "doc_id": "Doc_45",
                "section": "§3",
                "snippet": "International trips require VP approval.",
                "source": "corpus",
            }
        ],
        decision="hybrid",
        session_id="sess_synth_01",
        turn_id=2,
        trigger_timestamp_s=time.time() - 0.8,
        start_timestamp_s=time.time() - 1.0,
    )

    await synth._handler(event_v2)

    assert len(published_events) == 2
    res2: SynthesizerResultEvent = published_events[1]
    assert res2.answer_version == 2
    assert "Doc_45 §3" in res2.citations


@pytest.mark.asyncio
async def test_synthesizer_uncertainty_flagging():
    mock_container = MagicMock()
    mock_container.settings.log_dir = None
    mock_container.event_bus.publish = AsyncMock()

    synth = Synthesizer(mock_container)
    await synth.start()

    # Empty retrieval results should trigger uncertainty
    empty_event = RetrievalResultEvent(
        query="quantum submarine maintenance protocol",
        results=[],
        decision="hybrid",
        session_id="sess_unknown",
        turn_id=1,
    )

    published = []
    synth.container.event_bus.publish = AsyncMock(side_effect=lambda e: published.append(e))
    await synth._handler(empty_event)

    assert len(published) == 1
    res: SynthesizerResultEvent = published[0]
    assert res.uncertainty is not None
    assert "insufficient" in res.uncertainty.lower() or "unverified" in res.uncertainty.lower()
