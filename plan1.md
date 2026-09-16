# Streaming Live RAG: Samsung Theme 4 Architecture & Implementation Plan

## Executive Summary & Challenge Overview

This implementation plan is built directly from the **Samsung Electronics (Device eXperience CTO / Samsung Research) Theme 4: Streaming Live RAG Guide**.

### The Core Problem
Traditional conversational RAG operates in a rigid sequential loop: **Wait for silence → Finalize transcription → Formulate search query → Retrieve corpus chunks → Synthesize response**.
In conversational voice and real-time support, this causes:
1. **Unacceptable Conversational Latency** (several seconds of dead air).
2. **Context Annihilation on Late-Arriving Constraints** (e.g., *"Actually, the trip was international"* causes naive systems to wipe session history or re-retrieve the entire corpus from scratch).
3. **Wasted Retrieval on Presentation Changes** (e.g., *"Summarize that in 2 bullets"* triggers unnecessary vector searches).
4. **Hallucination & Weak Grounding** (citing non-existent documents or answering from ungrounded parametric model weights).

### The Target Challenge
Build an end-to-end, reproducible **Streaming Live RAG Pipeline** that:
1. **Listens Incrementally**: Evaluates timestamped transcript chunks (e.g. `0.0s`, `0.8s`, `1.6s`, `2.1s`) and speculatively triggers retrieval *before* the user finishes speaking.
2. **Decomposes Multi-Intent Queries**: Splits compound utterances into discrete, parallelizable sub-queries.
3. **Refines on Late Details (Delta Querying)**: Mutates and updates existing responses and citations incrementally without restarting.
4. **Suppresses Presentation Queries**: Recognizes formatting/re-styling requests and uses existing session context without corpus hits.
5. **Strict Grounding & Citation Traceability**: Guarantees zero hallucinated citations (`[Doc_ID §Section]`), with explicit uncertainty indicators for unverified claims.

---

## 1. System Architecture

```
Incoming Audio/Transcript Stream:
[Chunk 0.0s] ────────► [Chunk 0.8s] ────────► [Chunk 1.6s] ────────► [Utterance End 2.1s]
      │                      │                      │
      ▼                      ▼                      ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        COMPONENT 1: RETRIEVAL CONTROLLER                               │
│  • Intent Semantic Stability Evaluator (Token Entropy / Boundary Classifier)           │
│  • Decision Matrix: [WAIT | RETRIEVE_EARLY | NO_RETRIEVAL_SUPPRESS]                   │
│  • Presentation Query Suppressor (formatting, summarization, tone shifts)             │
└────────────────────────────────────┬───────────────────────────────────────────────────┘
                                     │ Trigger = RETRIEVE_EARLY
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     COMPONENT 2: MULTI-INTENT DECOMPOSER                               │
│  • Compound Utterance Dissector (isolates orthogonal sub-intents)                      │
│  • Sub-Query Generator (e.g. Q1: Venue capacity, Q2: Cancellation, Q3: Catering)       │
│  • Parallel Dispatcher                                                                │
└────────────────────────────────────┬───────────────────────────────────────────────────┘
                                     │ Parallel Sub-Queries
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                 COMPONENT 3: CORPUS RETRIEVAL & EVIDENCE FUSION                        │
│  • Hybrid Search Engine: Dense Embeddings + BM25 Sparse Search                         │
│  • Reciprocal Rank Fusion (RRF) & Semantic Deduplication                               │
│  • Cross-Encoder Reranker (top-K dense factual relevance)                              │
│  • Strict Document Provenance Registry (`Doc_XX §YY`)                                  │
└────────────────────────────────────┬───────────────────────────────────────────────────┘
                                     │ Grounded Evidence Chunks
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│              COMPONENT 4: SESSION-AWARE SYNTHESIZER & REFINEMENT                       │
│  • Incremental Response Generator with Exact Citations                                 │
│  • Late-Arriving Detail Resolver (Delta Queries only; preserves Version 1 context)     │
│  • Answer Version Lineage Manager (Version 1 → Version 2)                              │
│  • Explicit Uncertainty & Clarification Flagger (Zero Parametric Hallucination)        │
└────────────────────────────────────┬───────────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     COMPONENT 5: TELEMETRY & OBSERVABILITY ENGINE                      │
│  • End-to-End Latency Tracking (Early retrieval gain vs sequential baseline)          │
│  • Structured JSON Event Logging (`retrieval_events`, `sub_queries`, `citations`)      │
│  • Token Cost & Version Lineage Auditing                                               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Hard Engineering Rules & Constraints (Non-Negotiable)

1. **Zero Parametric Hallucination**:
   - Only facts explicitly contained in the provided corpus may be used for factual assertions.
   - External web search, unindexed model memory, or fabricated document IDs are strictly forbidden.
2. **Strict Citation Granularity**:
   - Every factual sentence must cite its exact source chunk format: `[Doc_ID §Section]`.
   - Any assertion lacking corpus support must trigger an explicit uncertainty notice:
     `"uncertainty": "Catering accommodation policies could not be verified from the retrieved corpus."`
3. **Session-Bound State (Ephemeral)**:
   - Memory is strictly ephemeral and scoped to the active conversation session.
   - Cross-session profiling, persistent user cookies, or disk-persisted tracking across independent test runs are prohibited.
4. **Architectural Parsimony**:
   - Avoid heavy multi-agent overhead or endless loop iterations. Evaluated on **cost-to-performance efficiency** and runtime latency.
5. **No Hardcoded Logic**:
   - Prompts, classifiers, and decomposers must generalize across unseen corpora and held-out test sets.

---

## 3. Technical Evaluation Gates (G1 to G6) & Target Thresholds

| Gate | Criterion | Target Threshold | Implementation & Validation Strategy |
|------|-----------|------------------|---------------------------------------|
| **G1** | **Reproducibility** | **Pass / Fail** | Single command launch via `docker compose up` or `bash run_benchmark.sh`. Automated test replay completes without manual human input. |
| **G2** | **Early Retrieval Triggering** | **$\ge$ 80% of eligible queries** | Retrieval commences prior to final transcript completion on held-out streaming prompts. False-trigger rate on no-retrieval / incomplete thoughts $< 10\%$. |
| **G3** | **Multi-Intent Identification** | **$\ge$ 70% of compound queries** | Correctly detects and extracts $\ge 2$ distinct orthogonal sub-queries from compound utterances without conversational drift or over-fragmentation. |
| **G4** | **Factual Grounding & Citations** | **$\ge$ 85% citation support** | 100% of sampled assertions backed by cited chunks. **Zero fabricated document IDs** (`Doc_999`). |
| **G5** | **Session Refinement** | **Verified state continuity** | Late-arriving constraints mutate/update existing answer (`Version 1 → Version 2`) via delta query, preserving prior valid citations and context. |
| **G6** | **Telemetry & Observability** | **100% trace coverage** | Real-time JSON structured telemetry logging: timestamps, latency savings, retrieval triggers, sub-queries, citations, version lineage, token cost. |

---

## 4. Input & Output Event Schema Specifications

### Incremental Stream Processing (Example 1)
- `t = 0.0s`: `"I need to plan a customer workshop in..."`
  $\rightarrow$ **Decision**: `WAIT` (Incomplete thought, semantically unstable. No retrieval).
- `t = 0.8s`: `"...Pune for 30 people, and I need..."`
  $\rightarrow$ **Decision**: `RETRIEVE_EARLY` (Intent: Pune workshop venue capacity 30). Dispatch initial vector/hybrid search. Log `retrieval_started`.
- `t = 1.6s`: `"...the cancellation policy and the catering options."`
  $\rightarrow$ **Decision**: `DECOMPOSE_AND_PARALLEL_RETRIEVE`. Generate 3 sub-queries:
    1. *"Venue capacity for 30 attendees in Pune"*
    2. *"Cancellation terms and refund policies"*
    3. *"On-site and external catering options"*
- `t = 2.1s`: `[Utterance End]`
  $\rightarrow$ **Synthesize**: Stream unified answer with citations (`[Doc_12 §2]`, `[Doc_31 §4]`, `[Doc_09 §1]`) + explicit uncertainty indicator if catering is unverified.

### Structured Output Record Schema (JSON)
```json
{
  "session_id": "sess_live_9823",
  "answer_version": 1,
  "telemetry": {
    "stream_duration_s": 2.1,
    "retrieval_trigger_timestamp_s": 0.8,
    "early_retrieval_gain_ms": 1300,
    "total_latency_ms": 1820,
    "prompt_tokens": 842,
    "completion_tokens": 164
  },
  "retrieval_events": [
    {
      "timestamp_s": 0.8,
      "query": "Pune workshop venue capacity 30",
      "trigger": "speculative_early"
    },
    {
      "timestamp_s": 1.6,
      "query": "cancellation policy workshop venues Pune",
      "trigger": "multi_intent"
    },
    {
      "timestamp_s": 1.6,
      "query": "catering service options workshop Pune",
      "trigger": "multi_intent"
    }
  ],
  "sub_queries": [
    "venue capacity for 30 attendees in Pune",
    "cancellation terms and refund policies",
    "on-site and external catering options"
  ],
  "answer": "For a 30-person workshop in Pune, documented venues include Venue A and Venue B [Doc_12 §2]. Cancellation requires 14 days notice for a full refund [Doc_31 §4].",
  "citations": [
    "Doc_12 §2",
    "Doc_31 §4"
  ],
  "uncertainty": "Catering accommodation policies for Venue A could not be verified from the retrieved corpus."
}
```

### Late-Arriving Detail Refinement (Example 2)
- **Step 1 (Initial)**: *"Summarize the travel reimbursement rule for an employee trip."*
  $\rightarrow$ Retrieves base policy guidelines. Emits cited summary + creates `Answer Version 1` in session memory.
- **Step 2 (Late Detail)**: *"The trip was international and the booking was made after travel."*
  $\rightarrow$ **Refine, Do Not Restart**: Recognize delta constraints. Dispatches targeted query: *"international travel reimbursement late booking exception"*.
- **Step 3 (Refined Response)**: Emits `Answer Version 2`.
  $\rightarrow$ Preserves prior base citations, appends late-booking delta citations, updates answer without full re-indexing.

### Presentation Query Suppression (Example 3)
- **User Input**: *"Please repeat your last answer in two bullets."*
- **Controller Evaluation**:
  ```json
  {
    "retrieval_required": false,
    "reason": "presentation_restructure"
  }
  ```
- **System Behavior**: Reformats existing session context into 2 bullet points. **Zero vector search or corpus queries executed**. Retains existing citations without hallucinating new ones.

---

## 5. Integrating with Ultron Agent Architecture

ULTRON Agent provides existing building blocks that directly accelerate this build:

1. **Streaming Audio & VAD**:
   - `core/assistant.py` and `speech/` (Faster Whisper + Silero VAD) provide real-time token/word stream with microsecond timestamps.
2. **Dual LLM Tiering**:
   - NVIDIA NIM (`nemotron-3-super-120b`) for rapid speculative decomposition + local Ollama (`qwen3:4b-instruct`) for lightweight intent boundary classification.
3. **Research & Retrieval Subsystem**:
   - `skills/research_skill.py` already implements chunk parsing, evidence scoring, and citation generation. We adapt this into a streaming Hybrid Retriever.
4. **Session Memory**:
   - Ephemeral session state manager adapts `memory/` and `utils/record_store.py` to hold versioned conversation turns and evidence caches.

---

## 6. Detailed 3-Person Team Allocation

| Person | Focus Area | Detailed Deliverables |
|--------|------------|-----------------------|
| **Person A** | **Streaming Controller & Simulator** | 1. **Live Stream Simulator**: Feeds timestamped transcript chunks (`0.0s`, `0.8s`, etc.) from audio/text datasets.<br>2. **Intent Stability Classifier**: Rule + lightweight model classifier to decide `WAIT`, `RETRIEVE_EARLY`, or `SUPPRESS`.<br>3. **Presentation Suppressor**: Detects reformatting, summarization, and translation turns.<br>4. **Early Retrieval Metrics**: Measures timestamp gains ($t_{\text{final}} - t_{\text{trigger}}$) for Gate G2. |
| **Person B** | **Corpus Indexing, Hybrid Retrieval & Fusion** | 1. **Corpus Ingestion & Chunking**: Optimized chunking preserving document headers (`Doc_XX §YY`).<br>2. **Hybrid Engine**: Fast BM25 (sparse) + Chroma/Qdrant/FAISS dense embeddings.<br>3. **RRF & Deduplication**: Reciprocal Rank Fusion to merge parallel sub-query results without inflating context windows.<br>4. **Cross-Encoder Reranker**: Rapid reranking for maximum factual density. |
| **Person C** | **Multi-Intent Decomposition, Refinement & Synthesis** | 1. **Multi-Intent Decomposer**: Extracts orthogonal sub-queries from compound sentences (Gate G3).<br>2. **Session-Aware Synthesizer**: Produces grounded text with exact section citations (Gate G4).<br>3. **Late-Constraint Resolver**: Delta query generation and version management (`Version 1 → Version 2`) (Gate G5).<br>4. **Uncertainty Flagger**: Emits explicit uncertainty when evidence is missing. |

---

## 7. Phased Build Plan & Timeline

### Phase 1: Framing & Foundation (Hours 0 – 8)
- [x] Audit evaluation corpus and chunking format (`Doc_ID §Section`).
- [x] Build baseline hybrid retrieval pipeline (BM25 + Dense Embeddings).
- [x] Define rigid JSON schemas for `ControllerDecision`, `RetrievalEvent`, `StructuredOutputRecord`, and `TelemetryLog`.

### Phase 2: Streaming Controller & Live Simulator (Hours 8 – 16)
- [x] Implement streaming transcript feeder simulator (mimicking real-time ASR emissions at 200–500ms intervals).
- [x] Implement intent stability scoring (wait for semantic noun/verb phrase stabilization).
- [x] Implement early retrieval triggering and log speculative latency savings (targeting Gate G2 $\ge 80\%$).
- [x] Add presentation query detector (zero retrieval for reformatting).

### Phase 3: Multi-Intent Parsing & Evidence Fusion (Hours 16 – 26)
- [x] Implement query decomposition prompt/engine to split compound requests into parallel sub-queries (targeting Gate G3 $\ge 70\%$).
- [x] Dispatch parallel asynchronous searches.
- [x] Implement Reciprocal Rank Fusion (RRF) and deduplicate chunks across sub-queries.

### Phase 4: Session Refinement & Grounded Synthesis (Hours 26 – 36)
- [x] Build ephemeral session context memory (retaining prior answers, citations, and retrieved chunk IDs).
- [x] Implement delta query handler for late-arriving constraints (preserving existing context, incrementing version).
- [x] Build strict grounding verification: check every output claim against cited text; emit explicit uncertainty if missing (targeting Gate G4 $\ge 85\%$).

### Phase 5: Telemetry, Benchmarking, Ablations & Packaging (Hours 36 – 48)
- [x] Instrument end-to-end telemetry (trace coverage 100% for Gate G6).
- [x] Run full automated evaluation suite comparing against sequential baseline RAG.
- [x] Conduct 2 mandatory architectural ablation experiments:
  - Ablation 1: Hybrid (Dense + BM25) vs. Dense-Only retrieval.
  - Ablation 2: Rule-based heuristic controller vs. LLM-based controller.
- [x] Document 3 edge-case failure modes and mitigations.
- [x] Package into single-command Docker runner (`docker compose up`) (Gate G1).
- [x] Record 5-minute system demonstration video and write 6-page Architecture Brief.

---

## 8. Engineering Deliverables Checklist

- [x] **Reproducible Repository**: Clean CLI runner (`run_benchmark.sh`), Docker runner (`docker-compose.yml` / `Dockerfile`), locked dependencies (`pyproject.toml` / `uv.lock`), clean config templates.
- [x] **System Architecture Brief ($\le$ 6 pages)**: Comprehensive design brief at [`docs/STREAMING_RAG_ARCHITECTURE.md`](docs/STREAMING_RAG_ARCHITECTURE.md).
- [x] **Benchmarking & Evaluation Report**: Detailed quantitative evaluation and ablation report at [`docs/STREAMING_RAG_BENCHMARK.md`](docs/STREAMING_RAG_BENCHMARK.md).
  - Quantitative comparison vs. sequential baseline (Latency, F1 Grounding, Early Retrieval %).
  - 3 analyzed edge-case failure modes.
  - 2 ablation experiments (Hybrid vs Dense, Rule vs Model Controller).
- [x] **System Demonstration Flow & Script**: Interactive 5-scenario demo runner at [`scripts/demo_streaming_rag.py`](scripts/demo_streaming_rag.py) executing all 5 visual flows (ready for screen recording).
- [x] **Telemetry & Observability Schema**: Structured JSON Pydantic schemas in [`intelligence/models.py`](intelligence/models.py) and [`intelligence/telemetry.py`](intelligence/telemetry.py) logging end-to-end timestamps, speculative gains, retrieval events, version lineage, and token metrics.
