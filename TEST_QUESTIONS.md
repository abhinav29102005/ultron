# Streaming Live RAG – Official 15 Evaluation Test Questions
*Comprehensive benchmark & test suite for Samsung PRISM Theme 4 Streaming Live RAG*

This document provides **15 curated test questions** covering all technical evaluation gates (G1–G9). Each test query is isolated in a copy-paste code block for instant testing via the CLI.

---

## 🚀 Quick Execution Guide

You can run these questions interactively or as one-off commands:

```bash
# Launch interactive REPL (supports multi-turn context and /rag commands):
python3 -m streaming_rag.cli --interactive

# Or run an individual question directly:
python3 -m streaming_rag.cli "<paste question here>"
```

---

## 📋 Full Test Suite (15 Test Questions)

### Part 1: Single-Intent Factual Retrieval (G4 Factual Grounding)

#### Question 1: Domestic Travel Reimbursement & Filing Deadline
> **Capability:** Single-Intent Direct Retrieval | Exact Citation Verification  
> **Expected Citation:** `[Doc_45 §1]`  
> **Expected Outcome:** Confirms 100% reimbursement on domestic travel (trains, regional economy flights, lodging) upon submission of itemized GST receipts within 30 days.

```text
What is the submission deadline and reimbursement rate for domestic employee travel expenses?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What is the submission deadline and reimbursement rate for domestic employee travel expenses?"
```
</details>

---

#### Question 2: Hotel Lodging Tariff Limits (Tier-1 Metros)
> **Capability:** Numerical Value & City Entity Grounding  
> **Expected Citation:** `[Doc_52 §2]`  
> **Expected Outcome:** Retrieves exact nightly hotel tariff cap of **INR 6,500** per night inclusive of breakfast across Tier-1 cities (Mumbai, Delhi, Bangalore, Pune).

```text
What are the nightly hotel lodging tariff caps in Tier-1 cities like Mumbai and Pune?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What are the nightly hotel lodging tariff caps in Tier-1 cities like Mumbai and Pune?"
```
</details>

---

#### Question 3: Workshop Venue Booking Cancellation Notice
> **Capability:** Temporal Policy Retrieval  
> **Expected Citation:** `[Doc_31 §4]`  
> **Expected Outcome:** Returns the mandatory **14 calendar days** advance notice requirement prior to the event date to qualify for a 100% full refund.

```text
How many days of advance notice are required to receive a 100% full refund on a workshop venue reservation?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "How many days of advance notice are required to receive a 100% full refund on a workshop venue reservation?"
```
</details>

---

#### Question 4: Dietary Accommodations Catering Notice
> **Capability:** Service Specifics & Lead-Time Retrieval  
> **Expected Citation:** `[Doc_09 §1]`  
> **Expected Outcome:** Returns that on-site buffet catering requires **72 hours advance confirmation** for special dietary accommodations (vegan, gluten-free).

```text
What is the advance confirmation notice needed for vegan or gluten-free catering accommodations?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What is the advance confirmation notice needed for vegan or gluten-free catering accommodations?"
```
</details>

---

#### Question 5: Remote Hardware Setup & Monitor Allowance
> **Capability:** Financial Stipend & Hardware Allocation Standards  
> **Expected Citation:** `[Doc_POLICY §7]`  
> **Expected Outcome:** Cites **$1,800 USD** one-time home office stipend for certified ergonomic task seating, standing desk converters, noise-canceling headsets, and up to two 4K UHD displays (or one 49-inch ultrawide).

```text
What is the home office remote equipment stipend and external monitor allocation for software engineers?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What is the home office remote equipment stipend and external monitor allocation for software engineers?"
```
</details>

---

### Part 2: Multi-Intent Compound Decomposition (G3 Multi-Intent Gate)

#### Question 6: Workshop Venue + Cancellation + Catering (3-Way Split)
> **Capability:** Compound Utterance Decomposition | Parallel Retrieval without Sequential Wait  
> **Decomposed Sub-Queries:**
> 1. `a customer workshop in Pune for 30 people` -> `[Doc_12 §2]`
> 2. `cancellation policy Pune workshop` -> `[Doc_31 §4]`
> 3. `catering options Pune workshop` -> `[Doc_09 §1]`  
> **Expected Citations:** `[Doc_12 §2]`, `[Doc_31 §4]`, `[Doc_09 §1]`  
> **Expected Outcome:** Synthesizes Pune venue capacities (Venue A / Venue B), 14-day cancellation window, and 72-hour dietary catering into a unified response.

```text
I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy and catering options.
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy and catering options."
```
</details>

---

#### Question 7: Long-Haul Flight Thresholds & Airline Disruption Vouchers
> **Capability:** Multi-Topic Travel Governance Decomposition  
> **Decomposed Sub-Queries:**
> 1. `flight duration thresholds for international business class` -> `[Doc_POLICY §1]`
> 2. `airline disruption compensation vouchers declaration in ERP` -> `[Doc_POLICY §2]`  
> **Expected Citations:** `[Doc_POLICY §1]`, `[Doc_POLICY §2]`  
> **Expected Outcome:** Explains >8 hrs Premium Economy / >11 hrs Business Class rules, plus carrier delay (>4h) voucher declaration in ERP within 14 days.

```text
What are the flight duration thresholds for international business class and how are airline disruption compensation vouchers handled?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What are the flight duration thresholds for international business class and how are airline disruption compensation vouchers handled?"
```
</details>

---

#### Question 8: Accredited AI Hackathons Cloud Grants & Open-Source IP
> **Capability:** Multi-Intent Engineering Governance  
> **Decomposed Sub-Queries:**
> 1. `cloud GPU prototyping grant for accredited AI hackathons` -> `[Doc_POLICY §5]`
> 2. `intellectual property open-source license policy for hackathons` -> `[Doc_POLICY §6]`  
> **Expected Citations:** `[Doc_POLICY §5]`, `[Doc_POLICY §6]`  
> **Expected Outcome:** Retrieves up to $1,500 USD GPU prototyping grant for Nebius H100 / Groq LPU, and default Apache 2.0 open-source licensing.

```text
What cloud GPU prototyping grants are provided for accredited AI hackathons and what is the open-source license policy?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What cloud GPU prototyping grants are provided for accredited AI hackathons and what is the open-source license policy?"
```
</details>

---

### Part 3: Multi-Turn Context Continuity & Anaphora (G7 Context Discontinuity)

*Run Questions 9, 10, and 11 sequentially in the same interactive session (`python3 -m streaming_rag.cli --interactive`) to verify context memory.*

#### Question 9: Turn 1 – Establish Session Entity Context
> **Capability:** Initial Context & Entity Anchor (`location: Pune`, `event: workshop`, `headcount: 30`)  
> **Expected Citation:** `[Doc_12 §2]`  
> **Expected Outcome:** Lists Venue A (Kalyani Nagar) and Venue B (Shivajinagar) for 30 attendees.

```text
What approved corporate workshop venues do we have for 30 attendees in Pune?
```

---

#### Question 10: Turn 2 – Anaphoric Headcount Mutation (Elliptical Query)
> **Capability:** Context Discontinuity Resolution without repeating location or event  
> **Resolved Query Internally:** `"Pune workshop venue capacity for 75 attendees"`  
> **Expected Citation:** `[Doc_POLICY §4]`  
> **Expected Outcome:** Detects that 75 attendees exceed Kalyani Nagar / Shivajinagar limits; recommends Grand Ballroom B at Pune Tech Center with $450 USD surcharge.

```text
What if the workshop headcount increases to 75 people?
```

---

#### Question 11: Turn 3 – Deictic Spatial Reference ("there")
> **Capability:** Deictic Reference Resolution (`"there" -> Pune Tier-1`)  
> **Resolved Query Internally:** `"Hotel lodging caps and per diem limits in Pune Tier-1"`  
> **Expected Citation:** `[Doc_52 §2]`  
> **Expected Outcome:** Correctly grounds Pune hotel tariff cap (INR 6,500/night) without requiring the user to restate "Pune".

```text
What about hotel lodging tariffs there?
```

---

### Part 4: Intra-Stream Speculative Invalidation (G8 Speculative Pivot)

#### Question 12: Mid-Utterance Speculative Pivot & Stale Cache Invalidation
> **Capability:** Speculative Early Trigger + Mid-Stream Correction Invalidation  
> **Streaming Flow:**  
> 1. `t=0.0s`: User speaks `"I need lodging rates for Pune..."` -> Triggers `speculative_early`  
> 2. `t=0.6s`: User pivots `"...wait, actually make that Mumbai for 2 nights."` -> Invalidate Pune cache & trigger `speculative_pivot`  
> 3. `t=1.2s`: Final transcript arrives  
> **Expected Citation:** `[Doc_52 §2]`  
> **Expected Outcome:** Final grounded answer answers for **Mumbai** lodging caps; telemetry logs both `speculative_early` and `speculative_pivot` events.

```text
I need lodging rates for Pune... wait, actually make that Mumbai for 2 nights.
```

---

### Part 5: Session Refinement & Delta Constraints (G5 Versioning)

*Run Question 13 across two turns in the interactive CLI.*

#### Question 13: Delta Constraint Refinement (Version 1 -> Version 2)
> **Capability:** Incremental Constraint Ingestion without discarding Turn 1 context  
> **Turn 1 Utterance:**
> ```text
> Summarize the travel reimbursement rule for an employee trip.
> ```
> *Answer Version 1 yields `[Doc_45 §1]` (Domestic economy, 30-day receipt deadline).*
>
> **Turn 2 Late-Arriving Constraint:**
> ```text
> The trip was international and the booking was made after travel.
> ```
> **Expected Citations (Turn 2):** `[Doc_45 §1]`, `[Doc_45 §3]`  
> **Expected Outcome:** State increments to **Version 2**. Retains Turn 1 base rule while integrating VP pre-approval requirement and post-departure non-reimbursability clause.

---

### Part 6: Presentation Query Suppression (Gate 0 / Zero Search)

#### Question 14: Restructure Prior Answer into Bullet Points
> **Capability:** Presentation Query Suppression (Gate 0)  
> **Corpus Queries Executed:** **0** (No vector or BM25 searches)  
> **Expected Citations:** Preserves prior citations (`[Doc_45 §1]`, `[Doc_45 §3]`) on every bullet  
> **Expected Outcome:** Formats the existing session answer into clean markdown bullets without citation loss or factual drift.

```text
Please format that previous response into two concise bullet points.
```

---

### Part 7: Negative Control & Uncertainty Flagging (Zero Hallucination)

#### Question 15: Out-of-Corpus Query (Missing Evidence Detection)
> **Capability:** Hallucination Suppression & Explicit Uncertainty Flagging  
> **Corpus Evidence:** **0 matching chunks**  
> **Expected Citation:** None (0 fabricated citations)  
> **Expected Outcome:** Explicitly reports:  
> `"Policies or documentation for 'What is the submarine propeller maintenance protocol for deep-sea naval fleets?' could not be verified from the retrieved corpus."`

```text
What is the submarine propeller maintenance protocol for deep-sea naval fleets?
```

<details>
<summary><b>Verify CLI One-Liner</b></summary>

```bash
python3 -m streaming_rag.cli "What is the submarine propeller maintenance protocol for deep-sea naval fleets?"
```
</details>

---

## ⚡ Quick-Copy Raw Text List (All 15 Questions)

For rapid batch execution or testing, copy from this raw list:

```text
1. What is the submission deadline and reimbursement rate for domestic employee travel expenses?
2. What are the nightly hotel lodging tariff caps in Tier-1 cities like Mumbai and Pune?
3. How many days of advance notice are required to receive a 100% full refund on a workshop venue reservation?
4. What is the advance confirmation notice needed for vegan or gluten-free catering accommodations?
5. What is the home office remote equipment stipend and external monitor allocation for software engineers?
6. I need to plan a customer workshop in Pune for 30 people, and I need the cancellation policy and catering options.
7. What are the flight duration thresholds for international business class and how are airline disruption compensation vouchers handled?
8. What cloud GPU prototyping grants are provided for accredited AI hackathons and what is the open-source license policy?
9. What approved corporate workshop venues do we have for 30 attendees in Pune?
10. What if the workshop headcount increases to 75 people?
11. What about hotel lodging tariffs there?
12. I need lodging rates for Pune... wait, actually make that Mumbai for 2 nights.
13. The trip was international and the booking was made after travel.
14. Please format that previous response into two concise bullet points.
15. What is the submarine propeller maintenance protocol for deep-sea naval fleets?
```

---

## 📊 Summary of Evaluation Gates Covered

| Gate | Description | Questions Testing This Gate | Status |
|:---|:---|:---|:---|
| **G1** | Reproducibility (Automated CLI execution) | All Q1–Q15 | ✅ PASS |
| **G2** | Early Retrieval Triggering (>=800ms gain) | Q6, Q12 | ✅ PASS |
| **G3** | Multi-Intent Identification (>=2 orthogonal sub-queries) | Q6, Q7, Q8 | ✅ PASS |
| **G4** | Factual Grounding & Section Citations (`[Doc_XX §YY]`) | Q1–Q5 | ✅ PASS |
| **G5** | Session Refinement & Delta Constraints (V1 -> V2) | Q13 | ✅ PASS |
| **G6** | Telemetry & Observability (100% trace capture) | Accessible via `/rag telemetry` | ✅ PASS |
| **G7** | Context Discontinuity & Anaphora Resolution | Q9 -> Q10 -> Q11 | ✅ PASS |
| **G8** | Intra-Stream Speculative Invalidation (Pivot) | Q12 | ✅ PASS |
| **G0** | Presentation Query Suppression (Zero vector queries) | Q14 | ✅ PASS |
| **NC** | Negative Control & Uncertainty Flagging | Q15 | ✅ PASS |
