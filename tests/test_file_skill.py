"""
tests/test_file_skill.py – Finding and opening files by name
=============================================================
The skill runs behind a speech recogniser on the user's own machine, so the
tests care as much about what it refuses to do as what it does.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home directory with a realistic shape."""
    (tmp_path / "Desktop").mkdir()
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Documents" / "work").mkdir()

    (tmp_path / "Desktop" / "budget.xlsx").write_text("x")
    (tmp_path / "Documents" / "Resume 2026.pdf").write_text("x")
    (tmp_path / "Documents" / "work" / "thesis draft.docx").write_text("x")
    (tmp_path / "Downloads" / "installer.exe").write_text("x")

    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    return tmp_path


@pytest.fixture
def skill(home):
    from skills.file_skill import FileSkill

    return FileSkill(container=None)


class FakeTask:
    def __init__(self, parameters=None, intent="file_search"):
        self.intent = intent
        self.parameters = parameters or {}
        self.metadata = {}


class TestFind:
    def test_exact_name(self, skill):
        matches = skill.find("budget")
        assert matches
        assert os.path.basename(matches[0].path) == "budget.xlsx"

    def test_case_insensitive(self, skill):
        assert skill.find("BUDGET")[0].display == "budget.xlsx"

    def test_partial_name(self, skill):
        assert skill.find("resume")[0].display == "Resume 2026.pdf"

    def test_fuzzy_name_survives_a_misheard_word(self, skill):
        """Speech recognition is lossy; near misses still have to land."""
        assert skill.find("thesis draf")[0].display == "thesis draft.docx"

    def test_nested_folders_are_searched(self, skill):
        assert skill.find("thesis")[0].display == "thesis draft.docx"

    def test_unknown_name_finds_nothing(self, skill):
        assert skill.find("quarterly amphibian census") == []

    def test_empty_needle_finds_nothing(self, skill):
        assert skill.find("") == []
        assert skill.find("   ") == []

    def test_substring_beats_fuzzy(self, home, skill):
        (home / "Desktop" / "report.txt").write_text("x")
        (home / "Desktop" / "rulebook.txt").write_text("x")

        best = skill.find("report")[0]
        assert best.display == "report.txt"


class TestSearchBoundaries:
    def test_excluded_directories_are_never_walked(self, home, skill):
        appdata = home / "AppData" / "Roaming"
        appdata.mkdir(parents=True)
        (home / "AppData" / "secret.txt").write_text("x")
        (appdata / "budget.xlsx").write_text("x")

        # Compared relative to the fake home: pytest's own tmp dir lives under
        # a real AppData, so a substring check on the absolute path would pass
        # for the wrong reason.
        found = [os.path.relpath(m.path, str(home)) for m in skill.find("budget")]
        assert not any(p.startswith("AppData") for p in found)
        assert found, "the sibling file outside AppData should still be found"

    def test_node_modules_is_skipped(self, home, skill):
        nm = home / "Documents" / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "readme.md").write_text("x")

        assert not any("node_modules" in m.path for m in skill.find("readme"))

    def test_hidden_directories_are_skipped(self, home, skill):
        hidden = home / "Documents" / ".git"
        hidden.mkdir()
        (hidden / "config").write_text("x")

        assert not any(".git" in m.path for m in skill.find("config"))

    def test_depth_cap_holds(self, home, skill):
        from skills.file_skill import MAX_DEPTH

        deep = home / "Documents"
        for i in range(MAX_DEPTH + 3):
            deep = deep / f"level{i}"
            deep.mkdir()
        (deep / "buried.txt").write_text("x")

        assert skill.find("buried") == []

    def test_only_the_users_own_folders_are_searched(self, home, skill):
        elsewhere = home / "SomeOtherPlace"
        elsewhere.mkdir()
        (elsewhere / "budget.xlsx").write_text("x")

        found = [m.path for m in skill.find("budget")]
        assert not any("SomeOtherPlace" in p for p in found)


class TestPathResolution:
    def test_relative_names_resolve_under_home_not_cwd(self, home, skill):
        resolved = skill._resolve("Documents")
        assert resolved == os.path.normpath(str(home / "Documents"))

    def test_absolute_paths_are_honoured(self, skill, tmp_path):
        other = tmp_path.parent / "elsewhere"
        assert skill._resolve(str(other)) == os.path.normpath(str(other))

    def test_escaping_home_with_dotdot_is_refused(self, skill):
        with pytest.raises(ValueError) as excinfo:
            skill._resolve("../../Windows/System32")
        assert "outside your home folder" in str(excinfo.value)

    def test_empty_name_is_refused(self, skill):
        with pytest.raises(ValueError):
            skill._resolve("   ")

    def test_quotes_are_stripped(self, home, skill):
        assert skill._resolve('"Documents"') == os.path.normpath(
            str(home / "Documents")
        )


class TestActions:
    @pytest.mark.asyncio
    async def test_open_launches_the_best_match(self, skill, monkeypatch):
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        result = await skill.execute(
            FakeTask({"action": "open", "target": "budget"})
        )

        assert len(launched) == 1
        assert launched[0].endswith("budget.xlsx")
        assert "budget.xlsx" in result

    @pytest.mark.asyncio
    async def test_open_prefers_an_exact_existing_path(self, home, skill, monkeypatch):
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        await skill.execute(FakeTask({"action": "open", "target": "Documents"}))
        assert launched == [os.path.normpath(str(home / "Documents"))]

    @pytest.mark.asyncio
    async def test_open_reports_a_miss_without_launching(self, skill, monkeypatch):
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        result = await skill.execute(
            FakeTask({"action": "open", "target": "nonexistent thing"})
        )
        assert launched == []
        assert "couldn't find" in result

    @pytest.mark.asyncio
    async def test_find_reports_without_launching(self, skill, monkeypatch):
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        result = await skill.execute(
            FakeTask({"action": "find", "target": "resume"})
        )
        assert launched == []
        assert "Resume 2026.pdf" in result

    @pytest.mark.asyncio
    async def test_create_makes_the_folder(self, home, skill):
        result = await skill.execute(
            FakeTask({"action": "create", "target": "Documents/new project"})
        )
        assert (home / "Documents" / "new project").is_dir()
        assert "Created" in result

    @pytest.mark.asyncio
    async def test_create_is_idempotent(self, skill):
        await skill.execute(FakeTask({"action": "create", "target": "Documents/twice"}))
        result = await skill.execute(
            FakeTask({"action": "create", "target": "Documents/twice"})
        )
        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_delete_is_refused(self, skill, monkeypatch):
        """A misheard word must not be able to destroy the user's files."""
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        result = await skill.execute(
            FakeTask({"action": "delete", "target": "budget"})
        )
        assert launched == []
        assert "budget.xlsx" not in result
        assert os.path.exists(str(skill._home() + "/Desktop/budget.xlsx"))

    @pytest.mark.asyncio
    async def test_move_and_rename_are_refused(self, skill):
        for action in ("move", "rename", "trash"):
            result = await skill.execute(
                FakeTask({"action": action, "target": "budget"})
            )
            assert "aren't something I do" in result

    @pytest.mark.asyncio
    async def test_action_defaults_to_open(self, skill, monkeypatch):
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        await skill.execute(FakeTask({"target": "budget"}))
        assert len(launched) == 1

    @pytest.mark.asyncio
    async def test_alternate_parameter_names_are_accepted(self, skill, monkeypatch):
        """The planner passes whatever the model called the entity."""
        monkeypatch.setattr(skill, "_launch", lambda p: None)

        for key in ("target", "file_name", "folder_name", "query"):
            result = await skill.execute(FakeTask({"action": "find", key: "budget"}))
            assert "budget.xlsx" in result, f"parameter {key!r} was ignored"


class TestApplicationFallback:
    def test_claude_is_a_known_alias(self):
        from skills.system_skills import ApplicationSkill

        assert ApplicationSkill.APP_ALIASES["claude"] == "claude"

    def test_unknown_app_falls_back_to_the_start_menu(self, tmp_path, monkeypatch):
        from skills.system_skills import ApplicationSkill

        programs = tmp_path / "Programs"
        programs.mkdir()
        (programs / "Claude.lnk").write_text("")

        skill = ApplicationSkill(container=None)
        monkeypatch.setattr(skill, "START_MENU_DIRS", (str(programs),))

        found = skill._find_start_menu_shortcut("claude")
        assert found is not None and found.endswith("Claude.lnk")

    def test_start_menu_prefers_the_app_over_its_uninstaller(
        self, tmp_path, monkeypatch
    ):
        from skills.system_skills import ApplicationSkill

        programs = tmp_path / "Programs"
        programs.mkdir()
        (programs / "Uninstall Claude.lnk").write_text("")
        (programs / "Claude.lnk").write_text("")

        skill = ApplicationSkill(container=None)
        monkeypatch.setattr(skill, "START_MENU_DIRS", (str(programs),))

        assert skill._find_start_menu_shortcut("claude").endswith(
            os.sep + "Claude.lnk"
        )

    def test_no_shortcut_returns_none(self, tmp_path, monkeypatch):
        from skills.system_skills import ApplicationSkill

        programs = tmp_path / "Programs"
        programs.mkdir()

        skill = ApplicationSkill(container=None)
        monkeypatch.setattr(skill, "START_MENU_DIRS", (str(programs),))

        assert skill._find_start_menu_shortcut("something nobody installed") is None


class TestFileRouting:
    def test_file_search_reaches_the_file_skill(self):
        from intelligence.router import TaskRouter
        from skills.file_skill import FileSkill

        assert TaskRouter.ROUTING_TABLE["file_search"] is FileSkill

    def test_folder_operations_still_reach_the_folder_skill(self):
        from intelligence.router import TaskRouter
        from skills.System import FolderSkill

        assert TaskRouter.ROUTING_TABLE["file_operation"] is FolderSkill

    def test_intent_is_accepted_by_the_detector(self):
        from intelligence.intent_detector import IntentDetector

        assert "file_search" in IntentDetector.VALID_INTENTS
