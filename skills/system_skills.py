"""
skills/system_skills.py – Deterministic Desktop Skills
======================================================
Defines basic skills for Phase 2 executor.

Team: Skills Team
Phase: 2 (Executor)
"""

from __future__ import annotations

import platform
import datetime
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, NamedTuple
from skills.base import Skill
import urllib.parse
import webbrowser
try:
    import sympy as sp
except ImportError:
    sp = None

if TYPE_CHECKING:
    # Imported for annotations only. At runtime this would be a cycle:
    # skills.system_skills -> intelligence.task -> intelligence/__init__
    # -> intelligence.router -> skills.system_skills. `from __future__ import
    # annotations` above makes the type hints strings, so the cycle never
    # needs to exist.
    from core.container import ServiceContainer
    from intelligence.task import Task


# ── The known-website registry ────────────────────────────────────────────
#
# Users name websites the same way they name programs: "open youtube",
# "open gmail". Without a list of the sites that are sites, two things went
# wrong at once — the Start menu happily launched YouTube Music for "open
# youtube in chrome", and BrowserSkill turned a bare "youtube" into the
# unresolvable URL "https://youtube".
#
# The registry is defined above ApplicationSkill because that class consults
# it before it is willing to launch anything.


class Site(NamedTuple):
    """One entry in :data:`KNOWN_WEBSITES`.

    ``search`` is the site's own search URL with ``{q}`` standing in for the
    URL-encoded query. It is ``None`` for sites with no useful public search;
    those fall back to a Google ``site:`` query, which is still one tab
    landing on results rather than a blank home page.
    """

    label: str          # Spoken back to the user, so capitalised as the brand is.
    url: str            # Home page.
    search: str | None  # In-site search, "{q}" = URL-encoded query.


KNOWN_WEBSITES: dict[str, Site] = {
    "youtube": Site(
        "YouTube",
        "https://www.youtube.com",
        "https://www.youtube.com/results?search_query={q}",
    ),
    "google": Site(
        "Google",
        "https://www.google.com",
        "https://www.google.com/search?q={q}",
    ),
    "gmail": Site(
        "Gmail",
        "https://mail.google.com",
        # Gmail's own search, which searches the user's mail rather than the web.
        "https://mail.google.com/mail/u/0/#search/{q}",
    ),
    "maps": Site(
        "Google Maps",
        "https://www.google.com/maps",
        "https://www.google.com/maps/search/{q}",
    ),
    "drive": Site(
        "Google Drive",
        "https://drive.google.com",
        "https://drive.google.com/drive/search?q={q}",
    ),
    "github": Site(
        "GitHub",
        "https://github.com",
        "https://github.com/search?q={q}",
    ),
    "reddit": Site(
        "Reddit",
        "https://www.reddit.com",
        "https://www.reddit.com/search/?q={q}",
    ),
    "x": Site(
        "X",
        "https://x.com",
        "https://x.com/search?q={q}",
    ),
    "instagram": Site(
        "Instagram",
        "https://www.instagram.com",
        "https://www.instagram.com/explore/search/keyword/?q={q}",
    ),
    "facebook": Site(
        "Facebook",
        "https://www.facebook.com",
        "https://www.facebook.com/search/top?q={q}",
    ),
    "linkedin": Site(
        "LinkedIn",
        "https://www.linkedin.com",
        "https://www.linkedin.com/search/results/all/?keywords={q}",
    ),
    "wikipedia": Site(
        "Wikipedia",
        "https://en.wikipedia.org",
        "https://en.wikipedia.org/w/index.php?search={q}",
    ),
    "amazon": Site(
        "Amazon",
        "https://www.amazon.com",
        "https://www.amazon.com/s?k={q}",
    ),
    "stackoverflow": Site(
        "Stack Overflow",
        "https://stackoverflow.com",
        "https://stackoverflow.com/search?q={q}",
    ),
    "netflix": Site(
        "Netflix",
        "https://www.netflix.com",
        "https://www.netflix.com/search?q={q}",
    ),
    "chatgpt": Site(
        "ChatGPT",
        "https://chatgpt.com",
        # No public search endpoint; a site: query at least lands on results.
        None,
    ),
    "claude": Site(
        "Claude",
        "https://claude.ai",
        None,
    ),
    "whatsapp": Site(
        "WhatsApp Web",
        "https://web.whatsapp.com",
        None,
    ),
}

#: Spoken forms that mean one of the registry entries above. Kept separate
#: from KNOWN_WEBSITES so each site is described exactly once.
WEBSITE_ALIASES = {
    "yt": "youtube",
    "youtube music": "youtube",   # Said out loud this means the site, not the app.
    "google maps": "maps",
    "google map": "maps",
    "google drive": "drive",
    "gdrive": "drive",
    "google mail": "gmail",
    "twitter": "x",
    "insta": "instagram",
    "ig": "instagram",
    "fb": "facebook",
    "wiki": "wikipedia",
    "stack overflow": "stackoverflow",
    "chat gpt": "chatgpt",
    "claude ai": "claude",
    "whatsapp web": "whatsapp",
    "web whatsapp": "whatsapp",
    "amazon.in": "amazon",
    "prime": "amazon",
}


def normalize_website_name(name: str) -> str:
    """Reduce a spoken or typed site name to a registry key candidate.

    Strips the scheme, "www.", trailing slashes and sentence punctuation, so
    "YouTube", "youtube.com/" and "https://www.youtube.com" all arrive at the
    same place.
    """
    text = re.sub(r"\s+", " ", str(name or "").strip().lower())
    text = re.sub(r"^[a-z]+://", "", text)
    text = re.sub(r"^www\.", "", text)
    return text.strip(" /.,!?")


def resolve_website(name: str) -> Site | None:
    """Return the registry entry a spoken site name refers to, or None.

    A domain resolves too ("youtube.com" -> the YouTube entry), because the
    point of resolving is to reach the in-site search template; without that,
    "open youtube.com and look up MKBHD" would open a blank home page and
    lose the query.
    """
    text = normalize_website_name(name)
    if not text:
        return None

    for candidate in (text, WEBSITE_ALIASES.get(text, "")):
        if candidate in KNOWN_WEBSITES:
            return KNOWN_WEBSITES[candidate]

    if "." in text:
        # "youtube.com" -> "youtube". Deeper hosts ("en.wikipedia.org") miss
        # here and are opened verbatim, which is the right answer for them.
        head = text.split(".", 1)[0]
        if head in KNOWN_WEBSITES:
            return KNOWN_WEBSITES[head]
        alias = WEBSITE_ALIASES.get(head)
        if alias in KNOWN_WEBSITES:
            return KNOWN_WEBSITES[alias]

    return None


def _google_site_search(url: str, encoded_query: str) -> str:
    """Search one site through Google, for sites with no search of their own."""
    host = urllib.parse.urlsplit(url).netloc
    return f"https://www.google.com/search?q=site%3A{host}+{encoded_query}"


def build_website_url(website: str, query: str | None = None) -> str:
    """Turn a site name (and an optional in-site search) into one real URL.

    The old behaviour was ``"https://" + whatever was said``, which produced
    "https://youtube" — a URL no browser can resolve. Every branch here has to
    end at something a browser will actually load.
    """
    encoded = urllib.parse.quote_plus(query.strip()) if query and query.strip() else ""

    site = resolve_website(website)
    if site is not None:
        if not encoded:
            return site.url
        if site.search:
            return site.search.format(q=encoded)
        return _google_site_search(site.url, encoded)

    raw = str(website or "").strip()
    lowered = raw.lower()

    if lowered.startswith(("http://", "https://")):
        # A full URL to an unregistered site. There is no way to know its
        # search parameter, so a query becomes a Google site: search on it.
        return _google_site_search(raw, encoded) if encoded else raw

    if "." in raw and " " not in raw:
        # An unregistered domain: "hackernews.com", "myuni.edu.in".
        url = f"https://{raw}"
        return _google_site_search(url, encoded) if encoded else url

    if re.fullmatch(r"[a-z0-9][a-z0-9\-]*", lowered):
        # A single unregistered word. Browsers guess ".com" for exactly this
        # case and are usually right ("open pinterest"), which beats sending
        # the user to a results page they still have to click through.
        url = f"https://www.{lowered}.com"
        return _google_site_search(url, encoded) if encoded else url

    # Several words and no domain: not a site name at all, so search for it.
    terms = f"{raw} {query}".strip() if query else raw
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(terms)}"


def open_website_in_chrome(website: str, query: str | None = None) -> str:
    """Open a site (optionally on its own search results) and describe it.

    Shared by BrowserSkill and by ApplicationSkill's website-first guard, so
    "open youtube" behaves identically however it was classified.

    The reply names the site rather than the URL: this is read aloud, and a
    search URL read out character by character is unusable.
    """
    url = build_website_url(website, query)
    site = resolve_website(website)
    label = site.label if site else normalize_website_name(website) or url

    used_chrome, message = open_in_chrome(url)

    if not used_chrome:
        # Chrome was missing or the browser failed; open_in_chrome already
        # explains which happened, and that is the more useful thing to say.
        return message

    if query and query.strip():
        return f"Opened {label} and searched for {query.strip()} in Chrome."

    return f"Opened {label} in Chrome."


class ApplicationSkill(Skill):
    name = "ApplicationSkill"
    description = "Opens or closes desktop applications."
    version = "1.0.0"
    enabled = True

    # Application alias registry.
    # Maps spoken/typed names to a canonical, platform-agnostic application ID.
    # Add new aliases here as a single dictionary entry.
    APP_ALIASES = {
        # Browsers
        "chrome": "chrome",
        "google chrome": "chrome",
        "edge": "edge",
        "microsoft edge": "edge",
        "firefox": "firefox",
        "brave": "brave",

        # Editors / IDEs
        "code": "vscode",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "vscode": "vscode",
        "pycharm": "pycharm",
        "android studio": "android_studio",

        # Windows Utilities
        "terminal": "terminal",
        "command prompt": "terminal",
        "cmd": "terminal",
        "cli": "powershell",
        "powershell": "powershell",
        "pwsh": "powershell",
        "file explorer": "explorer",
        "explorer": "explorer",
        "settings": "settings",
        "camera": "camera",
        "calculator": "calculator",
        "calc": "calculator",
        "paint": "paint",
        "notepad": "notepad",
        "task manager": "task_manager",

        # AI assistants
        "claude": "claude",
        "claude desktop": "claude",
        "chatgpt": "chatgpt",

        # Communication
        "discord": "discord",
        "spotify": "spotify",
        "telegram": "telegram",
        "whatsapp": "whatsapp",
        "zoom": "zoom",

        # Office
        "word": "word",
        "excel": "excel",
        "powerpoint": "powerpoint",
    }

    # Canonical ID -> macOS application name.
    MACOS_APPS = {
        "chrome": "Google Chrome",
        "vscode": "Visual Studio Code",
        "terminal": "Terminal",
        "finder": "Finder",
        "safari": "Safari",
        "notes": "Notes",
        "calendar": "Calendar",
        "mail": "Mail",
        "messages": "Messages",
        "facetime": "FaceTime",
        "photos": "Photos",
        "music": "Music",
        "podcasts": "Podcasts",
        "spotify": "Spotify",
        "discord": "Discord",
        "slack": "Slack",
        "zoom": "zoom.us",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "edge": "Microsoft Edge",
        "firefox": "Firefox",
        "brave": "Brave Browser",
        "figma": "Figma",
        "postman": "Postman",
        "docker": "Docker Desktop",
        "android studio": "Android Studio",
        "xcode": "Xcode",
        "pycharm": "PyCharm",
        "intellij": "IntelliJ IDEA",
    }

    # Canonical ID -> Windows executable / URI.
    WINDOWS_APPS = {

        "chrome": {
            "open": "chrome.exe",
            "close": "chrome.exe",
            "type": "exe",
        },

        "edge": {
            "open": "msedge.exe",
            "close": "msedge.exe",
            "type": "exe",
        },

        "firefox": {
            "open": "firefox.exe",
            "close": "firefox.exe",
            "type": "exe",
        },

        "brave": {
            "open": "brave.exe",
            "close": "brave.exe",
            "type": "exe",
        },

        "vscode": {
            "open": "Code.exe",
            "close": "Code.exe",
            "type": "exe",
        },

        "pycharm": {
           "open": "pycharm64.exe",
            "close": "pycharm64.exe",
            "type": "exe",
        },

        "android_studio": {
            "open": "studio64.exe",
            "close": "studio64.exe",
            "type": "exe",
        },

        "terminal": {
            "open": "powershell.exe",
            "close": "powershell.exe",
            "type": "exe",
        },

        "powershell": {
            "open": "powershell.exe",
            "close": "powershell.exe",
            "type": "exe",
        },

        "explorer": {
            "open": "explorer.exe",
            "close": "explorer.exe",
            "type": "exe",
        },

        "notepad": {
            "open": "notepad.exe",
            "close": "notepad.exe",
            "type": "exe",
        },

        "paint": {
            "open": "mspaint.exe",
            "close": "mspaint.exe",
            "type": "exe",
        },

        "calculator": {
            "open": "calc.exe",
            "close": "CalculatorApp.exe",
            "type": "exe",
        },

        "settings": {
            "open": "ms-settings:",
            "close": "SystemSettings.exe",
            "type": "uri",
        },

        "camera": {
            "open": "microsoft.windows.camera:",
            "close": "WindowsCamera.exe",
            "type": "uri",
        },

        "task_manager": {
            "open": "taskmgr.exe",
            "close": "Taskmgr.exe",
            "type": "exe",
        },

        "spotify": {
            "open": "Spotify.exe",
            "close": "Spotify.exe",
            "type": "exe",
        },

        "discord": {
            "open": "Discord.exe",
            "close": "Discord.exe",
            "type": "exe",
        },

        "telegram": {
            "open": "Telegram.exe",
            "close": "Telegram.exe",
            "type": "exe",
        },

        "whatsapp": {
            "open": "WhatsApp.exe",
            "close": "WhatsApp.exe",
            "type": "exe",
        },

        "zoom": {
            "open": "Zoom.exe",
            "close": "Zoom.exe",
            "type": "exe",
        },
    }

    def _normalize_name(self, name: str) -> str:
        """Normalize the spoken application name by lowering, trimming, and collapsing whitespace."""
        return re.sub(r'\s+', ' ', name.lower().strip())

    def _resolve_alias(self, normalized_name: str, original_name: str) -> str:
        """Resolve the normalized name to a canonical application ID.

        Falls back to the normalized original name if no alias is registered.
        """
        return self.APP_ALIASES.get(normalized_name, normalized_name)

    # Where Windows keeps the shortcuts the Start menu shows.
    START_MENU_DIRS = (
        os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs",
        ),
        os.path.join(
            os.environ.get("PROGRAMDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs",
        ),
    )

    #: Shortest name allowed to match as a substring. Without a floor, "x"
    #: scores 0.92 against "Excel" and every stray syllable launches something.
    MIN_SHORTCUT_SUBSTRING = 3

    #: A fuzzy ratio below this is not a match. At 0.7 the Start menu produced
    #: "obs studio" -> Roblox Studio and "recovery" -> RecoveryDrive, which
    #: formats a USB drive.
    MIN_SHORTCUT_RATIO = 0.86

    #: How much of a shortcut's name a containment match has to account for.
    #: Containment used to score ~0.95 no matter how much of the name was left
    #: over, so "youtube" launched YouTube Music (coverage 7/13 = 0.54) and
    #: "recovery" launched Recovery Drive (8/14 = 0.57). The leftover words in
    #: both cases are what makes it a *different* product, so a match that
    #: leaves that much behind is not a match. 0.75 still admits the suffixes
    #: that are only decoration, e.g. "notepad" -> "Notepad++" (7/9 = 0.78).
    MIN_SHORTCUT_COVERAGE = 0.75

    #: Trimmed off a shortcut name before it is compared. A parenthetical is a
    #: variant marker rather than part of the product's name, which is what
    #: keeps "claude" matching "Claude (uninstall)" as it always has; Windows
    #: appends " - Shortcut" to copied .lnk files for the same reason. Words
    #: like "help" or "readme" are deliberately NOT trimmed — those are
    #: genuinely different entries, and launching one instead of the app would
    #: be the same class of bug this coverage rule exists to stop.
    _SHORTCUT_NOISE = re.compile(r"\s*\([^)]*\)|\s*-\s*shortcut$")

    @classmethod
    def _shortcut_stem_core(cls, stem: str) -> str:
        """Strip the decoration off a shortcut name before comparing it."""
        return cls._SHORTCUT_NOISE.sub("", stem).strip()

    @classmethod
    def _containment_score(cls, wanted: str, stem: str) -> float | None:
        """Score ``wanted`` appearing inside ``stem``, or None when it is noise.

        Two conditions, both learned from a real misfire:

        * The occurrence must sit on a word boundary, so "recovery" does not
          match "recoverydrive".
        * It must cover MIN_SHORTCUT_COVERAGE of what is left of the name once
          decoration is stripped, so "youtube" does not match "youtube music".
        """
        if len(wanted) < cls.MIN_SHORTCUT_SUBSTRING:
            return None

        core = cls._shortcut_stem_core(stem)
        if not core:
            return None

        # (?<!\w)/(?!\w) rather than \b: `wanted` may itself start or end with
        # punctuation ("notepad++"), where \b would assert the wrong thing.
        if not re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", core):
            return None

        coverage = len(wanted) / len(core)
        if coverage < cls.MIN_SHORTCUT_COVERAGE:
            return None

        # Prefer the shortest containing name: "Claude" should win over
        # "Claude (uninstall)".
        return 0.90 + 0.09 * coverage

    def _find_start_menu_shortcut(self, *names: str) -> str | None:
        """Locate a Start menu .lnk matching a spoken application name.

        WINDOWS_APPS only knows the apps somebody thought to add. Everything
        the user actually installed is already listed in the Start menu, so
        falling back to it means a new app is launchable the day it is
        installed rather than the day an alias is written for it.

        Several candidate names may be given — typically the canonical alias
        and the raw spoken words. "open claude desktop" resolves to the alias
        ``claude``, which matches the shortcut; the spoken form does not.
        """
        import difflib

        candidates = [n.strip().lower() for n in names if n and n.strip()]
        if not candidates:
            return None

        entries: list[tuple[str, str]] = []  # (stem, full path)
        for directory in self.START_MENU_DIRS:
            if not directory or not os.path.isdir(directory):
                continue
            for current, _dirs, files in os.walk(directory):
                for filename in files:
                    if filename.lower().endswith((".lnk", ".url")):
                        entries.append(
                            (
                                os.path.splitext(filename)[0].lower(),
                                os.path.join(current, filename),
                            )
                        )

        for wanted in candidates:
            best: tuple[float, str] | None = None

            for stem, path in entries:
                if stem == wanted:
                    return path

                score = self._containment_score(wanted, stem)

                # A rejected containment still gets the fuzzy pass rather than
                # being dropped outright, so tightening the rule above only
                # ever costs a match the ratio would refuse anyway.
                if score is None:
                    ratio = difflib.SequenceMatcher(None, wanted, stem).ratio()
                    if ratio < self.MIN_SHORTCUT_RATIO:
                        continue
                    # Kept strictly below the substring band so a near-miss can
                    # never outrank a real containment.
                    score = 0.80 + 0.09 * ratio

                # Ties broken by the shorter name rather than by directory walk
                # order, which differs between machines.
                if best is None or score > best[0] or (
                    score == best[0] and len(path) < len(best[1])
                ):
                    best = (score, path)

            if best is not None:
                return best[1]

        return None

    def _execute_windows(self, intent, canonical_id, display_name):

        app = self.WINDOWS_APPS.get(canonical_id)

        if app is None:
            if intent == "open_application":
                # Both spellings: "open claude desktop" resolves to the alias
                # `claude`, which is what the shortcut is actually called.
                shortcut = self._find_start_menu_shortcut(canonical_id, display_name)
                if shortcut is not None:
                    try:
                        os.startfile(shortcut)
                        return f"{display_name} opened successfully."
                    except Exception as e:
                        raise RuntimeError(
                            f'Failed to open "{display_name}". ({e})'
                        ) from e
                # Nothing in the alias table and nothing in the Start menu:
                # the app is not installed, which is worth saying plainly
                # rather than calling the name "unknown".
                raise RuntimeError(
                    f"I couldn't find {display_name} installed on this PC."
                )
            raise RuntimeError(f'Unknown application "{display_name}".')

        if intent == "open_application":

            try:
                # os.startfile resolves executables via the Windows
                # "App Paths" registry, the same mechanism Win+R uses.
                # This works regardless of where the app is actually
                # installed on a given machine, unlike a bare Popen()
                # call which only checks the system PATH.
                os.startfile(app["open"])

                return f"{display_name} opened successfully."

            except Exception as e:
                raise RuntimeError(f'Failed to open "{display_name}". ({e})') from e

        elif intent == "close_application":

            try:

                subprocess.run(
                    ["taskkill", "/IM", app["close"], "/F"],
                    check=True,
                    capture_output=True,
                    text=True,
                    # taskkill is a console program; without this it opens a
                    # visible console window when ULTRON runs under the GUI.
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

                return f"{display_name} closed successfully."

            except subprocess.CalledProcessError:
                raise RuntimeError(f'"{display_name}" is not running.')

            except Exception as e:
                raise RuntimeError(f'Failed to close "{display_name}". ({e})') from e

        raise RuntimeError(f"Unsupported intent: {intent}")

    def _execute_macos(self, intent: str, canonical_id: str, display_name: str) -> str:
        """Isolate macOS-specific logic for opening/closing applications."""
        # Resolve the canonical ID to a macOS application name, falling back
        # to the canonical ID itself if there is no explicit mapping.
        resolved_name = self.MACOS_APPS.get(canonical_id, canonical_id)

        if intent == "open_application":
            try:
                subprocess.run(
                    ["open", "-a", resolved_name],
                    check=True,
                    capture_output=True,
                    text=True
                )
                return f"{display_name} opened successfully."
            except subprocess.CalledProcessError:
                raise RuntimeError(f'I couldn\'t find an application named "{display_name}".')
            except Exception as e:
                raise RuntimeError(f'Failed to open application "{display_name}".') from e

        elif intent == "close_application":
            try:
                subprocess.run(
                    ["pkill", "-i", resolved_name],
                    check=True,
                    capture_output=True,
                    text=True
                )
                return f"{display_name} closed successfully."
            except subprocess.CalledProcessError:
                raise RuntimeError(f'Application "{display_name}" is not currently running.')
            except Exception as e:
                raise RuntimeError(f'Failed to close application "{display_name}".') from e

        raise RuntimeError(f"Unsupported intent: {intent}")

    #: Names that are a website first and a program second. The detector still
    #: mislabels "open youtube" as open_application often enough — a 3B local
    #: model is literal about the word "open" — that the skill has to hold the
    #: line itself: the Start menu will otherwise offer up whatever it has that
    #: is spelled similarly, which is how "open youtube in chrome" launched the
    #: YouTube Music desktop app.
    #:
    #: Derived rather than listed so the two tables cannot drift apart: every
    #: registered site is website-first EXCEPT the ones that are also a
    #: registered desktop app. Claude, ChatGPT and WhatsApp ship real Windows
    #: apps and are in APP_ALIASES, so for those "open" still means the app.
    WEBSITE_FIRST_NAMES = (
        frozenset(KNOWN_WEBSITES) | frozenset(WEBSITE_ALIASES)
    ) - frozenset(APP_ALIASES)

    LINUX_APPS = {
        "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
        "firefox": ["firefox"],
        "brave": ["brave-browser", "brave"],
        "edge": ["microsoft-edge"],
        "vscode": ["code"],
        "terminal": ["gnome-terminal", "konsole", "xfce4-terminal", "alacritty", "kitty", "xterm"],
        "spotify": ["spotify"],
        "discord": ["discord"],
        "slack": ["slack"],
        "telegram": ["telegram-desktop", "telegram"],
        "calculator": ["gnome-calculator", "kcalc", "galculator"],
        "files": ["nautilus", "dolphin", "thunar", "nemo"],
        "text_editor": ["gedit", "kate", "mousepad", "gnome-text-editor"],
    }

    def _execute_linux(self, intent: str, canonical_id: str, display_name: str) -> str:
        candidates = self.LINUX_APPS.get(canonical_id, [canonical_id])
        if intent == "open_application":
            binary = None
            for cand in candidates:
                found = shutil.which(cand)
                if found:
                    binary = found
                    break
            if not binary:
                if shutil.which("gtk-launch"):
                    try:
                        subprocess.Popen(["gtk-launch", canonical_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return f"{display_name} opened successfully."
                    except Exception:
                        pass
                raise RuntimeError(f"I couldn't find {display_name} installed on this Linux system.")

            try:
                subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return f"{display_name} opened successfully."
            except Exception as e:
                raise RuntimeError(f"Failed to open {display_name}: {e}")
        elif intent == "close_application":
            target_proc = candidates[0] if candidates else canonical_id
            try:
                subprocess.run(["pkill", "-f", target_proc], check=True, capture_output=True)
                return f"{display_name} closed successfully."
            except subprocess.CalledProcessError:
                raise RuntimeError(f"Application '{display_name}' is not currently running.")
        raise RuntimeError(f"Unsupported intent: {intent}")

    async def execute(self, task: Task) -> str:
        app_name = task.parameters.get("application")
        if not app_name:
            return "❌ Missing 'application' parameter."

        normalized = self._normalize_name(app_name)
        canonical_id = self._resolve_alias(normalized, app_name)
        display_name = app_name.strip()

        # Handled here rather than by rewriting the task, so the browser path
        # is reached whichever way the request was classified and the user gets
        # the tab they asked for instead of "I couldn't find youtube installed".
        if task.intent == "open_application" and normalized in self.WEBSITE_FIRST_NAMES:
            return open_website_in_chrome(
                normalized,
                task.parameters.get("query") or task.parameters.get("search_query"),
            )

        # Dispatch to platform-specific execution
        system = platform.system()

        if system == "Windows":
            return self._execute_windows(task.intent, canonical_id, display_name)

        elif system == "Darwin":
            return self._execute_macos(task.intent, canonical_id, display_name)

        elif system == "Linux":
            return self._execute_linux(task.intent, canonical_id, display_name)

        else:
            return f"❌ Unsupported operating system: {system}"

# ── Chrome launching ──────────────────────────────────────────────────────
#
# webbrowser.open() honours whatever the OS calls the default browser, which
# on a fresh Windows install is Edge. The user asked for their Chrome tab, so
# Chrome is located explicitly and only falls back to the default browser when
# Chrome genuinely is not installed.

#: Registry values Windows itself consults to resolve "chrome.exe". This is the
#: same App Paths mechanism Win+R uses, so it finds Chrome wherever it was
#: installed rather than assuming Program Files.
CHROME_REGISTRY_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
    ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
)

#: Checked after the registry, for installs whose App Paths entry is missing.
CHROME_FALLBACK_PATHS = (
    r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
    r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
)


def _chrome_from_registry() -> str | None:
    """Read chrome.exe's path out of the Windows App Paths registry key."""
    try:
        import winreg
    except ImportError:
        return None

    for root_name, subkey in CHROME_REGISTRY_KEYS:
        root = getattr(winreg, root_name)
        try:
            with winreg.OpenKey(root, subkey) as key:
                path, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue

        path = os.path.expandvars(str(path).strip('"'))
        if path and os.path.isfile(path):
            return path

    return None


def find_chrome() -> str | None:
    """
    Locate chrome.exe on this machine, or return None when Chrome is absent.

    Tries the registry first, then the three standard install directories,
    then PATH.
    """
    if platform.system() != "Windows":
        # macOS/Linux: let `which` decide, and fall back to the macOS bundle.
        for name in ("google-chrome", "google-chrome-stable", "chrome", "chromium"):
            found = shutil.which(name)
            if found:
                return found
        mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        return mac_chrome if os.path.isfile(mac_chrome) else None

    from_registry = _chrome_from_registry()
    if from_registry:
        return from_registry

    for template in CHROME_FALLBACK_PATHS:
        candidate = os.path.expandvars(template)
        # expandvars leaves an unset %VAR% verbatim, which never resolves.
        if "%" not in candidate and os.path.isfile(candidate):
            return candidate

    return shutil.which("chrome.exe") or shutil.which("chrome")


def open_in_chrome(url: str) -> tuple[bool, str]:
    """
    Open ``url`` in a new Chrome tab.

    Returns ``(used_chrome, message)``. When Chrome cannot be found the URL
    still opens in the default browser — silently failing would be worse than
    using the wrong browser — and the message says which browser was used.
    """
    chrome = find_chrome()

    if chrome:
        try:
            subprocess.Popen([chrome, "--new-tab", url])
            return True, "Opened in Chrome."
        except Exception:
            pass  # Fall through to the default browser.

    if webbrowser.open(url):
        return False, (
            "I could not find Chrome on this computer, so I opened it in your "
            "default browser instead."
        )

    return False, "❌ Failed to open the browser."


class BrowserSkill(Skill):
    name = "BrowserSkill"
    description = "Opens websites in a new Google Chrome tab."
    version = "2.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        website = task.parameters.get("website")
        # "search_query" is what the rule-based entity extractor calls it; the
        # LLM path emits "query". Both mean "and look this up on that site".
        query = task.parameters.get("query") or task.parameters.get("search_query")

        if not website:
            if not query:
                raise ValueError(
                    "Missing 'website' or 'query' parameter."
                )

            # No site named: a plain web search, as before.
            url = (
                "https://www.google.com/search?q="
                f"{urllib.parse.quote(query)}"
            )
            used_chrome, message = open_in_chrome(url)
            return "Website opened in Chrome." if used_chrome else message

        # A site *and* a query is one tab on that site's own results page, not
        # a blank home page followed by a separate Google search: "open youtube
        # and look up MKBHD" should land on YouTube's search results.
        return open_website_in_chrome(website, query)

class ClockSkill(Skill):
    name = "ClockSkill"
    description = "Returns the current time or date."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        now = datetime.datetime.now()
        if task.intent == "time":
            return f"The current time is {now.strftime('%I:%M %p')}."
        elif task.intent == "date":
            return f"Today's date is {now.strftime('%B %d, %Y')}."
        raise ValueError(f"Unsupported intent: {task.intent}")


def normalize_math_expression(expr: str) -> str:
    expr = expr.lower().strip()

    # Raised to the power
    expr = re.sub(
        r"(.+?)\s+raised\s+to\s+the\s+power\s+(.+)",
        r"\1**\2",
        expr
    )

    # Raised to
    expr = re.sub(
        r"(.+?)\s+raised\s+to\s+(.+)",
        r"\1**\2",
        expr
    )

    # Common mathematical words
    expr = expr.replace("multiplied by", "*")
    expr = expr.replace("divided by", "/")
    expr = expr.replace("times", "*")
    expr = expr.replace("plus", "+")
    expr = expr.replace("minus", "-")
    expr = expr.replace("×", "*")
    expr = expr.replace("÷", "/")
    expr = expr.replace("π", "pi")
    expr = expr.replace("^", "**")

    return expr


class MathSkill(Skill):
    name = "MathSkill"
    description = (
        "Evaluates arithmetic and solves mathematical expressions, equations, "
        "calculus, trigonometry, logarithms, and other mathematical problems."
    )
    version = "2.0.0"
    enabled = True

    # The expression arrives from an LLM or a speech transcript, so it is
    # untrusted input. Only these characters may survive normalisation, which
    # rules out names, attribute access, and calls before eval() ever runs.
    ALLOWED_CHARS = set("0123456789+-*/(). %")

    # Spoken arithmetic. Applied longest-phrase-first so that, for example,
    # "divided by" is matched before "by" would ever be considered.
    SPOKEN_OPERATORS = {
        "multiplied by": "*",
        "multiply by": "*",
        "divided by": "/",
        "divide by": "/",
        "to the power of": "**",
        "plus": "+",
        "add": "+",
        "minus": "-",
        "subtract": "-",
        "times": "*",
        "over": "/",
        "x": "*",
    }

    # Phrases that must not be rewritten before the symbolic pass. "x" is an
    # operator only in bare arithmetic ("3 x 4"); to SymPy it is the commonest
    # variable name, so rewriting it would break every algebraic expression.
    SYMBOLIC_UNSAFE_PHRASES = ("x",)

    # Names the symbolic evaluator understands. Anything not listed here is
    # parsed as a free symbol, not as a callable.
    SYMPY_NAMES = {
        "pi": sp.pi,
        "e": sp.E,
        "sqrt": sp.sqrt,
        "sin": sp.sin,
        "cos": sp.cos,
        "tan": sp.tan,
        "asin": sp.asin,
        "acos": sp.acos,
        "atan": sp.atan,
        "sinh": sp.sinh,
        "cosh": sp.cosh,
        "tanh": sp.tanh,
        "log": sp.log,
        "ln": sp.log,
        "exp": sp.exp,
        "abs": sp.Abs,
        "factorial": sp.factorial,
    } if sp is not None else {}

    def _strip_framing(self, raw: str) -> str:
        """Lower-case an utterance and drop the question wrapper around it."""
        text = str(raw).lower().strip()
        text = re.sub(r"^(what(?:s| is)|calculate|compute|how much is)\s+", "", text)
        return text.rstrip("?=. ")

    def _normalize(self, raw: str) -> str:
        """Turn a spoken or written sum into a bare arithmetic expression."""
        text = self._strip_framing(raw)

        for phrase, symbol in sorted(
            self.SPOKEN_OPERATORS.items(), key=lambda item: -len(item[0])
        ):
            text = re.sub(rf"\b{re.escape(phrase)}\b", symbol, text)

        text = text.replace("^", "**").replace("\u00d7", "*").replace("\u00f7", "/")

        return re.sub(r"\s+", "", text)

    def _normalize_symbolic(self, raw: str) -> str:
        """
        Normalise a spoken sum for SymPy while leaving symbol names intact.

        Runs the module-level word replacements first (they cover the multi-word
        power phrases), then the spoken-operator table for the phrases those do
        not reach, minus the ones that would clobber a variable name.
        """
        text = normalize_math_expression(self._strip_framing(raw))

        for phrase, symbol in sorted(
            self.SPOKEN_OPERATORS.items(), key=lambda item: -len(item[0])
        ):
            if phrase in self.SYMBOLIC_UNSAFE_PHRASES:
                continue
            text = re.sub(rf"\b{re.escape(phrase)}\b", symbol, text)

        return text.strip()

    def _evaluate_symbolic(self, expr: str) -> str:
        """
        Solve an expression symbolically. Raises on anything SymPy cannot parse.
        """
        if sp is None:
            raise ValueError("sympy is not installed")
        result = sp.sympify(expr, locals=self.SYMPY_NAMES)

        # A lone symbol means the utterance was a word, not a sum. Let the
        # caller fall through rather than reading the word back as an answer.
        if isinstance(result, sp.Symbol):
            raise ValueError(f"Not a mathematical expression: {expr}")

        result = sp.simplify(result)

        # Format numerical results
        if result.is_number:
            result = sp.N(result, 12)

            if result.is_real and result == sp.floor(result):
                result = int(result)
            else:
                result = str(result).rstrip("0").rstrip(".")

        return f"The result is {result}."

    def _evaluate_arithmetic(self, raw: str) -> str:
        """
        Evaluate plain arithmetic after normalisation. Only digits, operators
        and brackets survive :meth:`_normalize`, so eval() never sees a name,
        an attribute access or a call.
        """
        expr = self._normalize(raw)

        if not expr or not set(expr) <= self.ALLOWED_CHARS:
            raise ValueError(f"Could not calculate expression: {raw}")

        try:
            result = eval(expr, {"__builtins__": {}}, {})
        except Exception as exc:
            raise ValueError(f"Could not calculate expression: {raw}") from exc

        # 12/4 should read back as "3", not "3.0".
        if isinstance(result, float):
            result = round(result, 6)
            if result.is_integer():
                result = int(result)

        return f"The result is {result}."

    async def execute(self, task: Task) -> str:
        raw = str(task.parameters.get("expression", "") or "").strip()

        if not raw:
            raise ValueError("Missing 'expression' parameter.")

        # SymPy leads: it covers everything the arithmetic evaluator does plus
        # calculus, trigonometry and algebra. The arithmetic evaluator stays as
        # the backstop for spoken forms SymPy cannot parse, such as "3 x 4".
        try:
            return self._evaluate_symbolic(self._normalize_symbolic(raw))
        except Exception as symbolic_error:
            try:
                return self._evaluate_arithmetic(raw)
            except Exception:
                raise ValueError(
                    f"Could not calculate expression: {raw}"
                ) from symbolic_error

class WeatherSkill(Skill):
    name = "WeatherSkill"
    description = "Retrieves real-time weather using live meteorological service."
    version = "2.1.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        location = task.parameters.get("location", task.parameters.get("city", "")).strip()
        if location.lower() in ("current location", "here", "today", "now", "my location"):
            location = ""

        # Fast direct weather query via wttr.in (200ms, IP geo-located, no key required)
        try:
            import httpx, urllib.parse
            target_url = f"https://wttr.in/{urllib.parse.quote(location)}?format=3" if location else "https://wttr.in/?format=3"
            async with httpx.AsyncClient(verify=False, timeout=3.5) as client:
                resp = await client.get(target_url, headers={"User-Agent": "curl/8.0"})
                if resp.status_code == 200 and resp.text.strip():
                    return f"Current weather: {resp.text.strip()}"
        except Exception:
            pass

        # Fallback to web search
        try:
            from skills.web_skill import WebSkill
            web = WebSkill()
            query = f"current weather in {location or 'local area'} today"
            result = await web.search(query, max_results=2)
            if result:
                summary = result[0].snippet[:300]
                return f"Weather for {location or 'local area'}: {summary}"
            else:
                return f"Weather for {location or 'local area'} is temporarily unavailable."
        except Exception as e:
            return f"Weather retrieval failed: {str(e)}"

class ScreenshotSkill(Skill):
    name = "ScreenshotSkill"
    description = "Captures the screen and saves it as a PNG."
    version = "2.0.0"
    enabled = True

    # Linux desktops ship different capture tools; these are tried in order.
    LINUX_COMMANDS = (
        ("gnome-screenshot", "-f"),
        ("scrot",),
        ("spectacle", "-b", "-n", "-o"),
    )

    def _save_dir(self) -> str:
        """
        Pick the first user-visible folder that actually exists.

        A bare ~/Desktop is not safe to assume on Windows, where the folder is
        frequently redirected into OneDrive.
        """
        home = os.path.expanduser("~")

        for candidate in (
            os.path.join(home, "Desktop"),
            os.path.join(home, "OneDrive", "Desktop"),
            os.path.join(home, "Pictures"),
        ):
            if os.path.isdir(candidate):
                return candidate

        return home

    def _capture_windows(self, filepath: str) -> None:
        """
        Grab the screen through Pillow's ImageGrab.

        all_screens=True covers multi-monitor setups, which a primary-display
        capture would crop away.
        """
        from PIL import ImageGrab

        image = ImageGrab.grab(all_screens=True)
        image.save(filepath, "PNG")

    def _capture_linux(self, filepath: str) -> None:
        for command in self.LINUX_COMMANDS:
            try:
                subprocess.run([*command, filepath], check=True, capture_output=True)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue

        raise RuntimeError(
            "No screenshot tool available (tried gnome-screenshot, scrot, spectacle)."
        )

    async def execute(self, task: Task) -> str:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_at_%H.%M.%S")
        filepath = os.path.join(self._save_dir(), f"Screenshot_{timestamp}.png")

        system = platform.system()

        if system == "Windows":
            self._capture_windows(filepath)
        elif system == "Darwin":
            subprocess.run(["screencapture", filepath], check=True)
        else:
            self._capture_linux(filepath)

        return f"Screenshot saved to {filepath}."

class VolumeSkill(Skill):
    name = "VolumeSkill"
    description = "Adjusts system volume: up, down, mute, unmute, set %, max, min."
    version = "2.0.0"
    enabled = True

    # Step size in percentage points for relative up/down commands.
    STEP = 10

    def _get_windows_volume_interface(self):
        """
        Lazily import and resolve the Windows Core Audio volume interface.

        Goes through the raw IMMDeviceEnumerator COM interface rather than
        pycaw's AudioUtilities.GetSpeakers() helper, since newer pycaw
        versions wrap that call in an AudioDevice object that no longer
        exposes .Activate() directly. This lower-level path is stable
        across pycaw versions.
        """
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL, CoCreateInstance, GUID
        from pycaw.pycaw import (
            IMMDeviceEnumerator,
            IAudioEndpointVolume,
            EDataFlow,
            ERole,
        )

        CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")

        device_enumerator = CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            IMMDeviceEnumerator,
            CLSCTX_ALL,
        )
        endpoint = device_enumerator.GetDefaultAudioEndpoint(
            EDataFlow.eRender.value, ERole.eMultimedia.value
        )
        interface = endpoint.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None
        )
        return cast(interface, POINTER(IAudioEndpointVolume))

    def _execute_windows(self, action: str, level: int | None) -> str:
        volume = self._get_windows_volume_interface()

        # pycaw reports/accepts volume as a float scalar 0.0–1.0.
        current_scalar = volume.GetMasterVolumeLevelScalar()
        current_percent = round(current_scalar * 100)

        if action == "up":
            new_percent = min(100, current_percent + self.STEP)
            volume.SetMasterVolumeLevelScalar(new_percent / 100, None)
            return f"Volume increased to {new_percent}%."

        elif action == "down":
            new_percent = max(0, current_percent - self.STEP)
            volume.SetMasterVolumeLevelScalar(new_percent / 100, None)
            return f"Volume decreased to {new_percent}%."

        elif action == "mute":
            volume.SetMute(1, None)
            return "Volume muted."

        elif action == "unmute":
            volume.SetMute(0, None)
            return "Volume unmuted."

        elif action == "max":
            volume.SetMasterVolumeLevelScalar(1.0, None)
            return "Volume set to maximum."

        elif action == "min":
            volume.SetMasterVolumeLevelScalar(0.0, None)
            return "Volume set to minimum."

        elif action == "set":
            if level is None:
                raise ValueError("Missing 'level' for setting volume.")
            volume.SetMasterVolumeLevelScalar(level / 100, None)
            return f"Volume set to {level}%."

        raise ValueError(f"Unsupported volume action: '{action}'.")

    async def execute(self, task: Task) -> str:
        action = task.parameters.get("action")
        level = task.parameters.get("level")

        if not action:
            raise ValueError("Missing 'action' parameter.")

        system = platform.system()

    def _execute_linux(self, action: str, level: int | None) -> str:
        if shutil.which("pactl"):
            if action == "up":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{self.STEP}%"], check=True)
                return f"Volume increased by {self.STEP}%."
            elif action == "down":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{self.STEP}%"], check=True)
                return f"Volume decreased by {self.STEP}%."
            elif action == "mute":
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], check=True)
                return "Volume muted."
            elif action == "unmute":
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], check=True)
                return "Volume unmuted."
            elif action == "max":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"], check=True)
                return "Volume set to maximum."
            elif action == "min":
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "0%"], check=True)
                return "Volume set to minimum."
            elif action == "set":
                if level is None:
                    raise ValueError("Missing 'level' for setting volume.")
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
                return f"Volume set to {level}%."
        elif shutil.which("amixer"):
            if action == "up":
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{self.STEP}%+"], check=True)
                return "Volume increased."
            elif action == "down":
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{self.STEP}%-"], check=True)
                return "Volume decreased."
            elif action == "mute":
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "mute"], check=True)
                return "Volume muted."
            elif action == "unmute":
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "unmute"], check=True)
                return "Volume unmuted."
            elif action == "set":
                if level is None:
                    raise ValueError("Missing 'level' for setting volume.")
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"], check=True)
                return f"Volume set to {level}%."
        raise RuntimeError("Neither pactl nor amixer found for volume control on Linux.")

    async def execute(self, task: Task) -> str:
        action = task.parameters.get("action")
        level = task.parameters.get("level")

        if not action:
            raise ValueError("Missing 'action' parameter.")

        system = platform.system()

        if system == "Windows":
            return self._execute_windows(action, level)

        elif system == "Darwin":
            if action == "up":
                subprocess.run(
                    ["osascript", "-e",
                     f"set volume output volume (output volume of (get volume settings) + {self.STEP})"],
                    check=True,
                )
                return "Volume increased."
            elif action == "down":
                subprocess.run(
                    ["osascript", "-e",
                     f"set volume output volume (output volume of (get volume settings) - {self.STEP})"],
                    check=True,
                )
                return "Volume decreased."
            elif action == "mute":
                subprocess.run(["osascript", "-e", "set volume with output muted"], check=True)
                return "Volume muted."
            elif action == "unmute":
                subprocess.run(["osascript", "-e", "set volume without output muted"], check=True)
                return "Volume unmuted."
            elif action == "max":
                subprocess.run(["osascript", "-e", "set volume output volume 100"], check=True)
                return "Volume set to maximum."
            elif action == "min":
                subprocess.run(["osascript", "-e", "set volume output volume 0"], check=True)
                return "Volume set to minimum."
            elif action == "set":
                if level is None:
                    raise ValueError("Missing 'level' for setting volume.")
                subprocess.run(
                    ["osascript", "-e", f"set volume output volume {level}"],
                    check=True,
                )
                return f"Volume set to {level}%."
            raise ValueError(f"Unsupported volume action: '{action}'.")

        elif system == "Linux":
            return self._execute_linux(action, level)

        raise RuntimeError(f"Unsupported operating system: {system}")

class ChatSkill(Skill):
    """
    Conversational fallback: answers questions and small talk with the LLM.

    Every other skill in this module is deterministic. This is the one that
    hands the utterance back to the model and speaks whatever comes out. It
    carries the remembered facts and the recent conversation into the prompt,
    and strips the reasoning preamble a thinking model leaves in its reply.
    """

    name = "ChatSkill"
    description = "Answers general questions and small talk using the local LLM."
    version = "1.0.0"
    enabled = True

    # The reply is read aloud, so brevity matters more than completeness, and
    # every extra token is latency on a local model.
    SYSTEM_PROMPT = (
        "You are ULTRON, a friendly and capable assistant running locally on "
        "the user's computer.\n"
        "Your reply is spoken aloud, so answer in plain conversational prose: "
        "no markdown, no bullet points, no emoji, no code fences.\n"
        "Keep it to one or two short sentences unless the user asks for detail.\n"
        "If you do not know something, say so plainly rather than inventing it."
    )

    #: How many past turns of context to send with each request.
    HISTORY_TURNS = 10

    # Injected by the Executor through Skill.__init__; annotated only to narrow
    # the base class's Any for type checkers.
    container: ServiceContainer

    async def execute(self, task: Task) -> str:
        llm = self.container.llm
        utterance = task.metadata.get("raw_utterance") or task.parameters.get("text", "")

        system_prompt = self.SYSTEM_PROMPT

        # A store that will not read is a reason to answer without memory, not
        # a reason to lose the user's turn.
        try:
            memory_block = self.container.memory.render_block()
        except Exception:
            memory_block = ""

        if memory_block:
            system_prompt = f"{system_prompt}\n\n{memory_block}"

        messages = [llm.build_system_message(system_prompt)]

        history = self.container.state.conversation_history[-self.HISTORY_TURNS:]

        for turn in history:
            if turn.role == "assistant":
                messages.append(llm.build_assistant_message(turn.content))
            else:
                messages.append(llm.build_user_message(turn.content))

        # The Assistant records the incoming utterance before the pipeline runs,
        # so it is normally already the last history entry. Append it only when
        # it is missing, e.g. when the pipeline is driven without the facade.
        if utterance and (not history or history[-1].content != utterance):
            messages.append(llm.build_user_message(utterance))

        if len(messages) == 1:
            raise ValueError("Nothing to respond to.")

        # Ask for natural language rather than the JSON the intent detector
        # needs. Both provider spellings are passed because the two lines of
        # work named the switch differently; providers ignore the one they do
        # not recognise.
        response = await llm.complete(messages, json_mode=False, format=None)

        reply = (response.content or "").strip()

        # A thinking model narrates before it answers. Speak only the answer.
        if "FINAL:" in reply:
            reply = reply.split("FINAL:")[-1].strip()
        elif "</think>" in reply:
            reply = reply.split("</think>")[-1].strip()

        if not reply:
            raise ValueError("The language model returned an empty response.")

        return reply


class DefaultSkill(Skill):
    name = "DefaultSkill"
    description = "Default fallback skill."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        return f"No execution logic implemented for {task.intent}."