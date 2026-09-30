#!/usr/bin/env python3
"""
scripts/test_policy_questions.py
================================
Automated and Interactive Questioning Suite for Ingested policy.pdf.
Extracts, indexes, and evaluates all chapters of policy.pdf against Samsung Theme 4 Live RAG.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from streaming_rag.ingest import interactive_ingest_flow
from streaming_rag.models import StreamingChunk
from streaming_rag.pipeline import StreamingLiveRAG
from streaming_rag.session import SessionRegistry

console = Console()

POLICY_QUESTIONS = [
    {
        "id": 1,
        "title": "Domestic Travel Reimbursement",
        "query": "What is the booking window and economy class mandate for domestic travel?",
        "expected_citation": "Doc_45 §1 or Doc_POLICY §2"
    },
    {
        "id": 2,
        "title": "Long-Haul International Business Class",
        "query": "When are employees eligible for business class on international long-haul flights?",
        "expected_citation": "Doc_POLICY §1 or Doc_POLICY §3"
    },
    {
        "id": 3,
        "title": "Flight Delay & Cancellation Vouchers",
        "query": "How are airline cancellation compensation vouchers and delay refund checks handled?",
        "expected_citation": "Doc_POLICY §2 or Doc_POLICY §4"
    },
    {
        "id": 4,
        "title": "Tier-1 Lodging Caps",
        "query": "What are the nightly hotel lodging tariff caps in Tier-1 global metros?",
        "expected_citation": "Doc_52 §2 or Doc_POLICY §5"
    },
    {
        "id": 5,
        "title": "Extended Project Stays (>14 Nights)",
        "query": "What is the accommodation requirement for project stays extending beyond 14 continuous nights?",
        "expected_citation": "Doc_POLICY §3 or Doc_POLICY §7"
    },
    {
        "id": 6,
        "title": "Pune Workshop Venues & Capacity",
        "query": "What approved workshop venues exist in Pune and what is the maximum seating capacity?",
        "expected_citation": "Doc_12 §2 or Doc_POLICY §8"
    },
    {
        "id": 7,
        "title": "Capacity Overflow to Grand Ballroom B",
        "query": "What is the procedure and surcharge if a Pune workshop expects 31 to 100 participants?",
        "expected_citation": "Doc_POLICY §4 or Doc_POLICY §9"
    },
    {
        "id": 8,
        "title": "Venue Cancellation Refund Notice",
        "query": "What is the advance notice requirement to qualify for a 100% full refund on a venue reservation?",
        "expected_citation": "Doc_31 §4 or Doc_POLICY §10"
    },
    {
        "id": 9,
        "title": "Dietary Catering Confirmation Notice",
        "query": "What is the advance confirmation lead time required for vegan or gluten-free catering?",
        "expected_citation": "Doc_09 §1 or Doc_POLICY §12"
    },
    {
        "id": 10,
        "title": "Accredited AI Hackathons Cloud GPU Grants",
        "query": "What cloud GPU prototyping grant is provided for accredited AI hackathons like Samsung PRISM Theme 4?",
        "expected_citation": "Doc_POLICY §5 or Doc_POLICY §15"
    },
    {
        "id": 11,
        "title": "Hackathon IP Open-Source Licensing",
        "query": "Under what open-source license must AI hackathon code and retrieval indexes be released?",
        "expected_citation": "Doc_POLICY §6 or Doc_POLICY §16"
    },
    {
        "id": 12,
        "title": "Remote Setup Stipend & Monitor Allocation",
        "query": "What is the home office remote equipment stipend and external monitor allocation for software engineers?",
        "expected_citation": "Doc_POLICY §7 or Doc_POLICY §17"
    },
    {
        "id": 13,
        "title": "Hardware Security Encryption & Audits",
        "query": "What encryption standard is mandatory on company laptops and what is the lost device reporting window?",
        "expected_citation": "Doc_POLICY §9 or Doc_POLICY §19"
    },
    {
        "id": 14,
        "title": "Expense Claim Hard Forfeiture Rule",
        "query": "What is the ERP submission deadline for expenses and when does permanent forfeiture occur?",
        "expected_citation": "Doc_POLICY §10 or Doc_POLICY §21"
    },
    {
        "id": 15,
        "title": "Negative Control (Uncertainty Flagging)",
        "query": "What is the submarine propeller maintenance protocol for deep-sea naval fleets?",
        "expected_citation": "Explicit Uncertainty (Missing Evidence)"
    }
]

def main():
    console.print(Panel(
        "[bold cyan]POLICY.PDF INGESTION & EVALUATION QUESTIONING[/bold cyan]\n"
        "[dim]Ingesting master policy manual and evaluating all 15 governance queries[/dim]",
        border_style="cyan"
    ))

    # Step 1: Ingest policy.pdf
    pdf_path = REPO_ROOT / "policy.pdf"
    if not pdf_path.exists():
        console.print(f"[bold red]Error: {pdf_path} not found.[/bold red]")
        sys.exit(1)

    console.print(f"[bold yellow]Step 1: Ingesting '{pdf_path.name}' into Live RAG Corpus...[/bold yellow]")
    interactive_ingest_flow(str(pdf_path))

    # Step 2: Initialize RAG with updated corpus
    rag = StreamingLiveRAG.get_instance()
    rag.reload_corpus()
    SessionRegistry.clear("policy_eval_session")

    console.print(f"\n[bold green]✓ Loaded Live RAG Engine with {len(rag.corpus)} total chunks.[/bold green]\n")

    # Step 3: Run the 15 questions
    results_table = Table(title="15 Policy Ingestion Test Questions — Evaluation Results", border_style="cyan", box=box.ROUNDED)
    results_table.add_column("Q#", justify="center", style="bold cyan", width=5)
    results_table.add_column("Topic", style="white", width=26)
    results_table.add_column("Query", style="dim", width=36)
    results_table.add_column("Citations Yielded", style="green", width=22)
    results_table.add_column("Status", justify="center", style="bold green", width=10)

    for item in POLICY_QUESTIONS:
        qid = item["id"]
        title = item["title"]
        q = item["query"]

        stream = [StreamingChunk(timestamp_s=1.0, text=q, is_final=True)]
        rec = rag.process_stream(stream, session_id=f"policy_eval_turn_{qid}")

        citations_str = ", ".join(rec.citations) or "None"
        status = "FLAGGED" if rec.uncertainty else "GROUNDED"

        results_table.add_row(str(qid), title, q[:33] + "...", citations_str, status)

        # Print detailed individual result card
        console.print(f"[bold cyan]Q{qid}: {title}[/bold cyan]")
        console.print(f"  [dim]Query:[/dim] [white]\"{q}\"[/white]")
        console.print(f"  [dim]Answer:[/dim] {rec.answer[:160]}...")
        console.print(f"  [dim]Citations:[/dim] [bold green]{rec.citations}[/bold green]")
        if rec.uncertainty:
            console.print(f"  [dim]Uncertainty Flag:[/dim] [bold yellow]{rec.uncertainty}[/bold yellow]")
        console.print()

    console.print(results_table)
    console.print("[bold green]✔ All 15 questions successfully evaluated against policy.pdf.[/bold green]\n")

if __name__ == "__main__":
    main()
