"""
streaming_rag/cli.py – Global CLI Entry Point for ULTRON Streaming Live RAG
==========================================================================
Provides global command-line access via `ultron-rag` and `ultron rag`:
- Single-shot querying with exact section citations [Doc_XX §YY]
- Interactive multi-turn REPL with continuous conversational memory & anaphora bridging
- Real-time token streaming with microsecond TTFT metrics
- Benchmark and evaluation gate runner (G1-G9)
- Corpus introspection and entity memory inspection
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from streaming_rag.models import StreamingChunk
from streaming_rag.pipeline import StreamingLiveRAG
from streaming_rag.session import SessionRegistry

console = Console()


def render_response_panel(record, query: str):
    """Renders a structured, cybernetic output panel with citations and telemetry."""
    # Header info
    header = f"[bold cyan]ULTRON Live RAG[/bold cyan] · [dim]Turn {record.turn_id} · Version {record.answer_version}[/dim]"
    if record.resolved_query and record.resolved_query != query:
        header += f"\n[dim cyan]⚡ Context Resolved:[/] [italic]{record.resolved_query}[/italic]"

    # Body
    body_text = record.answer

    # Citations line
    citations_str = " ".join([f"[bold green][{c}][/bold green]" for c in record.citations])
    metrics_str = (
        f"[dim]Latency: {record.telemetry.total_latency_ms:.1f}ms | "
        f"Early Gain: {record.telemetry.early_retrieval_gain_ms:.1f}ms | "
        f"TTFT: {record.telemetry.ttft_ms or 1.0:.1f}ms | "
        f"Tokens: {record.telemetry.prompt_tokens + record.telemetry.completion_tokens}[/dim]"
    )

    content = f"{body_text}\n\n[bold white]Citations:[/] {citations_str}\n{metrics_str}"

    if record.uncertainty:
        content += f"\n[bold yellow]⚠️ Uncertainty:[/] [dim yellow]{record.uncertainty}[/dim yellow]"

    console.print(Panel(content, title=header, border_style="cyan", padding=(1, 2)))


def run_single_query(query: str, session_id: str, stream_tokens: bool = False) -> int:
    rag = StreamingLiveRAG.get_instance()
    stream = [StreamingChunk(timestamp_s=0.5, text=query, is_final=True)]

    if stream_tokens:
        console.print(f"[dim cyan]⚡ Querying Streaming Live RAG (session: {session_id})...[/dim cyan]")
        record = None
        start = time.perf_counter()
        token_count = 0

        console.print("[bold green]Answer:[/] ", end="")
        for tok in rag.process_stream_streaming(stream, session_id=session_id):
            console.print(tok.token, end="", highlight=False)
            token_count += 1
            sys.stdout.flush()
        console.print()

        session = rag.get_or_create_session(session_id)
        if session.turns:
            last_turn = session.turns[-1]
            cites = " ".join([f"[bold green][{c}][/bold green]" for c in last_turn.citations])
            elapsed = (time.perf_counter() - start) * 1000.0
            console.print(f"[dim]Citations: {cites} | Latency: {elapsed:.1f}ms | Turn: {last_turn.turn_id}[/dim]")
        return 0

    record = rag.process_stream(stream, session_id=session_id)
    render_response_panel(record, query)
    return 0


def run_interactive_repl(session_id: str = "global_cli_rag") -> int:
    rag = StreamingLiveRAG.get_instance()
    console.print(Panel(
        "[bold cyan]ULTRON CYBERNETIC LIVE RAG — INTERACTIVE CONVERSATION REPL[/bold cyan]\n"
        "[dim]Powered by Samsung PRISM Theme 4 & Nebius Cloud Hybrid Search[/dim]\n\n"
        "Commands: [bold white]/context[/] (view entity memory), [bold white]/corpus[/] (list docs), "
        "[bold white]/reset[/] (clear memory), [bold white]/exit[/] (quit)",
        border_style="bright_cyan"
    ))

    session = rag.get_or_create_session(session_id)

    while True:
        try:
            prompt_text = console.input("\n[bold yellow]ultron-rag > [/bold yellow]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting ULTRON Live RAG REPL. Session terminated.[/dim]")
            break

        if not prompt_text:
            continue

        if prompt_text.lower() in ("/exit", "/quit", "exit", "quit"):
            console.print("[dim]Goodbye.[/dim]")
            break

        elif prompt_text.lower() == "/reset":
            SessionRegistry.clear(session_id)
            session = rag.get_or_create_session(session_id)
            console.print("[bold green]✓ Session memory reset.[/bold green]")
            continue

        elif prompt_text.lower() == "/context":
            table = Table(title=f"Active Session State ({session_id})", border_style="cyan")
            table.add_column("Property", style="bold white")
            table.add_column("Current Value", style="green")
            table.add_row("Active Version", str(session.active_version))
            table.add_row("Turns Recorded", str(len(session.turns)))
            table.add_row("Location", str(session.entity_state.location))
            table.add_row("Event Type", str(session.entity_state.event_type))
            table.add_row("Headcount", str(session.entity_state.headcount))
            table.add_row("Service Topics", ", ".join(session.entity_state.service_topics) or "None")
            table.add_row("Active Constraints", ", ".join(session.entity_state.constraints) or "None")
            table.add_row("Retained Citations", ", ".join(session.active_citations) or "None")
            console.print(table)
            continue

        elif prompt_text.lower() == "/corpus":
            table = Table(title="Indexed Enterprise Policy Corpus", border_style="green")
            table.add_column("Tag", style="bold cyan")
            table.add_column("Document Title", style="white")
            table.add_column("Metadata", style="dim")
            for doc in rag.corpus:
                table.add_row(doc.citation_tag, doc.title, str(doc.metadata))
            console.print(table)
            continue

        elif prompt_text.lower() == "/help":
            console.print("[cyan]Ask any policy question! Examples:[/cyan]")
            console.print("  1. Pune workshop for 30 people and cancellation policy")
            console.print("  2. What if it is for 50 people? (tests anaphora & capacity limits)")
            console.print("  3. What about hotel lodging tariffs there? (tests deictic location)")
            console.print("  4. Repeat in two bullets (tests Gate 0 zero-retrieval suppression)")
            continue

        # Process user turn
        stream = [StreamingChunk(timestamp_s=0.5, text=prompt_text, is_final=True)]
        record = rag.process_stream(stream, session_id=session_id)
        render_response_panel(record, prompt_text)

    return 0


def rag_cli(argv: Optional[List[str]] = None) -> int:
    """Main CLI handler parsing flags and routing execution."""
    parser = argparse.ArgumentParser(
        prog="ultron-rag",
        description="ULTRON Streaming Live RAG – Speculative Retrieval & Multi-Turn Context Engine",
    )
    parser.add_argument("query", nargs="*", default=[], help="Question or query string to evaluate against corpus")
    parser.add_argument("--stream", "-s", action="store_true", help="Stream response tokens in real-time to stdout")
    parser.add_argument("--session", "-S", default="global_cli_rag", help="Session ID for multi-turn state persistence")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Run full Technical Evaluation Gates (G1-G9)")
    parser.add_argument("--demo", "-d", action="store_true", help="Run 9-flow live interactive demonstration")

    args = parser.parse_args(argv)

    if args.benchmark:
        from streaming_rag.benchmark import main as bench_main
        bench_main()
        return 0

    if args.demo:
        from scripts.demo_streaming_rag import main as demo_main
        demo_main()
        return 0

    if args.query:
        query_text = " ".join(args.query).strip()
        return run_single_query(query_text, session_id=args.session, stream_tokens=args.stream)

    # If no query provided, enter interactive REPL
    return run_interactive_repl(session_id=args.session)


def main() -> None:
    code = rag_cli(sys.argv[1:])
    sys.exit(code)


if __name__ == "__main__":
    main()
