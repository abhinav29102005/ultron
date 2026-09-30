"""
streaming_rag/corpus.py – Official Enterprise & Samsung PRISM Theme 4 Corpus Registry
====================================================================================
Provides formal, verified factual document chunks formatted strictly as [Doc_ID §Section].
Includes official enterprise operations governance, airline and travel policies,
conference/workshop venue directories, remote hardware standards, and Samsung PRISM Theme 4
Streaming Live RAG specifications.
"""

from __future__ import annotations

from typing import List
from streaming_rag.models import DocumentChunk


MASTER_CORPUS: List[DocumentChunk] = [
    # ── Enterprise Operations & Venue Specifications ──────────────────────────
    DocumentChunk(
        doc_id="Doc_12",
        section="§2",
        title="Event Spaces & Venue Directory - Pune Region",
        text="For corporate workshops of up to 30 attendees in Pune, documented approved facilities include Venue A (Kalyani Nagar) and Venue B (Shivajinagar), both featuring interactive projectors and high-speed fiber connectivity.",
        metadata={"region": "Pune", "category": "Venues", "capacity": 30}
    ),
    DocumentChunk(
        doc_id="Doc_31",
        section="§4",
        title="Corporate Workshop Booking and Cancellation Policy",
        text="All confirmed venue reservations require a minimum of 14 calendar days advance notice prior to the scheduled start date to qualify for a 100% full refund.",
        metadata={"topic": "Cancellation", "policy": "Refunds"}
    ),
    DocumentChunk(
        doc_id="Doc_09",
        section="§1",
        title="Approved Catering Services and Dietary Accommodations",
        text="On-site buffet catering is provided directly by authorized partner caterers, with special dietary accommodations (vegan, gluten-free) requiring 72 hours advance confirmation.",
        metadata={"topic": "Catering", "lead_time_hours": 72}
    ),

    # ── Enterprise Travel, Flight & Per-Diem Governance ───────────────────────
    DocumentChunk(
        doc_id="Doc_45",
        section="§1",
        title="General Employee Travel Reimbursement Guidelines",
        text="Standard domestic employee travel expenses, including intercity trains, regional economy flights, and standard lodging, are eligible for 100% reimbursement upon submission of itemized GST receipts within 30 days.",
        metadata={"category": "Travel", "scope": "Domestic"}
    ),
    DocumentChunk(
        doc_id="Doc_45",
        section="§3",
        title="International Travel Approvals and Late Booking Exception Policy",
        text="International employee trips require prior VP-level written approval; bookings made post-departure or after travel completion are strictly non-reimbursable unless an emergency operational waiver is issued by HR and Finance.",
        metadata={"category": "Travel", "scope": "International", "exception": "Late Booking"}
    ),
    DocumentChunk(
        doc_id="Doc_52",
        section="§2",
        title="Hotel Lodging Caps and Per Diem Limits",
        text="Nightly hotel tariffs in Tier-1 cities (Mumbai, Delhi, Bangalore, Pune) are capped at INR 6,500 per night inclusive of breakfast.",
        metadata={"category": "Lodging", "tier": "Tier-1"}
    ),

    # ── Samsung PRISM Theme 4: Streaming Live RAG Specifications ──────────────
    DocumentChunk(
        doc_id="Doc_SAM_01",
        section="§1",
        title="Samsung PRISM Theme 4: Streaming Live RAG Problem Scope & Architecture",
        text="The Samsung PRISM Theme 4 Streaming Live RAG challenge requires building a low-latency conversational RAG system that processes streaming audio/text transcripts incrementally, triggers speculative retrieval before the user finishes speaking, isolates multi-intent compound queries, and avoids sequential wait latency.",
        metadata={"domain": "Samsung", "theme": "Theme 4", "topic": "Problem Scope"}
    ),
    DocumentChunk(
        doc_id="Doc_SAM_02",
        section="§1",
        title="Samsung PRISM Theme 4: Technical Evaluation Gates (G1 to G6) & Target Thresholds",
        text="Samsung Theme 4 evaluation requires passing six technical gates: Gate G1 Reproducibility (automated single-command execution), Gate G2 Early Retrieval Triggering (commencing retrieval before utterance end on >=80% of eligible queries with >=800ms latency gain), Gate G3 Multi-Intent Identification (extracting >=2 orthogonal sub-queries on >=70% of compound utterances), Gate G4 Factual Grounding (>=85% citation support with 0 fabricated document IDs), Gate G5 Session Refinement (verified state continuity V1 -> V2 on late constraints), and Gate G6 Telemetry & Observability (100% trace capture of latency and token metrics).",
        metadata={"domain": "Samsung", "theme": "Theme 4", "topic": "Evaluation Gates"}
    ),
    DocumentChunk(
        doc_id="Doc_SAM_02",
        section="§2",
        title="Samsung PRISM Theme 4: Hard Engineering Rules & Constraints",
        text="Samsung Theme 4 mandates zero parametric hallucination where all factual assertions must cite exact source chunks formatted as [Doc_ID §Section], explicit uncertainty flags when corpus evidence is missing, strictly session-bound ephemeral state without cross-session leakage, architectural parsimony avoiding heavy multi-agent loops, and Gate 0 presentation query suppression where reformatting or summarization requests execute zero corpus vector queries.",
        metadata={"domain": "Samsung", "theme": "Theme 4", "topic": "Engineering Rules"}
    ),
    DocumentChunk(
        doc_id="Doc_SAM_03",
        section="§1",
        title="Samsung PRISM Theme 4: Demonstration Flows & Deliverables",
        text="The required Samsung Theme 4 demonstration requires showcasing: 1) Speculative early retrieval with >=800ms gain, 2) Compound multi-intent decomposition into orthogonal sub-queries, 3) Factual grounding with exact section citations [Doc_XX §YY], 4) Session continuity and delta constraint refinement (Version 1 -> Version 2), 5) Presentation query suppression with zero corpus queries, and 6) Real-time telemetry logging of latency and token accounting.",
        metadata={"domain": "Samsung", "theme": "Theme 4", "topic": "Demonstration Flows"}
    ),

    # ── Enterprise Master Policy Chapters (policy.pdf) ────────────────────────
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§1",
        title="Long-Haul Flights & Business Class Approval Thresholds",
        text="International long-haul flights with continuous scheduled flight legs exceeding 8 hours qualify for Premium Economy booking; legs exceeding 11 continuous hours qualify for Business Class lie-flat seating upon Vice President written pre-approval. Post-departure ticket alterations without emergency operational waiver are fully non-reimbursable.",
        metadata={"category": "Travel", "scope": "International", "topic": "Long-Haul Flights"}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§2",
        title="Flight Delays, Disruption Compensation & Carrier Vouchers",
        text="In the event of airline cancellations or carrier delays exceeding 4 hours, employees must seek direct carrier rebooking. Airline compensation vouchers, refund checks, or hotel credits issued by commercial carriers remain legal property of the enterprise and must be declared in ERP within 14 calendar days of trip completion.",
        metadata={"category": "Travel", "topic": "Disruption"}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§3",
        title="Extended Project Stays Exceeding 14 Nights & Serviced Apartments",
        text="For project assignments, client on-sites, or hackathon residencies extending beyond 14 continuous nights in a single city, employees must transition from commercial hotels to corporate serviced apartments, capped at $4,500 USD monthly in Tier-1 cities and $2,800 USD in Tier-2 cities.",
        metadata={"category": "Lodging", "type": "Extended", "duration_days_threshold": 14}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§4",
        title="Capacity Overflow Governance, Surcharges & Grand Ballroom B",
        text="Workshops or customer roundtables expecting between 31 and 100 participants cannot be accommodated at Kalyani Nagar Venue A or Shivajinagar Venue B; they must be booked into Grand Ballroom B at the Pune Tech Center with an additional $450 USD facility surcharge covering auxiliary air conditioning, event staff, and audio engineering support.",
        metadata={"region": "Pune", "category": "Venues", "overflow_capacity": 100, "surcharge_usd": 450}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§5",
        title="Accredited AI Hackathons, Team Eligibility & Prototyping Grants",
        text="Approved engineering hackathon teams (2 to 5 full-time engineers) competing in accredited challenges such as Samsung PRISM Theme 4 or Nebius Token Factory receive a dedicated cloud GPU prototyping grant of up to $1,500 USD per team for Nebius AI Cloud H100 clusters, NVIDIA NIM endpoints, and Groq LPU instances.",
        metadata={"domain": "Hackathons", "grant_usd": 1500, "eligible": ["Samsung PRISM", "Nebius", "NeurIPS"]}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§6",
        title="Intellectual Property Governance & Default Apache 2.0 Open-Source License",
        text="All algorithmic source code, agent architectures, and hybrid retrieval indexes developed during accredited hackathons are released as open-source software under the Apache 2.0 license by default, fostering broad technological collaboration. No proprietary customer data may be included.",
        metadata={"domain": "Hackathons", "license": "Apache 2.0"}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§7",
        title="Remote Setup Grant, Ergonomic Seating & Dual 4K Monitor Allocation",
        text="Full-time remote and hybrid software engineers receive a one-time home office establishment stipend of $1,800 USD for certified ergonomic task seating, motorized standing desk converters, noise-canceling headsets, and up to two 4K UHD external displays (or one 49-inch ultrawide display).",
        metadata={"category": "Hardware", "type": "Remote Setup", "stipend_usd": 1800}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§8",
        title="Annual Peripheral Refresh Stipend & High-Performance Laptop Cadence",
        text="Beginning after 12 months continuous service, engineers receive an annual peripheral refresh budget of $350 USD for mechanical keyboards, mice, webcams, and USB-C docks. High-performance engineering workstations operate on a mandatory 36-month hardware refresh cycle.",
        metadata={"category": "Hardware", "refresh_usd": 350, "laptop_cycle_months": 36}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§9",
        title="Corporate Hardware Asset Governance, Encryption & Lost Device Audits",
        text="All computing devices and displays procured through corporate expense allocations remain company property and must be enrolled in corporate MDM with FileVault or BitLocker 256-bit AES encryption active at all times. Lost or stolen hardware must be reported to IT Security within 2 hours.",
        metadata={"category": "Hardware", "security": "AES-256", "audit_hours": 2}
    ),
    DocumentChunk(
        doc_id="Doc_POLICY",
        section="§10",
        title="Expense Claim Forfeiture Rule (30-Day Window & 60-Day Hard Forfeiture)",
        text="All employee expense claims must be submitted in the ERP financial portal within 30 calendar days of expense incurrence with itemized tax receipts. Any reimbursement claim submitted after 60 calendar days is permanently forfeited without exception.",
        metadata={"category": "Finance", "deadline_days": 30, "forfeiture_days": 60}
    ),
]

# Alias for backward compatibility
SAMPLE_CORPUS = MASTER_CORPUS
