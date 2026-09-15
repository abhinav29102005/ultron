# ULTRON Streaming RAG Architecture

## Overview

ULTRON implements a 5-component speculative streaming RAG pipeline that eliminates dead-air latency by triggering corpus retrieval *before* the user finishes speaking.

## Architecture Diagram

```
Incoming Audio/Transcript Stream:
[Chunk 0.0s] ──► [Chunk 0.8s] ──► [Chunk 1.6s] ──► [Utterance End 2.1s]
      │                 │
      ▼                 ▼ S(t)>=0.80 → RETRIEVE_EARLY
┌─────────────────────────────────────────┐
│  COMPONENT 1: RETRIEVAL CONTROLLER      │
│  Semantic Stability Score S(t)∈[0,1]    │
│  Token entropy + trailing-prep penalty  │
│  Decision: WAIT | RETRIEVE_EARLY | SUPPRESS │
└──────────────────┬──────────────────────┘
                   │ RETRIEVE_EARLY
                   ▼
┌─────────────────────────────────────────┐
│  COMPONENT 2: MULTI-INTENT DECOMPOSER   │
│  Splits compound utterances             │
│  → [Q1: venue capacity]                 │
│  → [Q2: cancellation policy]            │
│  → [Q3: catering options]               │
└──────────────────┬──────────────────────┘
                   │ Parallel Sub-Queries
                   ▼
┌─────────────────────────────────────────┐
│  COMPONENT 3: HYBRID RETRIEVAL + RRF    │
│  Web search (BM25-style lexical)        │
│  Weaviate vector search (dense)         │
│  RRF(k=60) fusion + deduplication      │
│  Cross-encoder reranker (OpenAI/lexical)│
└──────────────────┬──────────────────────┘
                   │ Grounded doc chunks
                   ▼
┌─────────────────────────────────────────┐
│  COMPONENT 4: SESSION-AWARE SYNTHESIZER │
│  [Doc_XX §YY] strict citations only     │
│  Uncertainty flag when no doc_id        │
│  V1 → V2 delta versioning              │
│  Session state preserved across turns  │
└──────────────────┬──────────────────────┘
                   ▼
┌─────────────────────────────────────────┐
│  COMPONENT 5: TELEMETRY ENGINE          │
│  TelemetryTrace Pydantic model          │
│  Per-session JSONL append              │
│  Fields: early_retrieval_gain_ms,       │
│  stream_duration_s, token budgets       │
└─────────────────────────────────────────┘
```

## Component Details

### C1: Retrieval Controller (`intelligence/retrieval_controller.py`)

**Semantic Stability Score S(t):**
- Token frequency entropy: `H = -Σ p_i * log2(p_i)`
- Normalized: `S(t) = 1 - H/H_max`
- Trailing preposition penalty: `-0.25`
- Mid-word penalty: `-0.10`
- Trigger threshold: `S(t) >= 0.80 → RETRIEVE_EARLY`
- Presentation suppressor: `{bullet, short, summar, translate, repeat} → SUPPRESS`

**Latency benefit:** Trigger at t=0.8s vs utterance end at t=2.1s = **1,300ms gain**.

### C2: Decomposer (`intelligence/decomposer.py`)

Splits on `,`, `;`, ` and ` separators. Emits `DecomposedQueryEvent` with orthogonal sub-queries dispatched in parallel.

### C3: Hybrid Retriever (`intelligence/hybrid_retriever.py`)

- **Web tier:** `WebSkill.search()` → parallel sub-query fetches
- **Vector tier:** `WeaviateClientWrapper.vector_search()` (dense embeddings via OpenAI or nearText)
- **Fusion:** `_rrf_fuse(ranked_lists, k=60)` — RRF merges by URL key, deduplicates
- **Reranker:** `CrossEncoderReranker` — OpenAI scoring with lexical fallback

### C4: Synthesizer (`intelligence/synthesizer.py`)

- Strict grounding: only emits `[Doc_XX §YY]` when `doc_id` + `section` metadata present
- Uncertainty path: returns explicit disclaimer when corpus has no evidence
- Session versioning: `_sessions[session_id]["version"]` incremented per retrieval
- Delta querying: second retrieval on same session → V2 with updated citations

### C5: Telemetry (`intelligence/telemetry.py` + `intelligence/models.py`)

- `TelemetryTrace` Pydantic model: session_id, trace_id, stream_duration_s, early_retrieval_gain_ms, total_latency_ms, prompt/completion tokens, events list
- Append-only JSONL per session: `logs/telemetry_{session_id}.jsonl`

## Design Trade-offs

| Decision | Rationale |
|---|---|
| Token entropy stability (not LLM) | 0.2ms vs 350ms for LLM agent — preserves latency budget |
| RRF over concat | Eliminates duplicate chunks across parallel sub-queries |
| JSONL append | Zero-loss telemetry even on crash; readable without parsing full file |
| Uncertainty flag over hallucination | Strict grounding requirement from plan1.md §2.1 |
