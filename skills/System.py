"""
skills/System.py – System & File Management Skills
====================================================
Contains skills for interacting with the local system and filesystem:

  FolderSkill     – open, create, list, rename/move, delete folders
  BrightnessSkill – raise, lower, or set screen brightness (0–100)
  MicSkill        – mute, unmute, or toggle the default microphone

All skills are Windows-primary with graceful cross-platform stubs.

Team: Skills Team
Phase: 2 (Executor)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task


# ──────────────────────────────────────────────────────────────
# FolderSkill
# ──────────────────────────────────────────────────────────────

class FolderSkill(Skill):
    name = "FolderSkill"
    description = "Opens, creates, lists, or deletes a local folder."
    version = "2.1.0"
    enabled = True

    # Known top-level folders resolved relative to the user's home directory.
    # Anything not matched here is treated as a subfolder name under the
    # home directory, NOT the current working directory — this matters for
    # a background/voice assistant, where "cwd" is often wherever the
    # process happened to be launched from, not somewhere the user chose.
    KNOWN_FOLDERS = {
        "desktop": "Desktop",
        "downloads": "Downloads",
        "documents": "Documents",
        "docs": "Documents",
        "pictures": "Pictures",
        "music": "Music",
        "videos": "Videos",
    }

    #: Words a person says around a folder name that are not part of it.
    #: "open my downloads folder" names Downloads, not "my downloads folder".
    _FILLER_WORDS = frozenset(
        {"my", "the", "a", "an", "folder", "directory", "dir", "please", "up"}
    )

    #: Where a folder named by the user, but not a known shortcut, might be.
    #: One level deep only -- a full disk walk costs seconds and the answer is
    #: almost always here.
    _SEARCH_ROOTS = ("", "Desktop", "Documents")

    @classmethod
    def _strip_filler(cls, words: list[str]) -> list[str]:
        kept = [w for w in words if w.lower() not in cls._FILLER_WORDS]
        # Everything was filler ("the folder"): keep the original rather than
        # resolving to the home directory by accident.
        return kept or words

    @classmethod
    def _match_known(cls, word: str) -> str | None:
        """A known shortcut for this word, allowing a plural/singular slip.

        Speech-to-text produces "download" for Downloads often enough that
        requiring the exact plural is a real source of failure.
        """
        candidate = word.lower().strip()
        if candidate in cls.KNOWN_FOLDERS:
            return cls.KNOWN_FOLDERS[candidate]
        if f"{candidate}s" in cls.KNOWN_FOLDERS:
            return cls.KNOWN_FOLDERS[f"{candidate}s"]
        if candidate.endswith("s") and candidate[:-1] in cls.KNOWN_FOLDERS:
            return cls.KNOWN_FOLDERS[candidate[:-1]]
        return None

    @classmethod
    def _search_disk(cls, name: str) -> str | None:
        """Look for a folder called ``name`` near the user's home directory.

        Scored rather than first-match: an exact name beats a prefix beats a
        substring, and the shortest path wins a tie, so "friday agent" finds
        "friday-agent-main" without being derailed by a longer neighbour that
        also contains the words. The same approach ApplicationSkill uses for
        Start-menu shortcuts, for the same reason.
        """
        needle = name.lower().strip()
        if not needle:
            return None

        # "friday agent" should match "friday-agent-main": compare on letters
        # and digits only, so spoken spacing and punctuation stop mattering.
        squashed = "".join(ch for ch in needle if ch.isalnum())
        home = os.path.expanduser("~")
        best: tuple[int, str] | None = None

        for relative in cls._SEARCH_ROOTS:
            root = os.path.join(home, relative) if relative else home
            try:
                entries = os.scandir(root)
            except OSError:
                continue

            with entries:
                for entry in entries:
                    try:
                        if not entry.is_dir():
                            continue
                    except OSError:
                        continue

                    plain = entry.name.lower()
                    flat = "".join(ch for ch in plain if ch.isalnum())

                    if plain == needle:
                        score = 3
                    elif flat.startswith(squashed):
                        score = 2
                    elif squashed and squashed in flat:
                        score = 1
                    else:
                        continue

                    # An empty folder is almost never what somebody means
                    # by "open my project", so emptiness costs more than one
                    # grade of name match. That is deliberate: the live case
                    # was an empty leftover named exactly "friday agent"
                    # beating the real friday-agent-main on the Desktop. A
                    # populated exact match still wins over everything.
                    score = score + (2 if cls._has_contents(entry.path) else 0)

                    if best is None or score > best[0] or (
                        score == best[0] and len(entry.path) < len(best[1])
                    ):
                        best = (score, entry.path)

        return best[1] if best else None

    @staticmethod
    def _has_contents(path: str) -> bool:
        """True when the folder holds anything at all.

        Cheap: ``scandir`` stops at the first entry rather than listing the
        directory, so this costs the same for a project as for an empty stub.
        """
        try:
            with os.scandir(path) as entries:
                return next(entries, None) is not None
        except OSError:
            return False

    def _resolve_path(self, folder_name: str) -> str:
        """
        Resolve a spoken folder-name/location phrase to an absolute path.

        Supports:
          - "docs"                  -> home/Documents
          - "download"              -> home/Downloads (spoken plural slip)
          - "my downloads folder"   -> home/Downloads (filler words dropped)
          - "docs academic info"    -> home/Documents/academic info
            (nested subpath under a known shortcut)
          - "physics notes"         -> found on the Desktop by searching
          - an absolute path        -> used as-is
          - anything else           -> resolved under the user's home
                                        directory (NOT the working dir)

        Known shortcuts are tried before the disk search, so a stray folder
        called "Downloads" on the Desktop cannot shadow the real one.
        """
        raw = folder_name.strip()
        if not raw:
            raise ValueError("Empty folder name/location.")

        if os.path.isabs(raw):
            return raw

        words = self._strip_filler(raw.split())
        home = os.path.expanduser("~")

        known = self._match_known(words[0])
        if known is not None:
            base = os.path.join(home, known)
            remainder = " ".join(words[1:]).strip()
            return os.path.join(base, remainder) if remainder else base

        found = self._search_disk(" ".join(words))
        if found is not None:
            return found

        return os.path.join(home, raw)

    def _open_path(self, path: str) -> None:
        """Open a folder in the OS file browser, cross-platform."""
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)

    async def execute(self, task: Task) -> str:
        folder_name = task.parameters.get("folder_name")
        if not folder_name:
            raise ValueError("Missing 'folder_name' parameter.")

        action = task.parameters.get("action", "open")
        path = self._resolve_path(folder_name)

        if action == "open":
            if not os.path.isdir(path):
                raise RuntimeError(f'Folder "{folder_name}" does not exist.')
            self._open_path(path)
            return f'"{folder_name}" opened successfully.'

        elif action == "create":
            if os.path.exists(path):
                return f'"{folder_name}" already exists.'
            os.makedirs(path)
            return f'"{folder_name}" created successfully.'

        elif action == "list":
            if not os.path.isdir(path):
                raise RuntimeError(f'Folder "{folder_name}" does not exist.')

            entries = os.listdir(path)
            if not entries:
                return f'"{folder_name}" is empty.'

            preview = entries[:10]
            listing = ", ".join(preview)
            if len(entries) > 10:
                listing += f", and {len(entries) - 10} more"
            return f'"{folder_name}" contains: {listing}.'

        elif action == "modify":
            if not os.path.isdir(path):
                raise RuntimeError(f'Folder "{folder_name}" does not exist.')

            new_name = task.parameters.get("new_name")
            destination = task.parameters.get("destination")

            if not new_name and not destination:
                raise ValueError("'modify' requires 'new_name' and/or 'destination'.")

            if destination:
                dest_dir = self._resolve_path(destination)
                if not os.path.isdir(dest_dir):
                    raise RuntimeError(f'Destination "{destination}" does not exist.')
                target_name = new_name if new_name else os.path.basename(path)
                target_path = os.path.join(dest_dir, target_name)
            else:
                # Rename in place — same parent directory, new name.
                target_path = os.path.join(os.path.dirname(path), new_name)

            if os.path.exists(target_path):
                raise RuntimeError(f'"{os.path.basename(target_path)}" already exists at the destination.')

            shutil.move(path, target_path)

            if destination and new_name:
                return f'"{folder_name}" moved to "{destination}" and renamed to "{new_name}".'
            elif destination:
                return f'"{folder_name}" moved to "{destination}".'
            else:
                return f'"{folder_name}" renamed to "{new_name}".'

        elif action == "delete":
            if not os.path.isdir(path):
                raise RuntimeError(f'Folder "{folder_name}" does not exist.')

            if os.listdir(path):
                raise RuntimeError(
                    f'"{folder_name}" is not empty — I can only delete empty folders.'
                )

            os.rmdir(path)
            return f'"{folder_name}" deleted successfully.'

        raise ValueError(f"Unsupported folder action: '{action}'.")


# ──────────────────────────────────────────────────────────────
# BrightnessSkill
# ──────────────────────────────────────────────────────────────

class BrightnessSkill(Skill):
    """
    Adjusts screen brightness on Windows via WMI PowerShell commands.

    Supported actions:
      up   – increase brightness by STEP (default 10%)
      down – decrease brightness by STEP
      set  – set to an explicit integer level (0-100), passed as "level"
    """
    name = "BrightnessSkill"
    description = "Adjusts screen brightness: up, down, or set to a specific level."
    version = "1.0.0"
    enabled = True

    STEP = 10

    # ── helpers ──────────────────────────────────────────────

    def _get_brightness_windows(self) -> int:
        """Return current brightness level (0-100) on Windows."""
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness",
            ],
            capture_output=True,
            text=True,
            # Without this the PowerShell child opens its own console window,
            # because the PyQt entry point has no console for it to inherit.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = result.stdout.strip()
        if not raw.isdigit():
            raise RuntimeError("Could not read current brightness from WMI.")
        return int(raw)

    def _set_brightness_windows(self, level: int) -> None:
        """Set brightness level (0-100) on Windows via WMI."""
        level = max(0, min(100, level))
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                f".WmiSetBrightness(1, {level})",
            ],
            check=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    # ── macOS helpers ─────────────────────────────────────────

    def _get_brightness_macos(self) -> int:
        """Return current brightness (0-100) on macOS via osascript."""
        result = subprocess.run(
            ["osascript", "-e", "tell application \"System Events\" to get the brightness"],
            capture_output=True,
            text=True,
        )
        try:
            return int(float(result.stdout.strip()) * 100)
        except ValueError:
            raise RuntimeError("Could not read brightness on macOS.")

    def _set_brightness_macos(self, level: int) -> None:
        level = max(0, min(100, level))
        # brightness is a float 0.0-1.0 on macOS
        subprocess.run(
            ["osascript", "-e",
             f"tell application \"System Events\" to set the brightness to {level / 100:.2f}"],
            check=True,
        )

    # ── execute ───────────────────────────────────────────────

    async def execute(self, task: Task) -> str:
        action = task.parameters.get("action", "").lower()
        level = task.parameters.get("level")

        if not action:
            raise ValueError("Missing 'action' parameter (up / down / set).")

        system = platform.system()

        if system == "Windows":
            current = self._get_brightness_windows()

            if action == "up":
                new_level = min(100, current + self.STEP)
                self._set_brightness_windows(new_level)
                return f"Brightness increased to {new_level}%."

            elif action == "down":
                new_level = max(0, current - self.STEP)
                self._set_brightness_windows(new_level)
                return f"Brightness decreased to {new_level}%."

            elif action == "set":
                if level is None:
                    raise ValueError("Missing 'level' for brightness set.")
                self._set_brightness_windows(int(level))
                return f"Brightness set to {level}%."

        elif system == "Darwin":
            current = self._get_brightness_macos()

            if action == "up":
                new_level = min(100, current + self.STEP)
                self._set_brightness_macos(new_level)
                return f"Brightness increased to {new_level}%."

            elif action == "down":
                new_level = max(0, current - self.STEP)
                self._set_brightness_macos(new_level)
                return f"Brightness decreased to {new_level}%."

            elif action == "set":
                if level is None:
                    raise ValueError("Missing 'level' for brightness set.")
                self._set_brightness_macos(int(level))
                return f"Brightness set to {level}%."

        else:
            raise RuntimeError(f"Brightness control is not supported on {system}.")

        raise ValueError(f"Unsupported brightness action: '{action}'.")


# ──────────────────────────────────────────────────────────────
# MicSkill
# ──────────────────────────────────────────────────────────────

class MicSkill(Skill):
    """
    Mutes, unmutes, or toggles the default microphone (capture device).

    Uses the Windows Core Audio API via pycaw on Windows,
    and osascript on macOS.

    Supported actions: mute | unmute | toggle
    """
    name = "MicSkill"
    description = "Mutes, unmutes, or toggles the default microphone."
    version = "1.0.0"
    enabled = True

    # ── Windows helpers ───────────────────────────────────────

    def _get_mic_interface_windows(self):
        """Return the IAudioEndpointVolume interface for the default capture device."""
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL, CoCreateInstance, GUID
        from pycaw.pycaw import IMMDeviceEnumerator, IAudioEndpointVolume, EDataFlow, ERole

        CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        device_enumerator = CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            IMMDeviceEnumerator,
            CLSCTX_ALL,
        )
        # eCapture = 1 for microphone (input device)
        endpoint = device_enumerator.GetDefaultAudioEndpoint(
            EDataFlow.eCapture.value, ERole.eMultimedia.value
        )
        interface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    def _execute_windows(self, action: str) -> str:
        mic = self._get_mic_interface_windows()

        if action == "mute":
            mic.SetMute(1, None)
            return "Microphone muted."
        elif action == "unmute":
            mic.SetMute(0, None)
            return "Microphone unmuted."
        elif action == "toggle":
            current = mic.GetMute()
            mic.SetMute(0 if current else 1, None)
            return "Microphone unmuted." if current else "Microphone muted."

        raise ValueError(f"Unsupported mic action: '{action}'.")

    # ── macOS helpers ─────────────────────────────────────────

    def _execute_macos(self, action: str) -> str:
        """Toggle mic mute on macOS via osascript input volume."""
        if action == "mute":
            subprocess.run(
                ["osascript", "-e", "set volume input volume 0"],
                check=True,
            )
            return "Microphone muted."
        elif action == "unmute":
            subprocess.run(
                ["osascript", "-e", "set volume input volume 100"],
                check=True,
            )
            return "Microphone unmuted."
        elif action == "toggle":
            result = subprocess.run(
                ["osascript", "-e", "input volume of (get volume settings)"],
                capture_output=True,
                text=True,
            )
            current = int(result.stdout.strip() or "100")
            if current == 0:
                subprocess.run(["osascript", "-e", "set volume input volume 100"], check=True)
                return "Microphone unmuted."
            else:
                subprocess.run(["osascript", "-e", "set volume input volume 0"], check=True)
                return "Microphone muted."

        raise ValueError(f"Unsupported mic action: '{action}'.")

    # ── execute ───────────────────────────────────────────────

    async def execute(self, task: Task) -> str:
        action = task.parameters.get("action", "").lower()
        if not action:
            raise ValueError("Missing 'action' parameter (mute / unmute / toggle).")

        system = platform.system()

        if system == "Windows":
            return self._execute_windows(action)
        elif system == "Darwin":
            return self._execute_macos(action)
        else:
            raise RuntimeError(f"Mic control is not supported on {system}.")



