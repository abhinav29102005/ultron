"""
skills/media_skill.py – Spotify Desktop Playback Skill
=======================================================
Plays music in the Spotify *desktop application* and drives transport
controls (pause/resume/next/previous) through the Windows media keys.

Why not the Spotify Web API
---------------------------
The Web API would give exact, authoritative track lookup — but it needs an
OAuth flow, a registered developer application, a Premium account and the
user's credentials. None of that belongs in a local voice assistant, so this
skill deliberately uses only credential-free mechanisms:

  * the ``spotify:`` URI scheme, which the desktop client registers under
    ``HKCU\\Software\\Classes\\spotify``,
  * Spotify's public **oEmbed** endpoint (no auth) to confirm that a candidate
    track id really is the song the user asked for,
  * the free **iTunes Search API** (no key) to turn a half-remembered title
    into a canonical "Artist – Track",
  * the Windows media virtual-keys for transport control.

What was verified on Windows 11 with the Microsoft Store build of Spotify:

  * ``spotify:track:<id>`` starts playback of that track **only when the client
    is idle**. If something is already playing, the URI merely navigates. The
    reliable recipe is therefore: pause first (if the window title shows a
    track), then fire the URI. Verified 3/3 across two different tracks.
  * ``spotify:search:<query>`` opens the search page and never starts playback.
    Tapping play/pause afterwards resumes the *previously* playing track, not
    the search result, so this skill does not pretend otherwise.
  * ``VK_MEDIA_PLAY_PAUSE`` / ``NEXT`` / ``PREV`` work whether or not Spotify
    has focus.

The weak link is query -> track id, which without OAuth can only be done by
scraping search engines. When that fails the skill says so plainly and falls
back to opening Spotify's search page.

Team: Skills Team
"""

from __future__ import annotations

import asyncio
import csv
import ctypes
import io
import os
import platform
import re
import shutil
import subprocess
import urllib.parse
from typing import TYPE_CHECKING, Any, Optional

from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task


# ── Windows media virtual-key codes ────────────────────────────────────────
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
#: Utterances containing these never mean "start playing".
STOP_WORDS = (
    "stop", "pause", "shut up", "be quiet", "silence",
    "close spotify", "quit spotify", "kill spotify", "turn off",
)

VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_KEYUP = 0x0002

#: Spotify's main window title while nothing is playing. Anything else is
#: "Artist - Track", which is how this skill reads the transport state without
#: any API access at all.
IDLE_TITLES = {
    "",
    "spotify",
    "spotify free",
    "spotify premium",
    "n/a",
    "olemainthreadwndname",
    "default ime",
    "msctfime ui",
}

#: Spotify's helper processes own hidden windows whose titles look like real
#: ones to tasklist. Observed in the wild: a transient "GDI+ Window
#: (Spotify.exe)" appears for a second or two right as a track starts, which
#: would otherwise be read back to the user as the song title.
JUNK_TITLE_RE = re.compile(
    r"^(?:gdi\+ window|chrome_widgetwin|ime\b|\.net-broadcasteventwindow|"
    r"windows push notifications)",
    re.IGNORECASE,
)

#: A Spotify base-62 id is always 22 characters.
SPOTIFY_TRACK_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([A-Za-z0-9]{22})"
)


def send_media_key(vk_code: int) -> None:
    """Tap a media virtual-key. Windows delivers it to whichever player owns
    the media session, so Spotify does not need focus."""
    user32 = ctypes.windll.user32          # type: ignore[attr-defined]
    user32.keybd_event(vk_code, 0, 0, 0)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


class MediaSkill(Skill):
    """Plays music in the Spotify desktop app and controls playback."""

    name = "MediaSkill"
    description = (
        "Plays a named song in the Spotify desktop application and controls "
        "playback (pause, resume, next, previous, stop)."
    )
    version = "1.0.0"
    enabled = True

    #: Transport actions this skill understands, mapped to their media key.
    MEDIA_ACTIONS = {
        "pause": VK_MEDIA_PLAY_PAUSE,
        "resume": VK_MEDIA_PLAY_PAUSE,
        "play": VK_MEDIA_PLAY_PAUSE,
        "toggle": VK_MEDIA_PLAY_PAUSE,
        "next": VK_MEDIA_NEXT_TRACK,
        "previous": VK_MEDIA_PREV_TRACK,
        "stop": VK_MEDIA_PLAY_PAUSE,   # Spotify ignores VK_MEDIA_STOP.
    }

    #: Where the two Windows distributions of Spotify put their executable.
    #: The WindowsApps entry is the Store build's execution alias.
    SPOTIFY_PATHS = (
        r"%APPDATA%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
        r"%PROGRAMFILES%\Spotify\Spotify.exe",
    )

    HTTP_TIMEOUT = 8.0

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    #: Engines tried, in order, when hunting for an open.spotify.com/track link.
    #: DuckDuckGo rate-limits aggressively (HTTP 202 with an empty body), so it
    #: is not first.
    SEARCH_ENGINES = (
        "https://search.brave.com/search?q={q}",
        "https://html.duckduckgo.com/html/?q={q}",
        "https://www.bing.com/search?q={q}",
        "https://lite.duckduckgo.com/lite/?q={q}",
    )

    # ── Locating and launching the desktop app ─────────────────────────────

    def spotify_executable(self) -> Optional[str]:
        """Return the path to Spotify.exe, or None when it is not installed."""
        for template in self.SPOTIFY_PATHS:
            candidate = os.path.expandvars(template)
            # expandvars leaves an unset %VAR% verbatim; that never exists.
            if "%" not in candidate and os.path.isfile(candidate):
                return candidate

        return shutil.which("Spotify.exe") or shutil.which("spotify")

    def is_spotify_running(self) -> bool:
        return self._spotify_window_title() is not None

    def _spotify_window_title(self) -> Optional[str]:
        """
        Return Spotify's main window title, or None when Spotify is not running.

        Spotify runs half a dozen helper processes; only the UI process carries
        a real title. tasklist is used rather than a COM/WinRT session query
        because it needs no extra dependency and costs ~300 ms.
        """
        try:
            output = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/FO", "CSV", "/V"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
        except Exception:
            return None

        rows = list(csv.reader(io.StringIO(output)))
        if len(rows) < 2:
            return None

        found_process = False
        candidates: list[str] = []

        for row in rows[1:]:
            if not row or not row[0].lower().startswith("spotify"):
                continue
            found_process = True
            title = row[-1].strip()
            if title.lower() in IDLE_TITLES or JUNK_TITLE_RE.match(title):
                continue
            candidates.append(title)

        if not found_process:
            return None

        # "Artist - Track" is the shape the UI process uses, so prefer it over
        # any other stray window that survived the junk filter.
        for title in candidates:
            if " - " in title:
                return title

        return candidates[0] if candidates else ""

    def is_playing(self) -> bool:
        """True when Spotify's window title names a track rather than the app."""
        title = self._spotify_window_title()
        return bool(title) and title.lower() not in IDLE_TITLES

    async def ensure_spotify_running(self) -> bool:
        """
        Launch Spotify if it is not already up and wait for its window.

        Returns False when Spotify is not installed at all.
        """
        if self.is_spotify_running():
            return True

        executable = self.spotify_executable()
        if not executable:
            return False

        try:
            subprocess.Popen([executable])
        except Exception:
            return False

        # The client takes a few seconds to paint its window on a cold start.
        for _ in range(20):
            await asyncio.sleep(0.75)
            if self.is_spotify_running():
                return True

        return True

    # ── Credential-free track resolution ───────────────────────────────────

    async def _canonicalise(self, query: str) -> Optional[str]:
        """
        Turn a half-remembered title into "Artist Track" using the free,
        keyless iTunes Search API. Purely a query improver: a miss here is not
        an error, it just means we search with the user's own words.
        """
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=self.HTTP_TIMEOUT, headers={"User-Agent": self.USER_AGENT}
            ) as client:
                response = await client.get(
                    "https://itunes.apple.com/search",
                    params={"term": query, "entity": "song", "limit": 1},
                )
                results = response.json().get("results") or []
        except Exception:
            return None

        if not results:
            return None

        track = results[0]
        artist = str(track.get("artistName") or "").strip()
        title = str(track.get("trackName") or "").strip()

        return f"{artist} {title}".strip() or None

    async def _track_title(self, track_id: str) -> Optional[str]:
        """
        Ask Spotify's public oEmbed endpoint what a track id actually is.

        This needs no authentication and is the only way to be sure a scraped
        id is the song the user asked for rather than a live version, a remix
        or an unrelated track by the same artist.
        """
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=self.HTTP_TIMEOUT, headers={"User-Agent": self.USER_AGENT}
            ) as client:
                response = await client.get(
                    "https://open.spotify.com/oembed",
                    params={"url": f"spotify:track:{track_id}"},
                )
                if response.status_code != 200:
                    return None
                return str(response.json().get("title") or "") or None
        except Exception:
            return None

    #: Guest-artist credits Spotify appends to a title but a user never says.
    _CREDIT_RE = re.compile(
        r"[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\b[^\)\]]*[\)\]]",
        re.IGNORECASE,
    )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}

    def _titles_agree(self, wanted: str, found: str) -> bool:
        """
        Decide whether an oEmbed title is the song that was asked for.

        The test runs one way only: every distinctive word Spotify shows must
        have been asked for. The reverse would be wrong, because the user
        usually supplies an artist name the title never repeats.

        Being strict here is the point. A loose match happily returns
        "Shape of You - Live" or a karaoke cover for "shape of you", and
        playing the wrong recording is worse than admitting the lookup failed
        and opening the search page instead.
        """
        wanted_tokens = self._tokens(wanted)
        found_tokens = self._tokens(self._CREDIT_RE.sub("", found))

        if not wanted_tokens or not found_tokens:
            return False

        return found_tokens <= wanted_tokens

    async def resolve_track_id(self, query: str) -> Optional[tuple[str, str]]:
        """
        Best-effort, credential-free lookup of a Spotify track id.

        Returns ``(track_id, verified_title)`` or None. Every candidate is
        confirmed against Spotify's oEmbed endpoint before it is returned, so a
        result is either the right song or nothing at all.
        """
        try:
            import httpx
        except Exception:
            return None

        canonical = await self._canonicalise(query)
        search_terms = [t for t in (canonical, query) if t]

        seen: set[str] = set()

        async with httpx.AsyncClient(
            timeout=self.HTTP_TIMEOUT,
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
        ) as client:
            # Two query shapes, because the site: operator gives the cleanest
            # hits when an engine honours it and no hits at all when it does
            # not, while the loose form catches pages that merely link to the
            # track. Every candidate is verified either way.
            forms = [
                '"{term}" site:open.spotify.com/track',
                "{term} song open.spotify.com track",
            ]

            for term, form in ((t, f) for f in forms for t in search_terms):
                encoded = urllib.parse.quote(form.format(term=term))

                for engine in self.SEARCH_ENGINES:
                    try:
                        response = await client.get(engine.format(q=encoded))
                    except Exception:
                        continue

                    if response.status_code != 200:
                        continue

                    candidates = SPOTIFY_TRACK_RE.findall(
                        urllib.parse.unquote(response.text)
                    )

                    for track_id in candidates[:4]:
                        if track_id in seen:
                            continue
                        seen.add(track_id)

                        title = await self._track_title(track_id)
                        if title and self._titles_agree(term, title):
                            return track_id, title

        return None

    # ── Playback ───────────────────────────────────────────────────────────

    def _open_uri(self, uri: str) -> None:
        os.startfile(uri)  # type: ignore[attr-defined]

    async def play_track_uri(self, track_id: str) -> None:
        """
        Play a specific track.

        The desktop client only *starts* playback from a ``spotify:track:``
        URI when it is idle — when something is already playing the URI just
        navigates. Pausing first makes the outcome deterministic.
        """
        if self.is_playing():
            send_media_key(VK_MEDIA_PLAY_PAUSE)
            await asyncio.sleep(1.0)

        self._open_uri(f"spotify:track:{track_id}")
        await asyncio.sleep(2.0)

    async def open_search(self, query: str) -> None:
        self._open_uri("spotify:search:" + urllib.parse.quote(query))

    # ── Intent handlers ────────────────────────────────────────────────────

    async def _handle_play(self, task: Task) -> str:
        query = str(
            task.parameters.get("query")
            or task.parameters.get("song")
            or task.parameters.get("track")
            or ""
        ).strip()

        if not await self.ensure_spotify_running():
            return (
                "I could not find the Spotify desktop app on this computer. "
                "Install Spotify and I will be able to play music for you."
            )

        # "Play some music" with nothing named: just resume the client.
        if not query:
            if self.is_playing():
                return "Spotify is already playing."
            send_media_key(VK_MEDIA_PLAY_PAUSE)
            await asyncio.sleep(1.0)
            title = self._spotify_window_title()
            if title:
                return f"Playing {title} on Spotify."
            return "Started Spotify playback."

        resolved = await self.resolve_track_id(query)

        if resolved:
            track_id, title = resolved
            await self.play_track_uri(track_id)

            now_playing = self._spotify_window_title()
            if now_playing:
                return f"Playing {now_playing} on Spotify."
            return f"Playing {title} on Spotify."

        # Honest fallback. Without OAuth there is no authoritative way to turn
        # a spoken title into a track id, so say what actually happened rather
        # than claiming the song is playing.
        await self.open_search(query)
        return (
            f"I could not pin down an exact Spotify track for '{query}', so I "
            f"opened Spotify on the search results for it. Pick a track and "
            f"I can control playback from there."
        )

    async def _handle_control(self, task: Task) -> str:
        action = str(task.parameters.get("action") or "").strip().lower()

        if action not in self.MEDIA_ACTIONS:
            raise ValueError(
                f"Unsupported media action: '{action}'. Expected one of: "
                + ", ".join(sorted(self.MEDIA_ACTIONS))
            )

        # "Pause" when nothing plays would start playback, since the key is a
        # toggle. Read the transport state first and no-op instead.
        playing = self.is_playing()

        if action in ("pause", "stop") and not playing:
            return "Nothing is playing right now."

        if action in ("resume", "play") and playing:
            return "Music is already playing."

        send_media_key(self.MEDIA_ACTIONS[action])
        await asyncio.sleep(1.0)

        title = self._spotify_window_title()

        if action in ("pause", "stop"):
            return "Playback paused."
        if action in ("next", "previous"):
            direction = "next" if action == "next" else "previous"
            return f"Skipped to the {direction} track." + (
                f" Now playing {title}." if title else ""
            )
        return f"Playing {title}." if title else "Playback resumed."

    async def execute(self, task: Task) -> str:
        if platform.system() != "Windows":
            return (
                "Music playback is only wired up for Windows on this build."
            )

        if task.intent == "media_control":
            return await self._handle_control(task)

        # Safety net. Intent classification runs on a small local model over a
        # speech transcript, and a clipped "stop the music" can arrive as just
        # "music" -- which looks like play_music with no query and would answer
        # "Spotify is already playing". Never start playback for an utterance
        # that plainly asks to stop it.
        utterance = " ".join(
            str(task.parameters.get(k) or "")
            for k in ("raw_utterance", "text", "query", "song", "track")
        ).lower()
        if any(w in utterance for w in STOP_WORDS):
            task.parameters.setdefault("action", "stop")
            return await self._handle_control(task)

        return await self._handle_play(task)
