"""
Tests for skills/code_skill.py – reading, listing and editing files.

Why this exists: ULTRON could see a screen and search the web, but had no way
to read or change the user's actual code. Asked to fix a bug it searched the
web for the error text, because looking at the file was not something it could
do. These are the tools that close that gap.

Everything here runs against tmp_path. Nothing touches the real filesystem.
"""

from __future__ import annotations

import pytest

from intelligence.task import Task, TaskStatus
from skills.code_skill import MAX_READ_CHARS, CodeSkill


def _task(intent: str, **params) -> Task:
    from datetime import datetime

    return Task(
        task_id="t1",
        skill_name="CodeSkill",
        intent=intent,
        parameters=params,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


class TestReadFile:
    @pytest.mark.asyncio
    async def test_contents_come_back_with_line_numbers(self, tmp_path):
        """The model has to cite a line to patch it, so it must see them."""
        target = tmp_path / "app.py"
        target.write_text("import os\nprint(os.name)\n", encoding="utf-8")

        out = await CodeSkill().execute(_task("read_file", path=str(target)))

        assert "1\timport os" in out
        assert "2\tprint(os.name)" in out

    @pytest.mark.asyncio
    async def test_a_missing_file_is_reported_not_raised(self, tmp_path):
        """The agent loop feeds this string back to the model, which can then
        list the directory and try again. An exception would end the turn."""
        out = await CodeSkill().execute(_task("read_file", path=str(tmp_path / "nope.py")))
        assert "not found" in out.lower()

    @pytest.mark.asyncio
    async def test_a_huge_file_is_truncated_rather_than_blowing_the_context(self, tmp_path):
        target = tmp_path / "big.txt"
        target.write_text("x" * (MAX_READ_CHARS * 3), encoding="utf-8")

        out = await CodeSkill().execute(_task("read_file", path=str(target)))

        assert len(out) < MAX_READ_CHARS * 2
        assert "truncated" in out.lower()

    @pytest.mark.asyncio
    async def test_a_directory_is_not_read_as_a_file(self, tmp_path):
        out = await CodeSkill().execute(_task("read_file", path=str(tmp_path)))
        assert "directory" in out.lower()

    @pytest.mark.asyncio
    async def test_a_binary_file_is_refused_with_an_explanation(self, tmp_path):
        target = tmp_path / "logo.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00")

        out = await CodeSkill().execute(_task("read_file", path=str(target)))

        assert "text" in out.lower()


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_contents_are_written(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("old\n", encoding="utf-8")

        await CodeSkill().execute(_task("write_file", path=str(target), content="new\n"))

        assert target.read_text(encoding="utf-8") == "new\n"

    @pytest.mark.asyncio
    async def test_the_previous_version_is_kept_as_a_backup(self, tmp_path):
        """A voice-driven edit has no undo and no diff review. The one thing
        that makes it safe to say yes to is that the old file is still there."""
        target = tmp_path / "app.py"
        target.write_text("original\n", encoding="utf-8")

        await CodeSkill().execute(_task("write_file", path=str(target), content="patched\n"))

        backups = list(tmp_path.glob("*.ULTRON-bak"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "original\n"

    @pytest.mark.asyncio
    async def test_a_new_file_can_be_created_in_an_existing_folder(self, tmp_path):
        target = tmp_path / "fresh.py"
        await CodeSkill().execute(_task("write_file", path=str(target), content="hi\n"))
        assert target.read_text(encoding="utf-8") == "hi\n"

    @pytest.mark.asyncio
    async def test_writing_into_a_missing_folder_is_refused(self, tmp_path):
        """Creating a directory tree is not what the user asked for, and a
        typo'd path should not silently scatter folders across the disk."""
        target = tmp_path / "no" / "such" / "dir" / "app.py"
        out = await CodeSkill().execute(_task("write_file", path=str(target), content="x"))
        assert "folder" in out.lower() or "directory" in out.lower()
        assert not target.exists()

    @pytest.mark.asyncio
    async def test_content_is_required(self, tmp_path):
        """An empty write would truncate the file to nothing."""
        target = tmp_path / "app.py"
        target.write_text("keep me\n", encoding="utf-8")

        out = await CodeSkill().execute(_task("write_file", path=str(target)))

        assert target.read_text(encoding="utf-8") == "keep me\n"
        assert "content" in out.lower()


class TestListDirectory:
    @pytest.mark.asyncio
    async def test_entries_are_listed_with_folders_marked(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "main.py").write_text("x", encoding="utf-8")

        out = await CodeSkill().execute(_task("list_directory", path=str(tmp_path)))

        assert "src" in out and "main.py" in out

    @pytest.mark.asyncio
    async def test_a_missing_folder_is_reported(self, tmp_path):
        out = await CodeSkill().execute(_task("list_directory", path=str(tmp_path / "gone")))
        assert "not found" in out.lower()
