"""
skills/document_skill.py – Render markdown into a real document
================================================================
The model writes markdown; this renders it. Nothing else.

That split is the whole design. A 3B model asked to emit PDF structure, or
LaTeX, or a full HTML page, produces something that *looks* right and opens
broken, and the failure only surfaces when the user double-clicks the file an
hour later. Markdown is the one format a small model gets right every time,
so it is the only thing the model is ever asked for -- a render failure here
is our bug to fix, never a prompt to retry.

Renderer choices are Windows-shaped. WeasyPrint wants the GTK/Pango DLLs from
a separate MSI and Pandoc is an external installer; neither survives a
"pip install and go" machine. ``markdown`` + ``xhtml2pdf`` are pure Python and
cover md/html/pdf. ``docx`` is refused unless Pandoc already happens to be on
PATH, because silently producing nothing is worse than saying no.

If xhtml2pdf's CSS subset ever proves too thin -- it drops flexbox, most
positioning and anything modern -- the documented alternative is Edge in
headless mode, which is present on every Windows 11 machine and needs no
install at all::

    msedge --headless --disable-gpu --print-to-pdf=<out.pdf> <file:///in.html>

It renders the same HTML with a real browser engine. It is not the default
because it spawns an external process per document, which is slower and one
more thing that can be missing or blocked.

Path safety follows the file_skill rule -- model-supplied paths are untrusted
-- but goes one step further: only the *basename* of the requested filename is
ever used, so ``../../evil.md`` is not detected and rejected, it is structurally
impossible. Writes never overwrite; a colliding name gains a `` -2`` suffix.
And nothing is reported as saved until it has been opened and read back.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.document")

#: What this skill can render. ``docx`` is accepted as a request but only
#: honoured when Pandoc is installed, so it is not in this tuple.
SUPPORTED_FORMATS = ("md", "html", "pdf")

#: Collision suffixes stop here. A hundred documents of the same name means
#: something is looping, and a bounded search fails loudly instead of hanging.
MAX_COLLISION_ATTEMPTS = 100

_MARKDOWN_HINT = (
    "Rendering that needs the markdown library. Install it with: pip install markdown"
)
_PDF_HINT = "PDF rendering needs xhtml2pdf. Install it with: pip install xhtml2pdf"
_PYPDF_HINT = (
    "Checking the PDF afterwards needs pypdf. Install it with: pip install pypdf"
)

#: The exact wording from the spec: name the formats that *do* work, so the
#: model reissues the call instead of apologising to the user.
_DOCX_REFUSAL = (
    "I can make that as pdf, html or markdown - docx needs pandoc installed."
)

#: Serif body for reading, monospace for code. Deliberately small: xhtml2pdf
#: supports a subset of CSS and silently drops the rest, so the stylesheet has
#: to look the same in a browser and in the PDF.
_CSS = """
@page { size: a4 portrait; margin: 2cm; }
body { font-family: Georgia, "Times New Roman", serif; font-size: 11pt;
       line-height: 1.5; color: #1a1a1a; }
h1, h2, h3, h4 { font-family: Helvetica, Arial, sans-serif; color: #111111; }
h1 { font-size: 20pt; }
h2 { font-size: 15pt; }
h3 { font-size: 12pt; }
code, pre { font-family: "Courier New", Courier, monospace; font-size: 9.5pt; }
pre { background-color: #f4f4f4; padding: 8pt; }
code { background-color: #f4f4f4; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #999999; padding: 4pt; text-align: left; }
th { background-color: #eeeeee; }
blockquote { margin-left: 1em; padding-left: 1em; border-left: 2px solid #cccccc;
             color: #444444; }
"""


def _default_root() -> Path:
    """The one directory this skill may write to.

    A function rather than a module constant so tests can redirect it without
    a real home directory ever being touched.
    """
    return Path.home() / "Documents" / "ULTRON"


def _no_window_flags() -> int:
    """CREATE_NO_WINDOW, or 0 off Windows.

    The GUI entry point owns no console, so any console program it starts gets
    a fresh visible one allocated by Windows. See tests/test_no_console_windows.
    """
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _safe_name(raw: str) -> str | None:
    """The basename of an untrusted filename, or None if there isn't one.

    Backslashes are folded to forward slashes first: a model that has been
    talking about Windows paths will send ``..\\..\\evil.md``, and on a POSIX
    box ``Path`` would read that as a single legal filename.
    """
    candidate = str(raw or "").strip().replace("\\", "/")

    # Control characters, NUL above all. A JSON string may legally contain
    # a NUL, so a model can send one; every path call then raises ValueError
    # rather than OSError, which walked straight past the error handling and
    # out of execute() as a traceback. Stripped here, at the edge, so no
    # filesystem call ever sees one.
    candidate = "".join(ch for ch in candidate if ch.isprintable() or ch == " ")

    name = Path(candidate).name.strip()

    # "." and ".." already collapse to an empty name; "..." and friends do not,
    # and a file made of nothing but dots is never what anyone meant.
    if not name or not name.strip("."):
        return None
    return name


def _resolve_format(explicit: Any, name: str) -> str:
    """Explicit argument wins, then the extension, then markdown.

    The extension is the fallback because the model is told to put one on the
    filename ("dsa-week1.pdf") far more reliably than it fills in `format`.
    """
    if explicit:
        return str(explicit).strip().lower().lstrip(".")

    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix in SUPPORTED_FORMATS or suffix == "docx":
        return suffix
    return "md"


def _with_format_suffix(name: str, fmt: str) -> str:
    """Make the filename end in the format actually being rendered.

    Only rewrites a suffix that is itself a document format: `notes.txt` asked
    for as markdown stays `notes.txt`, because the user named that file.
    """
    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix == fmt:
        return name
    if suffix and suffix not in SUPPORTED_FORMATS and suffix != "docx":
        return name
    return f"{Path(name).stem or name}.{fmt}"


def _unique_path(path: Path) -> Path:
    """A path that does not exist yet, suffixing ` -2`, ` -3`, ...

    Voice input has no "are you sure" for a filename, and two study plans
    dictated a week apart will collide. Losing the first one silently is the
    single worst thing this skill could do.
    """
    if not path.exists():
        return path

    for attempt in range(2, MAX_COLLISION_ATTEMPTS + 2):
        candidate = path.with_name(f"{path.stem} -{attempt}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"too many files named like {path.name}")


def _render_html(content_md: str, title: str) -> str:
    """Markdown to a standalone HTML page. Raises ImportError if unavailable."""
    import markdown

    body = markdown.markdown(content_md, extensions=["tables", "fenced_code"])
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '<meta charset="utf-8" />\n'
        f"<title>{html_lib.escape(title)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _write_pdf(page_html: str, destination: Path) -> None:
    """Render the same HTML to PDF. Raises ImportError if unavailable."""
    from xhtml2pdf import pisa

    with destination.open("wb") as handle:
        status = pisa.CreatePDF(page_html, dest=handle, encoding="utf-8")

    if status.err:
        raise OSError(f"xhtml2pdf reported {status.err} error(s)")


def _pdf_page_count(path: Path) -> int:
    """Pages in a written PDF. Raises ImportError if unavailable."""
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


class DocumentSkill(Skill):
    """Write a document the user can open, from markdown the model wrote."""

    name = "DocumentSkill"
    description = "Renders markdown into a md, html or pdf file in Documents/ULTRON."
    version = "1.0.0"
    enabled = True

    def __init__(self, container: Any = None, output_root: Path | str | None = None) -> None:
        super().__init__(container)
        # Resolved lazily rather than here: tests (and a future settings key)
        # redirect the root, and constructing the skill must not depend on it.
        self._output_root = Path(output_root) if output_root else None

    @property
    def output_root(self) -> Path:
        return self._output_root if self._output_root is not None else _default_root()

    async def execute(self, task: Task) -> str:
        params = task.parameters or {}
        filename = params.get("filename")
        content_md = params.get("content_md")
        fmt_arg = params.get("format")

        name = _safe_name(filename)
        if name is None:
            return "I need a name for the file."

        # Not `if not content_md`: an empty document is the one result that is
        # always a mistake, and it is what a model sends when it lost the plan.
        if content_md is None or not str(content_md).strip():
            return "I need the document content before I can write it."

        fmt = _resolve_format(fmt_arg, name)

        if fmt == "docx" and not shutil.which("pandoc"):
            return _DOCX_REFUSAL
        if fmt not in SUPPORTED_FORMATS and fmt != "docx":
            return (
                f"I can save documents as markdown, html or pdf, not '{fmt}'."
            )

        # Rendering a PDF takes the better part of a second and the GUI shares
        # this loop with the speech pipeline.
        return await asyncio.to_thread(self._create, name, str(content_md), fmt)

    # ── the deterministic half ────────────────────────────────────────────

    def _create(self, name: str, content_md: str, fmt: str) -> str:
        root = self.output_root
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"I couldn't create the ULTRON documents folder: {exc}"

        # Joined against the root *after* basename extraction, so there is no
        # path to escape from -- traversal never gets a component to work with.
        target = _unique_path(root / _with_format_suffix(name, fmt))

        try:
            if fmt == "md":
                target.write_text(content_md, encoding="utf-8")
            elif fmt == "html":
                target.write_text(_render_html(content_md, target.stem), encoding="utf-8")
            elif fmt == "pdf":
                missing = self._pdf_dependency_hint()
                if missing:
                    return missing
                _write_pdf(_render_html(content_md, target.stem), target)
            else:
                self._write_docx(content_md, target)
        except ImportError:
            # The PDF libraries were checked above, so the only import left
            # that can fail here is the markdown renderer.
            return _MARKDOWN_HINT
        except OSError as exc:
            self._discard(target)
            return f"I couldn't write {target.name}: {exc}"
        except Exception as exc:  # noqa: BLE001 - a renderer bug must not end the turn
            logger.error(f"Rendering {target.name} as {fmt} failed: {exc}")
            self._discard(target)
            return f"I couldn't render {target.name}, so nothing was saved."

        problem = self._verify(target, fmt)
        if problem:
            logger.error(f"Verification failed for {target}: {problem}")
            self._discard(target)
            return f"I wrote {target.name} but it came out unreadable, so I deleted it."

        logger.info(f"Saved {target} ({target.stat().st_size} bytes)")
        return f"Saved {target.name} in {self._spoken_location(root)}."

    def _pdf_dependency_hint(self) -> str | None:
        """Check both PDF libraries *before* writing anything.

        Discovering pypdf is missing after the render would mean either
        deleting a perfectly good PDF or claiming an unverified one is fine.
        """
        try:
            import xhtml2pdf  # noqa: F401
        except ImportError:
            return _PDF_HINT
        try:
            import pypdf  # noqa: F401
        except ImportError:
            return _PYPDF_HINT
        return None

    def _write_docx(self, content_md: str, target: Path) -> None:
        """Hand the markdown to Pandoc, which the caller has already found."""
        pandoc = shutil.which("pandoc")
        with tempfile.TemporaryDirectory(prefix="ULTRON-doc-") as tmp:
            source = Path(tmp) / "source.md"
            source.write_text(content_md, encoding="utf-8")
            result = subprocess.run(
                [str(pandoc), str(source), "-f", "markdown", "-o", str(target)],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=_no_window_flags(),
            )
        if result.returncode != 0:
            raise OSError((result.stderr or "pandoc failed").strip().splitlines()[-1])

    def _verify(self, path: Path, fmt: str) -> str | None:
        """Open the file we just claimed to write. Returns why not, or None.

        xhtml2pdf can return success and leave a zero-byte or header-only file
        behind, and a document the user cannot open is indistinguishable from
        one that was never written -- except that ULTRON said it was there.
        """
        try:
            if not path.is_file():
                return "the file is not there"
            if path.stat().st_size <= 0:
                return "the file is empty"
        except OSError as exc:
            return f"the file could not be checked ({exc})"

        if fmt != "pdf":
            return None

        try:
            pages = _pdf_page_count(path)
        except Exception as exc:  # noqa: BLE001 - any reader failure is a bad PDF
            return f"the pdf could not be opened ({exc})"
        return None if pages >= 1 else "the pdf has no pages"

    def _discard(self, path: Path) -> None:
        """Remove a partial file. Never raises -- the caller is already failing."""
        try:
            path.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            # ValueError, not just OSError: an embedded NUL makes unlink raise
            # before it touches the disk. _safe_name strips those now, but the
            # cleanup path runs when something has already gone wrong and must
            # not be the thing that raises.
            logger.warning(f"Could not remove partial file {path}: {exc}")

    def _spoken_location(self, root: Path) -> str:
        """Say where it went the way the user thinks of it, not as a full path."""
        try:
            return str(root.relative_to(Path.home()))
        except ValueError:
            return str(root)
