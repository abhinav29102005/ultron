"""
tests/test_file_skill_hardening.py – Regressions from adversarial review
========================================================================
Every case here reproduced against a real filesystem before the fix. They are
kept apart from test_file_skill.py because that file covers the feature and
this one covers the ways it was got wrong.
"""

from __future__ import annotations

import asyncio
import os

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    for name in ("Desktop", "Documents", "Downloads"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(
        os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p
    )
    return tmp_path


@pytest.fixture
def skill(home):
    from skills.file_skill import FileSkill

    return FileSkill(container=None)


class FakeTask:
    def __init__(self, parameters=None):
        self.intent = "file_search"
        self.parameters = parameters or {}
        self.metadata = {}


# ============================================================ code execution
class TestExecutablesAreNotLaunchedFromAGuess:
    """os.startfile runs whatever it is given; a fuzzy match is not consent.

    Before the fix, "open setup" scored an exact 1.0 against setup.bat and ran
    it, and a .reg match would have been offered for merge into the registry.
    """

    @pytest.mark.asyncio
    async def test_bat_is_not_executed_by_a_fuzzy_match(
        self, home, skill, monkeypatch
    ):
        (home / "Desktop" / "setup.bat").write_text("x")
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        result = await skill.execute(FakeTask({"action": "open", "target": "setup"}))

        assert not any(p.endswith(".bat") for p in launched)
        assert "won't launch" in result

    @pytest.mark.asyncio
    async def test_reg_is_not_merged_into_the_registry(
        self, home, skill, monkeypatch
    ):
        (home / "Desktop" / "installer.reg").write_text("x")
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        await skill.execute(FakeTask({"action": "open", "target": "installer"}))
        assert not any(p.endswith(".reg") for p in launched)

    @pytest.mark.asyncio
    async def test_a_safe_match_is_preferred_over_an_executable(
        self, home, skill, monkeypatch
    ):
        (home / "Desktop" / "report.exe").write_text("x")
        (home / "Desktop" / "report.pdf").write_text("x")
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        await skill.execute(FakeTask({"action": "open", "target": "report"}))
        assert launched == [str(home / "Desktop" / "report.pdf")]

    @pytest.mark.asyncio
    async def test_an_explicit_path_to_an_executable_is_honoured(
        self, home, skill, monkeypatch
    ):
        """Being explicit is different from us guessing."""
        exe = home / "Desktop" / "tool.exe"
        exe.write_text("x")
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        await skill.execute(FakeTask({"action": "open", "target": "Desktop/tool.exe"}))
        assert launched == [os.path.normpath(str(exe))]

    @pytest.mark.asyncio
    async def test_when_only_executables_match_nothing_is_launched(
        self, home, skill, monkeypatch
    ):
        (home / "Desktop" / "wiper.cmd").write_text("x")
        launched = []
        monkeypatch.setattr(skill, "_launch", launched.append)

        result = await skill.execute(FakeTask({"action": "open", "target": "wiper"}))
        assert launched == []
        assert "won't launch" in result


# ================================================================== scoring
class TestScoringBandsDoNotOverlap:
    def test_real_file_beats_a_coincidental_letter_overlap(self, skill):
        # "syn|thesis" contains "thesis" literally; this was the actual top
        # hit for find("thesis") on the author's machine.
        wrong = skill._score("thesis", "windows.media.speechsynthesis.h")
        right = skill._score("thesis", "thesis final draft 2026.docx")
        assert right > wrong

    def test_spaced_name_does_not_beat_the_real_prefix(self, skill):
        assert skill._score("budget", "budget report.xlsx") > skill._score(
            "budget", "bud get.txt"
        )

    def test_exact_name_beats_a_backup_of_it(self, skill):
        assert skill._score("notes.txt", "notes.txt") > skill._score(
            "notes.txt", "notes.txt.bak"
        )

    def test_needle_longer_than_the_filename_still_matches(self, skill):
        from skills.file_skill import MIN_SCORE

        # The intent prompt uses exactly this phrasing as its worked example.
        assert skill._score("budget spreadsheet", "budget.xlsx") >= MIN_SCORE

    def test_one_and_two_character_tokens_match_nothing(self, home, skill):
        (home / "Desktop" / "it.txt").write_text("x")
        (home / "Desktop" / "AI").mkdir()
        for stray in ("a", "s", "of"):
            assert skill.find(stray) == [], f"{stray!r} matched something"

    def test_a_filename_buried_inside_a_word_is_not_a_match(self, home, skill):
        """"sum.c" sits inside "re|sum|e" and was matching a request for the
        user's resume."""
        (home / "Desktop" / "sum.c").write_text("x")
        (home / "Desktop" / "Resume.pdf").write_text("x")

        assert skill._score("resume", "sum.c") == 0.0
        assert [m.display for m in skill.find("resume")] == ["Resume.pdf"]

    def test_a_whole_word_inside_the_phrase_still_matches(self, home, skill):
        (home / "Desktop" / "budget.xlsx").write_text("x")
        assert skill.find("my budget spreadsheet")[0].display == "budget.xlsx"

    def test_shorter_name_wins_among_prefixes(self, home, skill):
        (home / "Desktop" / "budget.xlsx").write_text("x")
        (home / "Desktop" / "budget notes from the old laptop.docx").write_text("x")
        assert skill.find("budget")[0].display == "budget.xlsx"


# =============================================================== containment
class TestContainmentCannotBeEscaped:
    @pytest.mark.parametrize(
        "escape",
        [
            r"%APPDATA%\..\..\..\..\Windows\System32",
            r"%COMSPEC%",
            "~/../../Windows",
            r"%USERPROFILE%\..\Public",
        ],
    )
    def test_variable_expansion_is_not_an_escape_hatch(self, skill, escape):
        """Each of these resolved to an accepted path outside home before."""
        with pytest.raises(ValueError):
            skill._resolve(escape)

    def test_unc_paths_are_refused(self, skill):
        with pytest.raises(ValueError) as excinfo:
            skill._resolve("\\\\server\\share\\evil.exe")
        assert "network" in str(excinfo.value)

    def test_forward_slash_unc_is_refused(self, skill):
        with pytest.raises(ValueError):
            skill._resolve("//server/share/evil.exe")

    def test_cross_drive_is_a_refusal_not_an_internal_error(self, skill):
        """commonpath raises on different drives; the user must not hear it."""
        with pytest.raises(ValueError) as excinfo:
            skill._resolve("Z:evil")
        assert "same drive" not in str(excinfo.value)
        assert "outside your home folder" in str(excinfo.value)

    def test_reserved_device_names_are_refused(self, skill):
        for name in ("NUL", "CON", "com1"):
            with pytest.raises(ValueError) as excinfo:
                skill._resolve(name)
            assert "reserved device" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_create_refuses_cross_drive_without_raising(self, skill):
        """This propagated a raw ValueError out of execute() before the fix."""
        result = await skill.execute(FakeTask({"action": "create", "target": "Z:evil"}))
        assert isinstance(result, str)
        assert "same drive" not in result


# ==================================================================== create
class TestCreateEdgeCases:
    @pytest.mark.asyncio
    async def test_existing_file_survives_and_no_winerror_leaks(self, home, skill):
        target = home / "Documents" / "important.txt"
        target.write_text("precious")

        result = await skill.execute(
            FakeTask({"action": "create", "target": "Documents/important.txt"})
        )

        assert target.read_text() == "precious"
        assert "WinError" not in result and "Errno" not in result

    @pytest.mark.asyncio
    async def test_file_shaped_name_does_not_silently_become_a_folder(
        self, home, skill
    ):
        result = await skill.execute(
            FakeTask({"action": "create", "target": "Documents/notes.txt"})
        )
        assert not (home / "Documents" / "notes.txt").is_dir(), (
            "created a folder named notes.txt, poisoning every later 'open notes'"
        )
        assert "looks like a file name" in result


# ================================================= reporting, budget, latency
class TestReportingAndBudget:
    def test_find_caps_but_find_all_does_not(self, home, skill):
        for i in range(12):
            (home / "Documents" / f"report {i}.txt").write_text("x")

        assert len(skill.find("report")) == 5
        assert len(skill.find_all("report")) == 12

    @pytest.mark.asyncio
    async def test_spoken_count_is_the_true_one(self, home, skill):
        for i in range(12):
            (home / "Documents" / f"report {i}.txt").write_text("x")

        result = await skill.execute(FakeTask({"action": "find", "target": "report"}))
        assert "I found 12" in result, "the truncated count was reported as the total"

    def test_entry_budget_is_shared_across_roots(self, home, skill, monkeypatch):
        import skills.file_skill as fs

        monkeypatch.setattr(fs, "MAX_ENTRIES", 5)
        for root in ("Desktop", "Documents", "Downloads"):
            for i in range(10):
                (home / root / f"budget{i}.txt").write_text("x")

        # A per-root budget would allow up to 3 x 5 here.
        assert len(skill.find_all("budget")) <= 5


class TestSearchDoesNotBlockTheEventLoop:
    @pytest.mark.asyncio
    async def test_execute_yields_to_the_loop(self, skill, monkeypatch):
        """A synchronous walk froze audio and barge-in for its whole duration.

        The work is stubbed with a fixed sleep rather than a real search: a
        search over a temp tree finishes faster than one heartbeat tick, so a
        real one would pass whether or not it ran on the loop.
        """
        import time

        monkeypatch.setattr(
            skill, "_run", lambda action, target: (time.sleep(0.25), "done")[1]
        )

        ticks = 0

        async def _heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.005)
                ticks += 1

        beat = asyncio.ensure_future(_heartbeat())
        try:
            result = await skill.execute(FakeTask({"action": "find", "target": "x"}))
        finally:
            beat.cancel()

        assert result == "done"
        assert ticks > 10, (
            f"the loop ticked only {ticks} times during a 250ms search; "
            "the work is running on the event loop"
        )
