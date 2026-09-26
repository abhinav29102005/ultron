"""
streaming_rag/ingest.py – Drag & Drop and File Selection Ingestion for Live RAG
================================================================================
Enables adding external files (PDF, TXT, MD, JSON, CSV) into the RAG corpus:
- Supports terminal Drag-and-Drop (pasting file paths with quotes/file://)
- Supports native GUI file picker (Zenity / Tkinter) via `/rag select`
- Extracts text using pypdf, native readers, and OCR fallback
- Chunks text into verified [Doc_ID §Section] items
- Persists to ~/.ultron/rag_custom_corpus.json and live reloads the index
"""

from __future__ import annotations

import os
import sys
import re
import json
import shutil
import subprocess
import urllib.parse
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from streaming_rag.models import DocumentChunk
from streaming_rag.corpus import SAMPLE_CORPUS

console = Console()


def get_custom_corpus_file() -> Path:
    """Return the platform-appropriate custom corpus JSON file path."""
    app_dir = os.environ.get("ULTRON_HOME")
    if app_dir and Path(app_dir).exists():
        base = Path(app_dir) / "data"
    else:
        # Determine whether running under ultron or friday
        repo_name = Path(__file__).resolve().parent.parent.name.lower()
        folder_name = ".friday" if "friday" in repo_name else ".ultron"
        base = Path.home() / folder_name
    base.mkdir(parents=True, exist_ok=True)
    return base / "rag_custom_corpus.json"


def load_all_chunks() -> List[DocumentChunk]:
    """Load default corpus combined with any user-ingested custom chunks."""
    corpus: List[DocumentChunk] = list(SAMPLE_CORPUS)
    custom_file = get_custom_corpus_file()
    if custom_file.exists():
        try:
            with open(custom_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    corpus.append(DocumentChunk(**item))
        except Exception as e:
            console.print(f"[dim yellow]Warning: Failed to load custom corpus ({e})[/dim yellow]")
    return corpus


def save_custom_chunk(chunk: DocumentChunk) -> None:
    """Persist a newly ingested DocumentChunk into the custom corpus file."""
    custom_file = get_custom_corpus_file()
    existing: List[Dict[str, Any]] = []
    if custom_file.exists():
        try:
            with open(custom_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    # Avoid duplicate tags
    existing = [x for x in existing if not (x.get("doc_id") == chunk.doc_id and x.get("section") == chunk.section)]
    existing.append({
        "doc_id": chunk.doc_id,
        "section": chunk.section,
        "title": chunk.title,
        "text": chunk.text,
        "metadata": chunk.metadata,
    })

    with open(custom_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def clean_file_path(raw_path: str) -> Optional[Path]:
    r"""
    Sanitize terminal drag-and-drop input:
    - Strips wrapping quotes ('...', "...")
    - Converts file:// URIs (e.g. file:///home/user/doc.pdf)
    - Unescapes backslash spaces (e.g. My\ Document.pdf)
    - Expands user tilde (~/...)
    """
    if not raw_path:
        return None

    path_str = raw_path.strip()

    # Handle file:// URI
    if path_str.startswith("file://"):
        path_str = urllib.parse.unquote(path_str[7:])

    # Strip surrounding quotes
    if (path_str.startswith("'") and path_str.endswith("'")) or (path_str.startswith('"') and path_str.endswith('"')):
        path_str = path_str[1:-1]

    # Handle shell backslash escapes
    path_str = path_str.replace("\\ ", " ")

    p = Path(os.path.expanduser(path_str)).resolve()
    if p.exists() and p.is_file():
        return p
    return None


def select_files_via_gui() -> List[Path]:
    """Open a native desktop file picker dialog (Zenity, KDialog, or Tkinter)."""
    # 1. Try Zenity (GNOME / Linux standard)
    if shutil.which("zenity") and os.environ.get("DISPLAY"):
        try:
            res = subprocess.run(
                [
                    "zenity",
                    "--file-selection",
                    "--multiple",
                    "--separator=|",
                    "--title=Select Documents for ULTRON Live RAG",
                    "--file-filter=Documents (*.pdf *.txt *.md *.json *.csv) | *.pdf *.txt *.md *.markdown *.json *.csv",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode == 0 and res.stdout.strip():
                paths = [Path(p.strip()) for p in res.stdout.strip().split("|") if p.strip()]
                return [p for p in paths if p.exists() and p.is_file()]
        except Exception:
            pass

    # 2. Try KDialog (KDE standard)
    if shutil.which("kdialog") and os.environ.get("DISPLAY"):
        try:
            res = subprocess.run(
                [
                    "kdialog",
                    "--getopenfilename",
                    "--multiple",
                    "--title", "Select Documents for ULTRON Live RAG",
                    Path.home(),
                    "*.pdf *.txt *.md *.json *.csv | Documents",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode == 0 and res.stdout.strip():
                paths = [Path(p.strip()) for p in res.stdout.strip().split() if p.strip()]
                return [p for p in paths if p.exists() and p.is_file()]
        except Exception:
            pass

    # 3. Fallback to Tkinter File Dialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        files = filedialog.askopenfilenames(
            title="Select Documents for ULTRON Live RAG",
            filetypes=[
                ("Supported Documents", "*.pdf *.txt *.md *.markdown *.json *.csv"),
                ("All Files", "*.*")
            ]
        )
        root.destroy()
        if files:
            return [Path(f) for f in files if Path(f).is_file()]
    except Exception:
        pass

    return []


def chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> List[str]:
    """Split text into semantic paragraph/sentence chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            # Split by sentence
            sentences = re.split(r"(?<=[.!?])\s+", para)
            curr = ""
            for s in sentences:
                if len(curr) + len(s) + 1 <= max_chars:
                    curr = (curr + " " + s).strip()
                else:
                    if curr:
                        chunks.append(curr)
                    curr = s
            if curr:
                chunks.append(curr)

    return chunks if chunks else [text.strip()]


def extract_chunks_from_file(file_path: Path) -> List[Tuple[str, str, Dict[str, Any]]]:
    """
    Extract structured chunks from a file.
    Returns: List of (section_name, text, metadata)
    """
    ext = file_path.suffix.lower()
    base_name = file_path.stem
    results: List[Tuple[str, str, Dict[str, Any]]] = []

    # 1. Plain Text / Markdown
    if ext in (".txt", ".md", ".markdown"):
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            # Look for markdown headers
            sections = re.split(r"\n(?=#{1,3}\s+)", content)
            sec_idx = 1
            for sec in sections:
                sec = sec.strip()
                if not sec:
                    continue
                lines = sec.split("\n", 1)
                sec_title = lines[0].lstrip("#").strip() if len(lines) > 0 and lines[0].startswith("#") else f"Section {sec_idx}"
                body = lines[1].strip() if len(lines) > 1 else sec
                if not body:
                    body = sec_title

                sub_chunks = chunk_text(body, max_chars=600)
                for sub in sub_chunks:
                    results.append((
                        f"§{sec_idx}",
                        sub,
                        {"source": file_path.name, "title": f"{base_name} - {sec_title}", "type": "markdown"}
                    ))
                    sec_idx += 1
        except Exception as e:
            console.print(f"[red]Error reading text file: {e}[/red]")

    # 2. PDF Documents
    elif ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            sec_idx = 1
            for page_num, page in enumerate(reader.pages, start=1):
                extracted = (page.extract_text() or "").strip()
                if extracted:
                    sub_chunks = chunk_text(extracted, max_chars=600)
                    for sub in sub_chunks:
                        results.append((
                            f"§{sec_idx}",
                            sub,
                            {"source": file_path.name, "page": page_num, "title": f"{base_name} (Page {page_num})", "type": "pdf"}
                        ))
                        sec_idx += 1
                else:
                    # Try OCR if text is empty (scanned PDF)
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                        ocr = RapidOCR()
                        import pypdfium2
                        pdf = pypdfium2.PdfDocument(str(file_path))
                        pil_image = pdf[page_num - 1].render().to_pil()
                        ocr_res, _ = ocr(pil_image)
                        if ocr_res:
                            ocr_text = "\n".join([line[1] for line in ocr_res])
                            sub_chunks = chunk_text(ocr_text, max_chars=600)
                            for sub in sub_chunks:
                                results.append((
                                    f"§{sec_idx}",
                                    sub,
                                    {"source": file_path.name, "page": page_num, "title": f"{base_name} (OCR Page {page_num})", "type": "pdf_ocr"}
                                ))
                                sec_idx += 1
                    except Exception:
                        pass
        except Exception as e:
            console.print(f"[red]Error parsing PDF: {e}[/red]")

    # 3. JSON Structured Data
    elif ext == ".json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sec_idx = 1
            if isinstance(data, list):
                for item in data:
                    text_val = item.get("text") or item.get("content") or item.get("description") or json.dumps(item)
                    title_val = item.get("title") or f"{base_name} Item {sec_idx}"
                    results.append((f"§{sec_idx}", str(text_val), {"source": file_path.name, "title": title_val, "type": "json"}))
                    sec_idx += 1
            elif isinstance(data, dict):
                for k, v in data.items():
                    val_str = v if isinstance(v, str) else json.dumps(v)
                    results.append((f"§{sec_idx}", f"{k}: {val_str}", {"source": file_path.name, "title": f"{base_name} - {k}", "type": "json"}))
                    sec_idx += 1
        except Exception as e:
            console.print(f"[red]Error reading JSON: {e}[/red]")

    # Fallback raw line reading
    if not results:
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            chunks = chunk_text(raw)
            for idx, c in enumerate(chunks, start=1):
                results.append((f"§{idx}", c, {"source": file_path.name, "title": base_name, "type": "raw"}))
        except Exception:
            pass

    return results


def ingest_file(file_path: Path, doc_id_prefix: Optional[str] = None) -> List[DocumentChunk]:
    """Ingest a file into the RAG corpus and return the created DocumentChunks."""
    if not doc_id_prefix:
        # Create a clean doc_id like Doc_TRAVEL_01
        clean_name = re.sub(r"[^A-Za-z0-9]", "_", file_path.stem).upper()
        # Truncate to reasonable length
        clean_name = clean_name[:12].strip("_")
        doc_id_prefix = f"Doc_{clean_name}"

    raw_chunks = extract_chunks_from_file(file_path)
    if not raw_chunks:
        console.print(f"[red]No extractable text found in {file_path.name}.[/red]")
        return []

    created_chunks: List[DocumentChunk] = []

    for sec, text, meta in raw_chunks:
        chunk = DocumentChunk(
            doc_id=doc_id_prefix,
            section=sec,
            title=meta.get("title", f"{doc_id_prefix} {sec}"),
            text=text,
            metadata=meta,
        )
        save_custom_chunk(chunk)
        created_chunks.append(chunk)

    # Immediately reload live RAG instance index
    try:
        from streaming_rag.pipeline import StreamingLiveRAG
        rag = StreamingLiveRAG.get_instance()
        rag.corpus = load_all_chunks()
        rag.reload_corpus()
    except Exception:
        pass

    return created_chunks


def interactive_ingest_flow(arg: Optional[str] = None) -> None:
    """Run the interactive drag-and-drop or select flow from CLI."""
    target_files: List[Path] = []

    if arg and arg.strip():
        # User provided path directly (or dragged & dropped into command line)
        cleaned = clean_file_path(arg.strip())
        if cleaned:
            target_files.append(cleaned)
        elif arg.strip().lower() in ("select", "browse", "choose"):
            console.print("[dim cyan]Opening native file chooser dialog...[/dim cyan]")
            target_files = select_files_via_gui()
        else:
            console.print(f"[red]File not found or unreadable: '{arg.strip()}'[/red]")
            return
    else:
        # Prompt user with interactive options
        console.print(Panel(
            "[bold cyan]ULTRON LIVE RAG — DOCUMENT INGESTION[/bold cyan]\n"
            "[dim]Add policies, PDFs, guidelines, and manuals directly to the factual corpus[/dim]\n\n"
            "• [bold white]Drag & Drop[/] any document file directly into this terminal window\n"
            "• [bold white]Paste or type[/] the absolute or relative file path\n"
            "• Type [bold yellow]'select'[/] (or press Enter) to open the native GUI file selector dialog",
            border_style="cyan"
        ))

        try:
            user_input = console.input("\n[bold yellow]rag-ingest > [/bold yellow]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Ingestion cancelled.[/dim]")
            return

        if not user_input or user_input.lower() in ("select", "browse", "choose"):
            console.print("[dim cyan]Opening native file chooser dialog...[/dim cyan]")
            target_files = select_files_via_gui()
        else:
            cleaned = clean_file_path(user_input)
            if cleaned:
                target_files.append(cleaned)
            else:
                console.print(f"[red]File not found: '{user_input}'[/red]")
                return

    if not target_files:
        console.print("[dim yellow]No files selected. Ingestion cancelled.[/dim yellow]")
        return

    # Ingest each selected file
    total_added = 0
    for f in target_files:
        console.print(f"[dim]Parsing and indexing '{f.name}'...[/dim]")
        chunks = ingest_file(f)
        if chunks:
            total_added += len(chunks)
            table = Table(title=f"Ingested '{f.name}' ({len(chunks)} chunks)", border_style="green")
            table.add_column("Tag", style="bold cyan", width=16)
            table.add_column("Section Title", style="white", width=32)
            table.add_column("Text Preview", style="dim")

            for c in chunks[:5]:  # Show first 5 chunks
                preview = c.text[:100] + "..." if len(c.text) > 100 else c.text
                table.add_row(c.citation_tag, c.title, preview)

            if len(chunks) > 5:
                table.add_row("...", f"... and {len(chunks) - 5} more chunks", "")

            console.print(table)

    console.print(f"[bold green]✓ Successfully added {total_added} chunks to the live RAG corpus![/bold green]")
    console.print("[dim]Type [bold cyan]/rag corpus[/bold cyan] to view, or query it immediately with [bold cyan]/rag <question>[/bold cyan].[/dim]\n")
