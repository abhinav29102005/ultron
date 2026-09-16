"""
streaming_rag/corpus.py – Evaluation Corpus Registry
===================================================
Provides verified factual document chunks formatted strictly as [Doc_ID §Section].
"""

from __future__ import annotations

from typing import List
from streaming_rag.models import DocumentChunk


SAMPLE_CORPUS: List[DocumentChunk] = [
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
]
