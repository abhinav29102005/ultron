"""
skills/file_skill.py – Open and find files, folders and applications
====================================================================
Three actions, deliberately: ``open``, ``find`` and ``create``.

There is no delete, move or rename here, and that is a design decision rather
than an omission. This runs on a voice path, behind a speech recogniser, on a
machine holding the user's own documents. "Delete my thesis draft" and "delete
my thesis" differ by one word that a microphone in a noisy room will happily
confuse.

Removing deletion is not on its own enough. ``os.startfile`` runs whatever it
is given, so a fuzzy match that lands on ``setup.bat`` executes it, and one
that lands on a ``.reg`` file offers to merge it into the registry. Executable
and script types are therefore never launched from a *guessed* match — only
from a path the user gave exactly. See ``EXECUTABLE_SUFFIXES``.

Path resolution is anchored on the user's home directory, never the working
directory: a background assistant is launched from wherever its shortcut
happened to point.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Iterator

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.file")

#: Where a search looks, in order. Missing folders are skipped.
SEARCH_ROOTS = (
    "Desktop",
    "OneDrive/Desktop",
    "Documents",
    "OneDrive/Documents",
    "Downloads",
    "Pictures",
    "Videos",
    "Music",
)

#: Never descended into. AppData alone holds hundreds of thousands of files
#: and nothing the user would ever ask for by name.
EXCLUDED_DIRS = frozenset(
    {
        "AppData",
        "Application Data",
        "node_modules",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "env",
        ".idea",
        ".vscode",
        "$RECYCLE.BIN",
        "System Volume Information",
        "site-packages",
        "dist-info",
        ".cache",
        ".next",
        "build",
        "target",
    }
)

#: Anything that runs code when opened. These are never launched from a fuzzy
#: match — only from a path the user typed or spoke exactly. Downloads is a
#: search root and is exactly where a "resume.pdf.exe" lands.
EXECUTABLE_SUFFIXES = frozenset(
    {
        ".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".msi", ".msp",
        ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
        ".hta", ".cpl", ".jar", ".reg", ".inf", ".lnk", ".url",
        ".sh", ".py", ".pyw", ".rb", ".pl", ".app",
    }
)

#: Reserved Windows device names. os.path.exists("~/NUL") is True, and opening
#: one is never what the user meant.
RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

#: Depth below each root. Four levels reaches anything a person filed by hand
#: and stops before it reaches a checked-out dependency tree.
MAX_DEPTH = 4

#: Shortest needle allowed to match as a substring. Without this a stray
#: recogniser token like "a" or "it" scores nearly 1.0 against dozens of files.
MIN_SUBSTRING_LEN = 3

#: A fuzzy ratio below this is not a match at all.
FUZZY_MIN = 0.75

#: Fuzzy matches are compressed into [0.55, 0.70] so they can never outrank a
#: real substring hit, which starts at 0.76. Without this the two bands
#: overlapped and "windows.media.speechsynthesis.h" outranked the actual
#: thesis for the needle "thesis".
FUZZY_FLOOR = 0.55
FUZZY_CEILING = 0.70

#: Below this a candidate is discarded.
MIN_SCORE = 0.55

#: Total entries examined across every root, not per root.
MAX_ENTRIES = 60_000


@dataclass(frozen=True)
class Match:
    path: str
    score: float

    @property
    def display(self) -> str:
        return os.path.basename(self.path) or self.path


def _is_inside(path: str, root: str) -> bool:
    """Whether ``path`` sits under ``root``.

    ``commonpath`` raises rather than returning when the two are on different
    drives, which is a "no", not an error to show the user.
    """
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


class FileSkill(Skill):
    name = "FileSkill"
    description = "Opens files, folders and applications, and finds files by name."
    version = "1.1.0"
    enabled = True

    # ---------------------------------------------------------------- paths
    def _home(self) -> str:
        return os.path.expanduser("~")

    def _search_roots(self) -> list[str]:
        home = self._home()
        roots = []
        for relative in SEARCH_ROOTS:
            candidate = os.path.join(home, *relative.split("/"))
            if os.path.isdir(candidate):
                roots.append(candidate)
        return roots

    def _resolve(self, raw: str) -> str:
        """Turn a spoken name into an absolute path under the user's home.

        A path the user gave as absolute is honoured — they were explicit.
        Everything else must land inside the home directory once fully
        resolved. "Fully" is the important word: the check runs after
        ``expandvars``, ``expanduser`` and ``realpath``, because each of those
        is otherwise an escape hatch. ``%APPDATA%\\..\\..\\..`` looks relative
        and expands to an absolute path outside home; a junction under
        Documents is lexically inside it and physically anywhere.
        """
        raw = (raw or "").strip().strip('"').strip("'")
        if not raw:
            raise ValueError("No file or folder name given.")

        # A UNC path is absolute, so the "user was explicit" rule would wave
        # it through and os.startfile would run something off a remote share.
        if raw.startswith("\\\\") or raw.startswith("//"):
            raise ValueError("I don't open files from network shares.")

        # Judged on what the user actually said, before any expansion: a
        # string that only becomes absolute through %VARS% was not explicit.
        was_absolute = os.path.isabs(raw)

        expanded = os.path.expanduser(os.path.expandvars(raw))
        if os.path.isabs(expanded):
            candidate = expanded
        else:
            candidate = os.path.join(self._home(), expanded)

        # realpath, not normpath: normpath is purely lexical and a junction
        # (which os.path.islink reports as False on Windows) would sail past.
        candidate = os.path.realpath(os.path.normpath(candidate))

        stem = os.path.splitext(os.path.basename(candidate))[0].upper()
        if stem in RESERVED_NAMES:
            raise ValueError(f'"{raw}" is a reserved device name, not a file.')

        if not was_absolute and not _is_inside(candidate, os.path.realpath(self._home())):
            raise ValueError(
                f'"{raw}" points outside your home folder. '
                "Give the full path if you meant that."
            )
        return candidate

    # --------------------------------------------------------------- search
    def _walk(self, root: str, budget: list[int]) -> Iterator[tuple[str, bool]]:
        """Yield (path, is_dir) under root, bounded by depth and a shared budget."""
        root_depth = root.rstrip(os.sep).count(os.sep)

        for current, dirs, files in os.walk(root, topdown=True):
            depth = current.count(os.sep) - root_depth
            if depth >= MAX_DEPTH:
                dirs[:] = []
            # Pruned in place so os.walk never descends into them at all.
            dirs[:] = [
                d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")
            ]

            for name in dirs:
                budget[0] -= 1
                if budget[0] <= 0:
                    logger.debug("Search stopped at the entry budget.")
                    return
                yield os.path.join(current, name), True

            for name in files:
                if name.startswith("."):
                    continue
                budget[0] -= 1
                if budget[0] <= 0:
                    logger.debug("Search stopped at the entry budget.")
                    return
                yield os.path.join(current, name), False

    def _score(self, needle: str, filename: str) -> float:
        """How well a filename matches what the user said.

        The bands do not overlap, and that is the point. An exact name beats a
        prefix, which beats a substring, which beats any fuzzy match at all.
        When these were one continuous scale, a file whose letters merely
        overlapped could outrank the file the user actually named.
        """
        needle = (needle or "").strip().lower()
        if not needle:
            return 0.0

        full = filename.lower()
        stem = os.path.splitext(full)[0]

        if needle == full:
            return 1.0
        if needle == stem:
            return 0.98

        best = 0.0
        for candidate in (full, stem):
            if not candidate:
                continue

            if len(needle) >= MIN_SUBSTRING_LEN:
                if candidate.startswith(needle):
                    # Shorter names win: "budget" should prefer budget.xlsx
                    # over "budget notes from the old laptop.docx".
                    best = max(best, 0.89 + 0.08 * (len(needle) / len(candidate)))
                elif needle in candidate:
                    best = max(best, 0.76 + 0.11 * (len(needle) / len(candidate)))

            # The user said more than the filename holds: "open my budget
            # spreadsheet" against budget.xlsx. Without this the extra words
            # drag the ratio below the threshold and the right file vanishes.
            #
            # The candidate has to appear as a whole word, not merely as
            # letters inside one: "sum.c" sits inside "re|sum|e" and was
            # scoring 0.82 against a request for the user's resume.
            if len(candidate) >= MIN_SUBSTRING_LEN and re.search(
                rf"\b{re.escape(candidate)}\b", needle
            ):
                best = max(best, 0.76 + 0.11 * (len(candidate) / len(needle)))

            ratio = difflib.SequenceMatcher(None, needle, candidate).ratio()
            if ratio >= FUZZY_MIN:
                scaled = FUZZY_FLOOR + (FUZZY_CEILING - FUZZY_FLOOR) * (
                    (ratio - FUZZY_MIN) / (1.0 - FUZZY_MIN)
                )
                best = max(best, scaled)

        return best

    def find(self, needle: str, limit: int = 5) -> list[Match]:
        """Best matches for a name, across the user's own folders.

        Returns at most ``limit``; use :meth:`find_all` when the true count
        matters.
        """
        return self.find_all(needle)[:limit]

    def find_all(self, needle: str) -> list[Match]:
        needle = (needle or "").strip()
        if not needle:
            return []

        budget = [MAX_ENTRIES]
        matches: list[Match] = []
        for root in self._search_roots():
            if budget[0] <= 0:
                break
            for path, _is_dir in self._walk(root, budget):
                score = self._score(needle, os.path.basename(path))
                if score >= MIN_SCORE:
                    matches.append(Match(path=path, score=score))

        matches.sort(key=lambda m: (-m.score, len(m.path)))
        return matches

    # ----------------------------------------------------------------- open
    def _launch(self, path: str) -> None:
        system = platform.system()
        if system == "Windows":
            os.startfile(path)  # noqa: S606 - the point of the skill
        elif system == "Darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)

    def _is_executable(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in EXECUTABLE_SUFFIXES

    def _open_path(self, raw: str) -> str:
        # An existing path is unambiguous; take it before guessing.
        try:
            direct = self._resolve(raw)
        except ValueError as exc:
            return str(exc)

        if os.path.exists(direct):
            self._launch(direct)
            kind = "folder" if os.path.isdir(direct) else "file"
            return f"Opened the {kind} {os.path.basename(direct) or direct}."

        matches = self.find(raw)
        if not matches:
            return f'I couldn\'t find anything called "{raw}".'

        best = matches[0]

        # A guessed match is not permission to run a program. "open setup"
        # scores an exact 1.0 against setup.bat, and a .reg file would be
        # merged into the registry.
        if self._is_executable(best.path):
            safe = next((m for m in matches if not self._is_executable(m.path)), None)
            if safe is None:
                return (
                    f"The closest match to \"{raw}\" is {best.display}, which runs "
                    "code. I won't launch that from a guess — open it yourself, "
                    "or give me the full path."
                )
            best = safe

        self._launch(best.path)

        # Near-ties are worth mentioning: opening the wrong file silently is
        # more annoying than a one-line "there were others".
        others = [
            m for m in matches
            if m is not best and best.score - m.score < 0.05
        ]
        if others:
            names = ", ".join(m.display for m in others[:2])
            return f"Opened {best.display}. There were others too: {names}."
        return f"Opened {best.display}."

    # --------------------------------------------------------------- actions
    def _create(self, target: str) -> str:
        path = self._resolve(target)

        if os.path.isdir(path):
            return f"{os.path.basename(path)} already exists."
        if os.path.exists(path):
            return (
                f"There's already a file called {os.path.basename(path)} there, "
                "so I haven't made a folder with that name."
            )

        # "create a file called notes.txt" would otherwise silently produce a
        # *folder* named notes.txt, which then poisons every later "open notes".
        suffix = os.path.splitext(path)[1]
        if suffix and suffix.lower() not in {".d", ""}:
            return (
                f'"{os.path.basename(path)}" looks like a file name. I can make '
                "folders, not files — say it without the extension if you meant "
                "a folder."
            )

        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            return f"I couldn't create that folder: {exc.strerror or exc}."
        return f"Created the folder {os.path.basename(path)}."

    def _run(self, action: str, target: str) -> str:
        """The blocking part, run off the event loop by execute()."""
        if action == "find":
            matches = self.find_all(target)
            if not matches:
                return f'I couldn\'t find anything called "{target}".'
            if len(matches) == 1:
                return (
                    f"I found {matches[0].display} in "
                    f"{os.path.dirname(matches[0].path)}."
                )
            names = ", ".join(m.display for m in matches[:3])
            return (
                f"I found {len(matches)}: {names}. Say open and the name to open one."
            )

        if action == "create":
            try:
                return self._create(target)
            except ValueError as exc:
                return str(exc)

        if action == "open":
            return self._open_path(target)

        return (
            f'I can open, find and create things, but not "{action}". '
            "Deleting and moving files aren't something I do."
        )

    async def execute(self, task: Task) -> str:
        params = task.parameters or {}
        action = (params.get("action") or "open").lower()
        target = (
            params.get("target")
            or params.get("file_name")
            or params.get("folder_name")
            or params.get("query")
            or ""
        )

        # A search walks thousands of directory entries. Doing that on the
        # event loop freezes audio, TTS and barge-in for its whole duration —
        # on the very path the barge-in work exists to keep responsive.
        return await asyncio.to_thread(self._run, action, target)
