"""
skills/code_skill.py – Read, list and edit files
=================================================
The hands FRIDAY did not have.

Asked to fix a bug, FRIDAY used to search the web for the error text -- not
because searching seemed right, but because reading the user's file was not
something it could do at all. Three tools close that: list a folder, read a
file, write a file.

Safety is deliberately boring rather than clever:

  * a write always leaves the previous version beside the file as
    ``.friday-bak``. A voice-driven edit has no diff review and no undo, so
    the recoverable copy is the whole safety story;
  * a write refuses to create missing parent folders, because a misheard path
    should not scatter directories across the disk;
  * an empty write is refused, since it can only ever truncate;
  * reads are capped, so one large file cannot eat the model's context.

The agent loop asks the user before any write reaches this skill -- see
``confirm`` on the tool definition in ``intelligence/tool_registry.py``.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.code")

#: How much of a file the model may see at once. Roughly 15k tokens, which
#: leaves room for the conversation and the answer in a modest context window.
MAX_READ_CHARS = 60_000

#: Entries listed before the listing is cut short. A node_modules folder must
#: not become the whole turn.
MAX_LIST_ENTRIES = 200

#: Suffix for the copy kept beside an overwritten file.
BACKUP_SUFFIX = ".friday-bak"

#: Command output handed back to the model. A stack trace is a few hundred
#: characters; a runaway loop printing to stdout is unbounded, and the model
#: only needs the beginning and the end of it either way.
MAX_OUTPUT_CHARS = 8_000

#: Programs run_command may start when no settings object says otherwise.
DEFAULT_RUN_ALLOWLIST = ("python", "py", "pytest", "node", "npm", "code")

#: Seconds a single command may take by default.
DEFAULT_RUN_TIMEOUT = 45.0

#: Where shadow copies live, under the system temp directory.
SHADOW_DIRNAME = "friday-fix"


def _looks_binary(raw: bytes) -> bool:
    """True when these bytes are not text.

    A NUL byte never appears in text encoded as UTF-8 or any ASCII superset,
    and it appears almost immediately in real binaries, so the first block is
    enough to decide.
    """
    return b"\x00" in raw[:4096]


class CodeSkill(Skill):
    """Filesystem access for reading and patching the user's own code."""

    name = "CodeSkill"
    description = "Reads, lists, edits and runs files on the user's machine."
    version = "2.0.0"
    enabled = True

    def __init__(
        self,
        container: Any = None,
        shadow_root: Path | str | None = None,
        run_timeout: float | None = None,
    ) -> None:
        super().__init__(container)
        settings = getattr(container, "settings", None)

        self._shadow_root = Path(
            shadow_root or Path(tempfile.gettempdir()) / SHADOW_DIRNAME
        )
        self._run_timeout = float(
            run_timeout
            if run_timeout is not None
            else getattr(settings, "agent_run_timeout_seconds", DEFAULT_RUN_TIMEOUT)
        )

        raw_allowlist = getattr(settings, "agent_run_allowlist", None)
        self._allowlist = tuple(
            part.strip().lower()
            for part in str(raw_allowlist).split(",")
            if part.strip()
        ) if raw_allowlist else DEFAULT_RUN_ALLOWLIST

    async def execute(self, task: Task) -> str:
        intent = task.intent
        params = task.parameters or {}

        if intent == "read_file":
            return self._read(params.get("path"))
        if intent == "write_file":
            return self._write(params.get("path"), params.get("content"))
        if intent == "list_directory":
            return self._list(params.get("path"))
        if intent == "edit_file":
            return self._edit(
                params.get("path"), params.get("old_text"), params.get("new_text")
            )
        if intent == "copy_to_shadow":
            return self._shadow(params.get("path"))
        if intent == "run_command":
            return await self._run(params.get("command"), params.get("cwd"))

        raise ValueError(f"CodeSkill cannot handle intent: {intent}")

    # ── read ──────────────────────────────────────────────────────────────

    def _read(self, raw_path: str | None) -> str:
        if not raw_path:
            return "I need a file path to read."

        path = self._resolve(raw_path)

        if path.is_dir():
            return (
                f"{path} is a directory, not a file. Use list_directory to see "
                f"what is inside it."
            )
        if not path.exists():
            return f"File not found: {path}"

        try:
            raw = path.read_bytes()
        except OSError as exc:
            return f"Could not read {path}: {exc}"

        if _looks_binary(raw):
            return f"{path} is not a text file, so there is nothing to read."

        text = raw.decode("utf-8", errors="replace")

        truncated = len(text) > MAX_READ_CHARS
        if truncated:
            text = text[:MAX_READ_CHARS]

        # Line numbers, because the model has to be able to say *where* the
        # problem is before it can be asked to fix it.
        numbered = "\n".join(
            f"{number}\t{line}"
            for number, line in enumerate(text.splitlines(), start=1)
        )

        header = f"{path} ({len(raw)} bytes)"
        if truncated:
            header += f" -- truncated to the first {MAX_READ_CHARS} characters"

        return f"{header}\n{numbered}"

    # ── write ─────────────────────────────────────────────────────────────

    def _write(self, raw_path: str | None, content: str | None) -> str:
        if not raw_path:
            return "I need a file path to write to."

        # Not `if not content`: an empty string is the one value that can only
        # destroy, and it is also what a model sends when it has lost track of
        # what it meant to write.
        if content is None or content == "":
            return (
                "I need the new content to write. Refusing to write an empty "
                "file, which would erase what is there."
            )

        path = self._resolve(raw_path)

        if path.is_dir():
            return f"{path} is a directory, not a file."

        parent = path.parent
        if not parent.is_dir():
            return (
                f"The folder {parent} does not exist. I won't create folders "
                f"on my own -- check the path is right."
            )

        backup_note = ""
        if path.exists():
            backup = path.with_name(path.name + BACKUP_SUFFIX)
            try:
                backup.write_bytes(path.read_bytes())
                backup_note = f" The previous version is saved as {backup.name}."
            except OSError as exc:
                # Without a backup this edit is unrecoverable, so it does not
                # happen at all.
                return f"Could not back up {path.name} ({exc}), so I did not write it."

        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return f"Could not write {path}: {exc}"

        lines = len(content.splitlines())
        logger.info(f"Wrote {path} ({lines} lines)")
        return f"Wrote {lines} lines to {path.name}.{backup_note}"

    # ── list ──────────────────────────────────────────────────────────────

    def _list(self, raw_path: str | None) -> str:
        path = self._resolve(raw_path) if raw_path else Path.cwd()

        if not path.exists():
            return f"Folder not found: {path}"
        if not path.is_dir():
            return f"{path} is a file, not a folder."

        try:
            entries = sorted(
                path.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
        except OSError as exc:
            return f"Could not list {path}: {exc}"

        shown = entries[:MAX_LIST_ENTRIES]
        rendered = "\n".join(
            f"  {entry.name}/" if entry.is_dir() else f"  {entry.name}"
            for entry in shown
        )

        header = f"{path} ({len(entries)} entries)"
        if len(entries) > len(shown):
            header += f" -- showing the first {len(shown)}"

        return f"{header}\n{rendered}" if rendered else f"{path} is empty."

    # ── edit ──────────────────────────────────────────────────────────────

    def _edit(self, raw_path: str | None, old: str | None, new: str | None) -> str:
        """Replace one exact fragment, leaving the rest of the file alone.

        This is what makes a small model able to fix code at all. ``write_file``
        wants the complete new contents, and a 3B model asked to reproduce two
        hundred lines to change one of them will quietly drop or reword the
        rest -- so it does the safe thing instead and pastes a snippet into the
        conversation, which is exactly the behaviour the user complained about.
        Here it only has to produce the line it is changing.

        Both failure modes refuse rather than approximate. Not found means the
        model is working from a stale read; found twice means it has not said
        which one it means. Either way the answer is to tell it and let it read
        the file again -- silently patching the wrong line is the one outcome
        there is no recovering from.
        """
        if not raw_path:
            return "I need a file path to edit."
        if not old:
            return "I need the exact text to replace."
        if new is None:
            return "I need the replacement text."
        if old == new:
            return "The old and new text are the same, so there is no change to make."

        path = self._resolve(raw_path)

        if path.is_dir():
            return f"{path} is a directory, not a file."
        if not path.exists():
            return f"File not found: {path}"

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Could not read {path}: {exc}"

        occurrences = text.count(old)

        if occurrences == 0:
            return (
                f"That exact text was not found in {path.name}. Read the file "
                f"again and quote the line exactly as it appears."
            )
        if occurrences > 1:
            return (
                f"That text appears in {occurrences} places in {path.name}, so "
                f"I don't know which one you mean. Include a surrounding line "
                f"to make it unique."
            )

        line_number = text[: text.index(old)].count(chr(10)) + 1

        backup = path.with_name(path.name + BACKUP_SUFFIX)
        try:
            backup.write_bytes(path.read_bytes())
        except OSError as exc:
            return f"Could not back up {path.name} ({exc}), so I did not edit it."

        try:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
        except OSError as exc:
            return f"Could not write {path}: {exc}"

        logger.info(f"Edited {path} at line {line_number}")
        return (
            f"Edited {path.name} at line {line_number}. "
            f"The previous version is saved as {backup.name}."
        )

    # ── shadow copy ───────────────────────────────────────────────────────

    def _shadow(self, raw_path: str | None) -> str:
        """Copy a file somewhere it can be broken safely.

        The fix loop runs candidate edits and then executes them, which means
        running code that is wrong on purpose, repeatedly. Doing that to the
        file the user has open in their editor would flicker broken versions
        under their cursor and leave the wrong one behind if the turn were
        interrupted. So the loop works on a copy, and the real file is changed
        exactly once, at the end, with the user's consent.
        """
        if not raw_path:
            return "I need a file path to copy."

        path = self._resolve(raw_path)

        if not path.exists():
            return f"File not found: {path}"
        if path.is_dir():
            return f"{path} is a directory, not a file."

        try:
            self._shadow_root.mkdir(parents=True, exist_ok=True)
            shadow = self._shadow_root / path.name
            shutil.copyfile(path, shadow)
        except OSError as exc:
            return f"Could not make a working copy of {path.name}: {exc}"

        return (
            f"Working copy of {path.name} is at {shadow}. Edit and run that "
            f"one; the original is untouched until you apply the fix."
        )

    # ── run ───────────────────────────────────────────────────────────────

    async def _run(self, command: str | None, cwd: str | None = None) -> str:
        """Run an allowlisted program and return what it printed.

        The verify half of the fix loop: the model changes something, runs it,
        and reads the result. A non-zero exit is a *result*, not a failure --
        it is the whole reason the loop exists -- so it comes back as ordinary
        text for the model to read.

        Never a shell. The arguments are parsed once, here, and passed as a
        list, so an ``&& rm -rf`` riding along behind an allowed program name
        is data rather than a second command. The allowlist then decides
        whether the program may start at all: the point is to run the user's
        own code and read its output, not to hand a language model a terminal.
        """
        if not command or not str(command).strip():
            return "What command should I run?"

        try:
            parts = shlex.split(str(command), posix=False)
        except ValueError as exc:
            return f"I couldn't make sense of that command: {exc}"

        if not parts:
            return "What command should I run?"

        program = Path(parts[0].strip('"')).stem.lower()

        if program not in self._allowlist:
            return (
                f"I won't run '{program}'. I can only run: "
                f"{', '.join(self._allowlist)}."
            )

        parts = [part.strip('"') for part in parts]
        directory = self._resolve(cwd) if cwd else None

        try:
            process = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=str(directory) if directory and directory.is_dir() else None,
                # Console-window hygiene: see tests/test_no_console_windows.py.
                # Never OR'd with DETACHED_PROCESS, which makes Windows ignore
                # this flag and hands every child its own visible console.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            return f"'{parts[0]}' is not installed, or is not on the PATH."
        except OSError as exc:
            return f"Could not start that command: {exc}"

        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._run_timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return (
                f"That command timed out after {self._run_timeout:g} seconds, "
                f"so I stopped it."
            )

        output = (stdout or b"").decode("utf-8", errors="replace").strip()

        if len(output) > MAX_OUTPUT_CHARS:
            # Keep both ends: the first lines say what ran, the last lines
            # carry the exception, and the middle is almost never the point.
            half = MAX_OUTPUT_CHARS // 2
            output = f"{output[:half]}{chr(10)}... (output truncated) ...{chr(10)}{output[-half:]}"

        code = process.returncode
        verdict = "finished successfully" if code == 0 else f"exited with code {code}"

        if output:
            return f"Command {verdict}.{chr(10)}{output}"
        return f"Command {verdict}, with no output."

    # ── paths ─────────────────────────────────────────────────────────────

    def _resolve(self, raw_path: str) -> Path:
        """Expand ``~`` and environment variables, and anchor relative paths.

        A relative path from a spoken request means "in the project I am
        working on", which is the process working directory -- the autostart
        launcher chdir's there precisely so this holds at boot too.
        """
        expanded = os.path.expandvars(os.path.expanduser(str(raw_path).strip()))
        return Path(expanded).expanduser().absolute()
