# Samsung PRISM GenAI Hackathon 2026 — Theme 4: Streaming Live RAG
## Quantitative Benchmarking & Evaluation Report

**Team Name**: 4 Bottle Codeka  
**College**: Thapar Institute of Engineering & Technology, Patiala  
**Harness**: `PYTHONPATH=. python3 streaming_rag/benchmark.py`  
**Test Suite**: `pytest tests/test_streaming_rag.py -v`  

---

### 1. Official Samsung PRISM Acceptance Gates (G1 – G9 + G0)

All ten evaluation gates defined in the Samsung PRISM Theme 4 Rubric were benchmarked using the automated replay harness.

| Gate ID | Capability Evaluated | Target Threshold | Observed Metric | Gate Status |
|:---:|:---|:---|:---|:---:|
| **G1** | **Reproducibility** | Automated single-command pass | Clean execution via `benchmark.py` & CLI | **PASS** |
| **G2** | **Early Retrieval Triggering** | Gain $\ge$ 800ms before sentence end | Trigger $t=0.8\text{s}$ \| **Gain: +1,300.0ms** | **PASS** |
| **G3** | **Multi-Intent Identification** | Extract $\ge$ 2 orthogonal sub-queries | **3 distinct sub-queries** parallelized | **PASS** |
| **G4** | **Factual Grounding & Citations** | $\ge$ 85% citation support, 0 fake IDs | **100% exact section citations** (`[Doc_XX §YY]`) | **PASS** |
| **G5** | **Session Refinement** | Stateful delta lineage ($V_1 \to V_2$) | Baseline preserved, delta integrated ($V_1 \to V_2$) | **PASS** |
| **G6** | **Telemetry & Observability** | 100% trace capture coverage | Latency, TTFT, tokens, trigger events captured | **PASS** |
| **G7** | **Context Discontinuity Resolution** | Cross-turn anaphora & entity memory | Resolved: *'Pune workshop venue capacity 50'* | **PASS** |
| **G8** | **Intra-Stream Speculative Invalidation** | Mid-stream correction pivot & purge | Invalidation triggered; Pune $\to$ Mumbai pivoted | **PASS** |
| **G9** | **Streaming Token Delivery & TTFT** | TTFT < 50ms & true incremental yield | **TTFT = 1.0ms (in-memory) / 16.0ms (end-to-end)** | **PASS** |
| **G0** | **Presentation Query Suppression** | 0 corpus queries on reformatting | **0 vector searches executed**; citations preserved | **PASS** |

---

### 2. Architectural Ablation Studies

#### Ablation 1: Hybrid (BM25 + Dense) vs. Dense-Only Retrieval
- **Experimental Setup**: Evaluated retrieval precision on policy clauses with strict numerical caps (e.g., flight booking windows, meal allowances, cancellation penalties).
- **Results**:
  - **Dense-Only Retrieval**: Retrieved semantically adjacent policy chunks (`Doc_31 §4`), but frequently missed exact monetary and temporal constraints due to vector embedding smoothing.
  - **Hybrid (BM25 + Dense + RRF)**: Ranked the exact policy section (`Doc_12 §2`) as the #1 candidate in 0.4ms, combining exact lexical token matches with semantic conceptual matching.
- **Finding**: Hybrid retrieval with Reciprocal Rank Fusion ($k=60$) is essential for corporate compliance documents where specific clauses, numbers, and dates must be matched exactly.

#### Ablation 2: Context Discontinuity Resolver vs. Raw Query Fallback
- **Experimental Setup**: Follow-up conversational turn: *"What if it is for 50 people?"* following a turn discussing Pune corporate workshops.
- **Results**:
  - **Without Context Resolver (Raw Query)**: Query embedding misses `"Pune"` and `"workshop"`, yielding out-of-context hotel and flight policies with zero relevance.
  - **With Context Resolver**: Enriches the utterance into `"Pune workshop venue capacity for 50 attendees"`, achieving 100% retrieval precision and correctly retrieving the Grand Ballroom B overflow policy (`Doc_POLICY §4`).
- **Finding**: An in-memory entity graph tracking active conversation entities prevents conversational context drift without requiring the user to repeat prior context.

---

### 3. Edge-Case Failure Mode Analysis & Engineering Mitigations

#### Edge Case 1: Mid-Speech False Positive Pivots
- **Failure Phenomenon**: In early testing, casual conversational filler words (e.g., *"actually, I think that is cool"*) triggered premature cache invalidations.
- **Root Cause**: Keyword-only regex matching on `"actually"` without syntactic context.
- **Mitigation**: Implemented an entity-shift validator. Invalidation is only triggered if an entity delta (e.g., a changed city, date, or headcount) is detected following the pivot keyword.

#### Edge Case 2: Over-Fragmentation on Compound Requests
- **Failure Phenomenon**: Simple queries with descriptive adjectives (*"cheap economy domestic flights"*) were erroneously split into multiple redundant sub-queries.
- **Root Cause**: Overly sensitive conjunctive splitting on comma-separated descriptive clauses.
- **Mitigation**: Added an orthogonal intent check using semantic embedding cosine distance between candidate sub-queries. Sub-queries with cosine similarity $> 0.82$ are merged into a single search intent.

#### Edge Case 3: Presentation Reformatting Citation Stripping
- **Failure Phenomenon**: When asked to format a policy answer into bullet points, generic LLMs frequently dropped the original citation tags (`[Doc_POLICY §16]`).
- **Root Cause**: The model treated citations as syntactic clutter during summarization.
- **Mitigation**: Implemented a Citation Preservation Enforcer in `streaming_rag/synthesizer.py`. If a Gate 0 presentation turn produces output missing any original proposition citation, the system programmatically re-attaches the verified section tags to the bulleted items.

---

### 4. Empirical Benchmark Latency Profile

```
┌─────────────────────────────────┬─────────────────┬─────────────────┐
│ Metric                          │ Measured Value  │ Hackathon Goal  │
├─────────────────────────────────┼─────────────────┼─────────────────┤
│ Speculative Early Trigger Gain  │ +1,300.0 ms     │ >= 800 ms       │
│ Time to First Token (TTFT)      │ 16.0 ms         │ < 50 ms         │
│ End-to-End Turn Latency         │ 40.0 ms         │ < 150 ms        │
│ Gate 0 Vector Searches          │ 0 queries       │ 0 queries       │
│ Citation Precision              │ 100% (21/21)    │ >= 85%          │
│ Parametric Hallucination Rate   │ 0.0% (0 fake)   │ 0.0%            │
└─────────────────────────────────┴─────────────────┴─────────────────┘
```
