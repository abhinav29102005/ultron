"""
Tests for skills/document_skill.py – markdown in, a real document out.

The output root is monkeypatched in every test: this skill's whole job is to
write into the user's Documents folder, and a test suite that actually did
that would litter a real machine.

What is worth asserting is not "does markdown render" -- that is the library's
problem -- but the deterministic promises the skill makes on top of it: a
traversal filename cannot escape the root, an existing file is never
overwritten, and nothing is announced as saved until it has been read back.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from intelligence.task import Task, TaskStatus
from skills import document_skill
from skills.document_skill import DocumentSkill

FIXTURE_MD = """# Week 1

A short plan with a **table** and some code.

| Day | Topic |
|-----|-------|
| Mon | Arrays |
| Tue | Hashing |

```python
def solve(nums):
    return sorted(nums)
```

> Revise on Sunday.
"""


def _task(**params) -> Task:
    return Task(
        task_id="t1",
        skill_name="DocumentSkill",
        intent="create_document",
        parameters=params,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    """Redirect the sandbox root, exactly as the skill resolves it at call time."""
    target = tmp_path / "FRIDAY"
    monkeypatch.setattr(document_skill, "_default_root", lambda: target)
    return target


class TestFormats:
    @pytest.mark.asyncio
    async def test_markdown_is_written_verbatim(self, root):
        out = await DocumentSkill().execute(
            _task(filename="week1.md", content_md=FIXTURE_MD)
        )

        written = root / "week1.md"
        assert written.read_text(encoding="utf-8") == FIXTURE_MD
        assert "week1.md" in out

    @pytest.mark.asyncio
    async def test_html_renders_tables_and_fenced_code(self, root):
        await DocumentSkill().execute(
            _task(filename="week1.html", content_md=FIXTURE_MD)
        )

        page = (root / "week1.html").read_text(encoding="utf-8")
        assert "<table>" in page  # the "tables" extension is on
        assert "<pre><code" in page  # so is "fenced_code"
        assert "<style>" in page and "monospace" in page  # the embedded shell

    @pytest.mark.asyncio
    async def test_pdf_is_produced_and_opens_with_at_least_one_page(self, root):
        from pypdf import PdfReader

        out = await DocumentSkill().execute(
            _task(filename="week1.pdf", content_md=FIXTURE_MD)
        )

        written = root / "week1.pdf"
        assert written.stat().st_size > 0
        assert len(PdfReader(str(written)).pages) >= 1
        assert "week1.pdf" in out

    @pytest.mark.asyncio
    async def test_the_format_argument_beats_the_extension(self, root):
        """The model sometimes names the file .md and asks for a pdf anyway."""
        await DocumentSkill().execute(
            _task(filename="week1.md", content_md=FIXTURE_MD, format="pdf")
        )

        assert (root / "week1.pdf").exists()
        assert not (root / "week1.md").exists()

    @pytest.mark.asyncio
    async def test_an_extensionless_name_defaults_to_markdown(self, root):
        await DocumentSkill().execute(_task(filename="notes", content_md="hello"))
        assert (root / "notes.md").read_text(encoding="utf-8") == "hello"

    @pytest.mark.asyncio
    async def test_an_unknown_format_is_refused_by_name(self, root):
        out = await DocumentSkill().execute(
            _task(filename="week1.epub", content_md=FIXTURE_MD, format="epub")
        )

        assert "epub" in out
        assert not root.exists() or not list(root.glob("*"))


class TestSandbox:
    @pytest.mark.asyncio
    async def test_a_traversal_filename_lands_inside_the_root(self, root):
        """`../../evil.md` is not detected and rejected -- only its basename is
        ever used, so there is nothing left to escape with."""
        await DocumentSkill().execute(
            _task(filename="../../evil.md", content_md="payload")
        )

        assert (root / "evil.md").exists()
        assert not (root.parent.parent / "evil.md").exists()

    @pytest.mark.asyncio
    async def test_a_windows_style_traversal_also_lands_inside(self, root):
        await DocumentSkill().execute(
            _task(filename=r"..\..\Startup\evil.md", content_md="payload")
        )

        assert (root / "evil.md").exists()

    @pytest.mark.asyncio
    async def test_an_absolute_path_is_reduced_to_its_basename(self, root):
        await DocumentSkill().execute(
            _task(filename=r"C:\Windows\System32\drivers\etc\hosts.md",
                  content_md="payload")
        )

        assert (root / "hosts.md").exists()

    @pytest.mark.asyncio
    async def test_a_dot_only_name_is_refused(self, root):
        out = await DocumentSkill().execute(_task(filename="...", content_md="x"))
        assert "name" in out.lower()
        assert not root.exists() or not list(root.glob("*"))

    @pytest.mark.asyncio
    async def test_empty_content_is_refused(self, root):
        out = await DocumentSkill().execute(_task(filename="week1.md", content_md="   "))
        assert "content" in out.lower()
        assert not root.exists() or not list(root.glob("*"))


class TestNoSilentOverwrite:
    @pytest.mark.asyncio
    async def test_a_second_document_of_the_same_name_is_suffixed(self, root):
        skill = DocumentSkill()
        await skill.execute(_task(filename="plan.md", content_md="first"))
        out = await skill.execute(_task(filename="plan.md", content_md="second"))

        assert (root / "plan.md").read_text(encoding="utf-8") == "first"
        assert (root / "plan -2.md").read_text(encoding="utf-8") == "second"
        assert "plan -2.md" in out

    @pytest.mark.asyncio
    async def test_the_suffix_keeps_counting(self, root):
        skill = DocumentSkill()
        for _ in range(3):
            await skill.execute(_task(filename="plan.md", content_md="x"))

        assert (root / "plan -3.md").exists()

    @pytest.mark.asyncio
    async def test_pdfs_are_suffixed_before_the_extension(self, root):
        skill = DocumentSkill()
        await skill.execute(_task(filename="plan.pdf", content_md=FIXTURE_MD))
        await skill.execute(_task(filename="plan.pdf", content_md=FIXTURE_MD))

        assert (root / "plan -2.pdf").exists()


class TestVerification:
    @pytest.mark.asyncio
    async def test_an_unreadable_pdf_is_deleted_rather_than_announced(
        self, root, monkeypatch
    ):
        """A PDF that xhtml2pdf claims to have written but pypdf cannot open is
        worse than a failure: the user only finds out on double-click."""
        def _corrupt(page_html, destination):
            destination.write_bytes(b"not a pdf at all")

        monkeypatch.setattr(document_skill, "_write_pdf", _corrupt)

        out = await DocumentSkill().execute(
            _task(filename="broken.pdf", content_md=FIXTURE_MD)
        )

        assert not (root / "broken.pdf").exists()
        assert "saved" not in out.lower()

    @pytest.mark.asyncio
    async def test_an_empty_render_is_deleted(self, root, monkeypatch):
        monkeypatch.setattr(
            document_skill,
            "_write_pdf",
            lambda page_html, destination: destination.write_bytes(b""),
        )

        out = await DocumentSkill().execute(
            _task(filename="empty.pdf", content_md=FIXTURE_MD)
        )

        assert not (root / "empty.pdf").exists()
        assert "deleted" in out.lower()

    @pytest.mark.asyncio
    async def test_a_renderer_exception_does_not_end_the_turn(self, root, monkeypatch):
        def _boom(page_html, destination):
            raise RuntimeError("layout engine exploded")

        monkeypatch.setattr(document_skill, "_write_pdf", _boom)

        out = await DocumentSkill().execute(
            _task(filename="boom.pdf", content_md=FIXTURE_MD)
        )

        assert isinstance(out, str)
        assert "boom.pdf" in out
        assert not (root / "boom.pdf").exists()


class TestDocx:
    @pytest.mark.asyncio
    async def test_without_pandoc_docx_is_refused_with_the_alternatives(
        self, root, monkeypatch
    ):
        monkeypatch.setattr(document_skill.shutil, "which", lambda name: None)

        out = await DocumentSkill().execute(
            _task(filename="report.docx", content_md=FIXTURE_MD)
        )

        assert out == (
            "I can make that as pdf, html or markdown - docx needs pandoc installed."
        )
        assert not root.exists() or not list(root.glob("*"))

    @pytest.mark.asyncio
    async def test_the_refusal_also_fires_for_an_explicit_format_argument(
        self, root, monkeypatch
    ):
        monkeypatch.setattr(document_skill.shutil, "which", lambda name: None)

        out = await DocumentSkill().execute(
            _task(filename="report.md", content_md=FIXTURE_MD, format="docx")
        )

        assert "pandoc" in out


class TestSpokenReply:
    @pytest.mark.asyncio
    async def test_the_reply_names_the_file_and_carries_no_markdown(self, root):
        out = await DocumentSkill().execute(
            _task(filename="dsa-week1.pdf", content_md=FIXTURE_MD)
        )

        assert out.startswith("Saved dsa-week1.pdf in ")
        assert out.endswith(".")
        # It is read aloud by TTS -- none of this may reach it.
        assert "#" not in out and "*" not in out and "\n" not in out

    @pytest.mark.asyncio
    async def test_the_real_location_is_spoken_as_documents_friday(self, tmp_path):
        """Under the real home, the spoken form is the folder the user knows."""
        skill = DocumentSkill(output_root=Path.home() / "Documents" / "FRIDAY")
        assert skill._spoken_location(skill.output_root) == str(
            Path("Documents") / "FRIDAY"
        )


class TestHostileFilenames:
    """A model-supplied filename is untrusted input, and JSON allows a NUL.

    Every path call raises ValueError -- not OSError -- on an embedded null,
    so an unhandled one escaped execute() as a traceback. Section 0 requires a
    sentence: the assistant speaks its return value, and it cannot speak a
    stack trace.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fmt", ["md", "html", "pdf"])
    async def test_a_null_byte_never_raises(self, root, fmt):
        reply = await DocumentSkill().execute(
            _task(filename="evil\x00.md", content_md="# Hi", format=fmt)
        )

        assert isinstance(reply, str) and reply.strip()
        assert "Traceback" not in reply

    @pytest.mark.asyncio
    async def test_control_characters_are_stripped_from_the_name(self, root):
        await DocumentSkill().execute(
            _task(filename="no\x00tes\x07.md", content_md="# Hi", format="md")
        )

        written = sorted(p.name for p in root.iterdir())
        assert written == ["notes.md"], written

    @pytest.mark.asyncio
    async def test_a_name_of_only_control_characters_is_refused(self, root):
        reply = await DocumentSkill().execute(
            _task(filename="\x00\x07", content_md="# Hi", format="md")
        )

        assert isinstance(reply, str) and reply.strip()
        assert not root.exists() or not list(root.iterdir())


class TestHostileFilenames:
    """A model-supplied filename is untrusted, and JSON permits a null byte.

    Every path call raises ValueError -- not OSError -- on an embedded null,
    so an unhandled one escaped execute() as a traceback. The assistant speaks
    its return value, and it cannot speak a stack trace.
    """

    NUL = chr(0)
    BEL = chr(7)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fmt", ["md", "html", "pdf"])
    async def test_a_null_byte_never_raises(self, root, fmt):
        reply = await DocumentSkill().execute(
            _task(filename="evil" + self.NUL + ".md", content_md="# Hi", format=fmt)
        )

        assert isinstance(reply, str) and reply.strip()
        assert "Traceback" not in reply

    @pytest.mark.asyncio
    async def test_control_characters_are_stripped_from_the_name(self, root):
        await DocumentSkill().execute(
            _task(
                filename="no" + self.NUL + "tes" + self.BEL + ".md",
                content_md="# Hi",
                format="md",
            )
        )

        written = sorted(p.name for p in root.iterdir())
        assert written == ["notes.md"], written

    @pytest.mark.asyncio
    async def test_a_name_of_only_control_characters_is_refused(self, root):
        reply = await DocumentSkill().execute(
            _task(filename=self.NUL + self.BEL, content_md="# Hi", format="md")
        )

        assert isinstance(reply, str) and reply.strip()
        assert not root.exists() or not list(root.iterdir())
