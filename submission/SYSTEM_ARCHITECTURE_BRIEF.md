# Samsung PRISM GenAI Hackathon 2026 — Theme 4: Streaming Live RAG
## System Architecture & Engineering Brief (6-Page Technical Specification)

**Team Name**: 4 Bottle Codeka  
**College**: Thapar Institute of Engineering & Technology, Patiala  
**Members**: Abhinav Kumar Singh (Lead), Sukhansh Mittal, Lakkshya Jha, Vikramaditya Singh  
**Repository**: [https://github.com/abhinav29102005/ultron](https://github.com/abhinav29102005/ultron)  
**Release Tag**: `PRISM_GENAI_HACKATHON_Y2026`  

---

### 1. Executive Summary & Design Rationale
Conventional Retrieval-Augmented Generation (RAG) relies on a rigid turn-complete execution model: a user speaks, pauses, and the system synchronously converts the transcript into an embedding, queries a vector database, and generates an answer. In real-time conversational and voice-interactive environments, this introduces:
1. **Unacceptable Duplex Latency**: Pauses of 1,500ms–2,500ms while waiting for utterance boundary detection and dense vector search.
2. **Compound Multi-Intent Fragmentation**: Real speech packages multiple distinct requests into a single breath (e.g., venue capacity, cancellation policies, catering terms).
3. **Mid-Utterance Self-Corrections**: Users pivot mid-sentence (*"I need lodging in Pune... wait, make that Mumbai"*). Traditional RAG commits to the stale entity or produces contradictory hallucinations.
4. **Presentation Compute Waste**: Follow-up formatting turns (*"format that as two bullets"*) unnecessarily re-invoke expensive vector search pipelines.

**ULTRON Streaming Live RAG** resolves these fundamental challenges by implementing an event-driven, speculative, multi-tier retrieval engine with mid-stream invalidation, stateful session refinement lineage ($V_1 \to V_2$), and Gate 0 presentation query suppression.

---

### 2. End-to-End System Pipeline & Architecture

```
Incoming User Audio / Transcript Stream [Chunk 0.0s -> 0.8s -> 1.6s -> Utterance End 2.1s]
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [1] STREAMING RETRIEVAL CONTROLLER                                     │
│  • Rolling Token Differential Monitor & Intent Stability Classifier    │
│  • Decision Engine: [Wait | Speculative Early Trigger | No-Retrieval]  │
│  • Intra-Stream Speculative Pivot: Mid-speech self-correction purge     │
└────────────────────────────────────────────────────────────────────────┘
                             │ (Early Trigger @ Token 6–8 | +1,300ms Gain)
                             ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [2] COMPOUND MULTI-INTENT DECOMPOSER                                   │
│  • Orthogonal Sub-Query Extraction via Conjunctive / Elliptical Parser │
│  • Parallel Branch Routing (Concurrent AsyncIO Dispatches)             │
│  • Cross-Turn Anaphora & Coreference Resolution ("there", "for 50")    │
└────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [3] CORPUS RETRIEVAL, FUSION & RERANKING                               │
│  • Dual-Path Hybrid Search: BM25 Okapi (Lexical) + Dense Vectors       │
│  • Reciprocal Rank Fusion (RRF) with Dynamic Normalization             │
│  • Deduplication & Cross-Encoder Precision Reranking                   │
│  • 21 Master Corporate Policy Sections ([Doc_POLICY §1–§21])           │
└────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [4] SESSION-AWARE SYNTHESIZER & GATE 0 SUPPRESSOR                      │
│  • Gate 0 Classifier: 0 vector queries on presentation formatting      │
│  • Stateful Lineage Tracker: Baseline preservation + Delta mutation    │
│  • Section Attribution Engine: Verifiable [Doc_XX §YY] citations       │
│  • Explicit Negative Uncertainty Flagging (0 Parametric Hallucination) │
└────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
   Output: Real-Time Streamed Tokens (TTFT 16ms) + Section Citations + Telemetry HUD
```

---

### 3. Detailed Component Mechanics

#### 3.1 Speculative Early Retrieval Trigger
Rather than waiting for utterance finalization, the controller monitors incoming token velocity. At a calibrated semantic stability threshold (typically token 6–8, $t \approx 0.8\text{s}$), the controller dispatches candidate retrieval speculatively. This provides a **+1,300ms retrieval head start**, reducing perceived Time to First Token (TTFT) to **16.0ms**.

#### 3.2 Intra-Stream Speculative Pivot Controller
When users correct themselves mid-sentence (*"Pune... actually Mumbai for 2 nights"*):
- The controller tracks token n-gram deltas and detects invalidation keywords (`"wait"`, `"actually"`, `"make that"`, `"instead"`).
- In-flight retrieval tasks for the obsolete entity (`Pune`) are immediately cancelled.
- Cache lines associated with the discarded branch are purged.
- A new grounded query for the updated entity (`Mumbai`) is dispatched instantaneously without restarting the session.

#### 3.3 Compound Multi-Intent Decomposer
Complex utterances (*"Plan a workshop in Pune for 30 people, check cancellation policy, and catering options"*) are deconstructed into orthogonal sub-queries:
1. `venue capacity for 30 attendees in Pune`
2. `cancellation terms and refund policies for venue reservations`
3. `on-site catering confirmation requirements`
Each sub-query executes concurrently via non-blocking AsyncIO tasks and candidate chunks are merged using Reciprocal Rank Fusion ($k=60$).

#### 3.4 Cross-Turn Context Continuity & Anaphora Resolution
Follow-up turns (*"What if it is for 50 people?"*, *"What about hotel lodging tariffs there?"*) suffer from context drift in traditional systems. Ultron maintains an in-memory entity graph tracking active geographic locations, participant headcounts, and organizational units, automatically resolving ellipses and deictic pronouns to produce enriched queries.

#### 3.5 Session Refinement (State Lineage $V_1 \to V_2$)
Late-arriving constraints (*"The trip was international and booked post-travel"*) mutate the existing answer state rather than triggering a full re-query. Baseline domestic rules are preserved, delta constraints are fetched and integrated, and the session registry increments the lineage version cleanly ($V_1 \to V_2$).

#### 3.6 Gate 0 Presentation Query Suppression
When a user asks to reformat existing context (*"Format that into two bullet points"*), the Gate 0 intent classifier detects zero informational delta. It **suppresses 100% of corpus vector queries**, immediately streaming the formatted answer while keeping factual section citations intact.

---

### 4. Data Provenance & Ingestion Schema
- **Master Corpus**: Evaluated against [policy.pdf](policy.pdf), a 3-page, 21-section master corporate policy manual.
- **Section Attribution**: Chunks are canonicalized into strict section tags (`Doc_POLICY §1` through `Doc_POLICY §21`).
- **Negative Control**: Out-of-corpus queries (e.g., naval submarine maintenance) trigger explicit uncertainty indicators with **zero fabricated document IDs**.

---

### 5. Architectural Trade-offs & Mitigations

| Trade-off | Engineering Risk | Implemented Mitigation |
|---|---|---|
| **Early Speculative Triggering** | Premature, noisy queries on incomplete thoughts | Minimum 6-token stability window + rolling entropy check |
| **Mid-Stream Invalidation** | Orphaned async tasks consuming thread pool | Strict task cancellation tokens (`asyncio.Task.cancel()`) |
| **Hybrid Search (BM25 + Dense)** | Double index lookups increasing latency | Inverted index cached in RAM; parallel vector dot-product (< 1ms) |
| **Cloud Provider Reliance** | API timeouts or rate limit exhaustion | Tri-tier fallback: Groq LPU $\to$ NVIDIA NIM $\to$ Local Qwen |

---

### 6. Telemetry & Observability Schema
Every conversational turn emits a structured JSON audit record:
```json
{
  "turn_id": 1,
  "timestamp_s": 0.8,
  "retrieval_triggers": ["speculative_early"],
  "early_retrieval_gain_ms": 1300.0,
  "ttft_ms": 16.0,
  "end_to_end_latency_ms": 40.0,
  "prompt_tokens": 80,
  "completion_tokens": 166,
  "sub_queries": [
    "workshop venues Pune 30 attendees",
    "cancellation policy venue booking",
    "catering options Pune workshop"
  ],
  "citations": ["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"],
  "session_version": "V1",
  "gate_0_suppressed": false
}
```
