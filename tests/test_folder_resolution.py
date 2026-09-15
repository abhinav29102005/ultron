"""
Tests for FolderSkill path resolution – W7.

The user's complaint: "it can't open my folders and I have to be quite
specific". The resolver only matched exact singular known names and otherwise
joined the words straight onto the home directory, so "open my download
folder" resolved to ``~/download folder`` -- which does not exist -- and
"open my project folder" never found the project sitting on the Desktop.

Three widenings, in the order they are tried:

  * the spoken plural/singular slip ("download" for Downloads);
  * the filler words a person says around a folder name ("my", "folder");
  * an actual look on disk, one level under home and Desktop, when the name
    is not a known shortcut at all.

The disk search is last on purpose: it costs a directory listing, and the
known shortcuts answer the common case without touching the filesystem.
"""

from __future__ import annotations

import os

import pytest

from skills.System import FolderSkill


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home directory with the usual folders and a project."""
    for name in ("Desktop", "Downloads", "Documents", "Pictures"):
        (tmp_path / name).mkdir()
    (tmp_path / "Desktop" / "friday-agent-main").mkdir()
    (tmp_path / "Desktop" / "Physics Notes").mkdir()
    (tmp_path / "Documents" / "academic info").mkdir()

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


class TestKnownShortcuts:
    """The existing behaviour, which must keep working."""

    def test_an_exact_known_name(self, home):
        assert FolderSkill()._resolve_path("downloads") == str(home / "Downloads")

    def test_a_nested_subpath_under_a_shortcut(self, home):
        resolved = FolderSkill()._resolve_path("docs academic info")
        assert resolved == str(home / "Documents" / "academic info")

    def test_an_absolute_path_is_used_as_is(self, home):
        assert FolderSkill()._resolve_path(str(home / "Pictures")) == str(home / "Pictures")


class TestSpokenVariations:
    @pytest.mark.parametrize(
        "spoken,expected",
        [
            ("download", "Downloads"),
            ("Downloads", "Downloads"),
            ("DOWNLOAD", "Downloads"),
            ("document", "Documents"),
            ("picture", "Pictures"),
            ("my downloads", "Downloads"),
            ("the downloads folder", "Downloads"),
            ("my downloads folder", "Downloads"),
            ("downloads directory", "Downloads"),
        ],
    )
    def test_singular_plural_and_filler_words(self, home, spoken, expected):
        """Speech does not reliably produce the exact folder name."""
        assert FolderSkill()._resolve_path(spoken) == str(home / expected)


class TestSearchingDisk:
    def test_a_folder_on_the_desktop_is_found_by_name(self, home):
        """"open my physics notes" should not need the full path."""
        resolved = FolderSkill()._resolve_path("physics notes")
        assert resolved == str(home / "Desktop" / "Physics Notes")

    def test_a_partial_name_matches(self, home):
        resolved = FolderSkill()._resolve_path("friday agent")
        assert resolved == str(home / "Desktop" / "friday-agent-main")

    def test_a_known_shortcut_still_wins_over_a_disk_search(self, home):
        """A folder named "Downloads" on the Desktop must not shadow the real
        Downloads folder."""
        (home / "Desktop" / "Downloads").mkdir()
        assert FolderSkill()._resolve_path("downloads") == str(home / "Downloads")

    def test_an_unknown_name_falls_back_to_the_home_directory(self, home):
        """Unchanged behaviour: something has to be returned, and the caller
        reports that it does not exist."""
        resolved = FolderSkill()._resolve_path("nothing like this exists")
        assert resolved.startswith(str(home))

    def test_an_empty_name_is_still_refused(self, home):
        with pytest.raises(ValueError):
            FolderSkill()._resolve_path("   ")


class TestEmptyFolderTiebreak:
    """An empty folder is almost never the one somebody means.

    Found live: the user has a stray empty ``~/friday agent`` left over from
    an earlier session, and their real project is ``~/Desktop/friday-agent-main``.
    The empty one won on an exact-name match -- correct by the scoring rules
    and useless in practice, because "open my friday agent project" opened an
    empty folder.

    Exact-name matching still wins over a prefix match; this only breaks the
    tie between two candidates that scored the same.
    """

    def test_a_populated_folder_beats_an_empty_one_at_the_same_score(self, home):
        (home / "project").mkdir()  # empty, in home
        (home / "Desktop" / "project").mkdir()
        (home / "Desktop" / "project" / "main.py").write_text("x", encoding="utf-8")

        assert FolderSkill._search_disk("project") == str(home / "Desktop" / "project")

    def test_an_exact_match_still_beats_a_mere_prefix(self, home):
        """The tiebreak must not promote a loosely-matching folder over the
        one the user actually named."""
        (home / "notes").mkdir()
        (home / "notes" / "a.txt").write_text("x", encoding="utf-8")
        (home / "Desktop" / "notes-archive-2024").mkdir()
        (home / "Desktop" / "notes-archive-2024" / "b.txt").write_text("x", encoding="utf-8")

        assert FolderSkill._search_disk("notes") == str(home / "notes")

    def test_an_empty_folder_is_still_found_when_it_is_the_only_match(self, home):
        (home / "Desktop" / "solo").mkdir()
        assert FolderSkill._search_disk("solo") == str(home / "Desktop" / "solo")

    def test_a_populated_near_match_beats_an_empty_exact_match(self, home):
        """The exact live case: an empty ~/"friday agent" left over from an
        old session, against the real ~/Desktop/friday-agent-main.

        Emptiness is strong evidence of a stub. A folder with nothing in it
        cannot be the project somebody is asking to open, even when its name
        is a perfect match.
        """
        (home / "friday agent").mkdir()  # empty leftover
        # friday-agent-main already exists on the fixture's Desktop; give it
        # contents so it is a real project rather than another empty stub.
        real = home / "Desktop" / "friday-agent-main"
        (real / "main.py").write_text("x", encoding="utf-8")

        assert FolderSkill._search_disk("friday agent") == str(real)
