"""
tests/test_skills_media.py – Media, Chrome and Web-Lookup Tests
================================================================
Covers the three pieces added for the "play my music" and "look it up in
Chrome" complaints:

  * intent detection for play_music / media_control / web_lookup / farewell,
  * Chrome path resolution, with the registry and filesystem mocked so the
    test says the same thing on a machine without Chrome,
  * the web-lookup boundary, which decides whether a question is answered
    from the model or from a real browser tab.

Nothing here launches a browser, a music player or a network request.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.validator import TaskValidator
from intelligence.intent_detector import (
    IntentDetector,
    is_web_lookup_blocked,
    needs_web_lookup,
)
from intelligence.parser import STTParser
from intelligence.router import TaskRouter
from intelligence.task import Task, TaskStatus
from skills.media_skill import MediaSkill
from skills.system_skills import DefaultSkill, find_chrome, open_in_chrome
from skills.web_skill import WebLookupSkill


def make_task(intent: str, **parameters) -> Task:
    return Task(
        task_id="test-media",
        skill_name="test",
        intent=intent,
        parameters=parameters,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


def detector() -> IntentDetector:
    """An IntentDetector with no LLM. Only the rule-based path is exercised."""
    return IntentDetector(llm=None)


def match(utterance: str) -> str:
    """Run an utterance through normalisation and the rule-based matcher."""
    normalized = STTParser.parse(utterance)["normalized_text"]
    return detector()._rule_based_match(normalized)


# ── The web-lookup boundary ───────────────────────────────────────────────
#
# This is the judgement call the whole feature turns on: a question needs the
# web when answering it requires current or external information, and must not
# open a tab when Friday, the OS, or arithmetic can answer it.


class TestWebLookupBoundary:
    """Questions that must NOT open a browser tab."""

    @pytest.mark.parametrize(
        "utterance",
        [
            # Arithmetic belongs to MathSkill.
            "what is 2+2",
            "what's 2 + 2",
            "whats 15 times 4",
            "calculate 144 divided by 12",
            "compute the square root of 81",
            # The clock and calendar belong to ClockSkill.
            "what time is it",
            "what's the time",
            "what's today's date",
            "what day is it",
            # The weather has its own skill.
            "what's the weather today",
            "what's the temperature right now",
            # Questions about Friday itself.
            "what can you do",
            "who are you",
            "what's your name",
            # Machine commands.
            "open chrome",
            "play blinding lights",
            "turn up the volume",
            "take a screenshot",
            "close spotify",
            # Memory.
            "what do you know about me",
            "forget where I live",
            # Small talk.
            "hi there",
            "hello",
            "thanks",
            "how are you",
            "good night",
            "bye bye",
        ],
    )
    def test_does_not_trigger_web_lookup(self, utterance):
        normalized = STTParser.parse(utterance)["normalized_text"]
        assert needs_web_lookup(normalized) is False, utterance

    @pytest.mark.parametrize(
        "utterance",
        [
            # The headline case from the user's complaint.
            "who won the election",
            # Explicit search requests.
            "search for python tutorials",
            "look up the mars rover",
            "google quantum computing",
            "find information about the amazon rainforest",
            "search the web for tide times",
            # Recency: the model's weights cannot answer these.
            "what's the latest news on ai",
            "what's the current price of bitcoin",
            "what happened with the stock market",
            "what's the score of the game right now",
            "when is the next spacex launch",
            # Real-world entities.
            "who is elon musk",
            "who was ada lovelace",
            "tell me about the eiffel tower",
        ],
    )
    def test_does_trigger_web_lookup(self, utterance):
        normalized = STTParser.parse(utterance)["normalized_text"]
        assert needs_web_lookup(normalized) is True, utterance

    def test_arithmetic_stays_local_even_with_a_recency_word(self):
        """A blocker outranks a trigger; "today" must not drag maths online."""
        assert is_web_lookup_blocked("what is 2+2 today") is True
        assert needs_web_lookup("what is 2+2 today") is False

    def test_weather_stays_with_the_weather_skill(self):
        """"today" is a recency marker, but WeatherSkill already owns this."""
        assert needs_web_lookup("what's the weather today") is False


class TestWebLookupCorrection:
    """The LLM's classification is reconciled with the boundary."""

    def _one(self, intent, text, entities=None):
        from intelligence.intent_detector import DetectedIntent

        return [
            DetectedIntent(
                intent=intent,
                confidence=0.9,
                entities=entities if entities is not None else {},
                raw_utterance=text,
            )
        ]

    def test_general_chat_is_promoted_when_the_web_is_needed(self):
        """The exact bug the user reported: answered from memory, not the web."""
        result = detector()._apply_web_lookup_boundary(
            self._one("general_chat", "who won the election"),
            "who won the election",
        )
        assert result[0].intent == "web_lookup"
        assert result[0].entities["query"] == "who won the election"

    def test_web_lookup_is_demoted_for_arithmetic(self):
        result = detector()._apply_web_lookup_boundary(
            self._one("web_lookup", "what is 2+2"), "what is 2+2"
        )
        assert result[0].intent == "general_chat"

    def test_query_framing_is_stripped(self):
        result = detector()._apply_web_lookup_boundary(
            self._one("web_lookup", "look up the mars rover"),
            "look up the mars rover",
        )
        assert result[0].entities["query"] == "the mars rover"

    def test_compound_requests_are_left_alone(self):
        """Two intents constrain each other; second-guessing one harms both."""
        from intelligence.intent_detector import DetectedIntent

        pair = [
            DetectedIntent("open_application", 0.9, {"application": "chrome"}, "x"),
            DetectedIntent("general_chat", 0.9, {}, "x"),
        ]
        result = detector()._apply_web_lookup_boundary(
            pair, "open chrome and who won the election"
        )
        assert [i.intent for i in result] == ["open_application", "general_chat"]


# ── Intent detection for the new intents ──────────────────────────────────


class TestNewIntentDetection:
    @pytest.mark.parametrize(
        "utterance",
        ["bye", "bye bye", "goodbye", "good night", "see you", "see ya",
         "talk to you later", "catch you later", "farewell"],
    )
    def test_farewell(self, utterance):
        assert match(utterance) == "farewell"

    @pytest.mark.parametrize(
        "utterance",
        ["good morning friday", "hello there", "hi"],
    )
    def test_greetings_are_not_farewells(self, utterance):
        assert match(utterance) != "farewell"

    @pytest.mark.parametrize(
        "utterance",
        ["play blinding lights", "play some music",
         "play bohemian rhapsody by queen", "put on despacito"],
    )
    def test_play_music(self, utterance):
        assert match(utterance) == "play_music"

    @pytest.mark.parametrize(
        "utterance,action",
        [
            ("pause the music", "pause"),
            ("pause", "pause"),
            ("resume the music", "resume"),
            ("next song", "next"),
            ("skip this track", "next"),
            ("previous song", "previous"),
            ("stop the music", "stop"),
        ],
    )
    def test_media_control(self, utterance, action):
        assert match(utterance) == "media_control"
        normalized = STTParser.parse(utterance)["normalized_text"]
        assert detector()._media_action(normalized) == action

    def test_stop_the_music_is_not_closing_an_application(self):
        assert match("stop the music") != "close_application"

    def test_song_query_survives_the_fallback(self):
        parsed = STTParser.parse("play bohemian rhapsody by queen")
        detected = detector()._fallback("play bohemian rhapsody by queen", parsed)
        assert detected[0].intent == "play_music"
        assert detected[0].entities["query"] == "bohemian rhapsody by queen"

    def test_generic_play_carries_no_query(self):
        parsed = STTParser.parse("play some music")
        detected = detector()._fallback("play some music", parsed)
        assert detected[0].intent == "play_music"
        assert "query" not in detected[0].entities

    def test_new_intents_are_accepted_by_the_detector(self):
        for intent in ("play_music", "media_control", "web_lookup", "farewell"):
            assert intent in IntentDetector.VALID_INTENTS


class TestRouting:
    def test_new_intents_are_routed(self):
        table = TaskRouter.ROUTING_TABLE
        assert table["play_music"] is MediaSkill
        assert table["media_control"] is MediaSkill
        # Informational requests no longer just open a tab and leave the
        # reading to the user. They run the multi-round research loop and come
        # back with a cited answer; WebLookupSkill still exists and still
        # works, it is simply no longer what these intents route to.
        from skills.research_skill import DeepResearchSkill

        assert table["web_lookup"] is DeepResearchSkill
        assert table["search_web"] is DeepResearchSkill
        assert table["news"] is DeepResearchSkill

    def test_farewell_routes_to_the_farewell_skill(self):
        """"bye bye" says goodbye and hides the window to the tray."""
        from skills.farewell_skill import FarewellSkill

        assert TaskRouter.ROUTING_TABLE["farewell"] is FarewellSkill


class TestValidation:
    def test_web_lookup_requires_something_to_look_up(self):
        result = TaskValidator().validate(make_task("web_lookup"))
        assert result.valid is False
        assert "query" in result.missing_parameters

    def test_web_lookup_falls_back_to_the_raw_utterance(self):
        task = make_task("web_lookup", raw_utterance="who won the election")
        result = TaskValidator().validate(task)
        assert result.valid is True
        assert task.parameters["query"] == "who won the election"

    def test_play_music_without_a_song_is_valid(self):
        result = TaskValidator().validate(make_task("play_music"))
        assert result.valid is True

    def test_media_control_requires_an_action(self):
        result = TaskValidator().validate(make_task("media_control"))
        assert result.valid is False
        assert "action" in result.missing_parameters

    def test_media_control_rejects_an_unknown_action(self):
        result = TaskValidator().validate(make_task("media_control", action="rewind"))
        assert result.valid is False

    def test_media_control_normalises_case(self):
        task = make_task("media_control", action="  Next ")
        assert TaskValidator().validate(task).valid is True
        assert task.parameters["action"] == "next"

    def test_farewell_is_always_valid(self):
        assert TaskValidator().validate(make_task("farewell")).valid is True


# ── Chrome resolution ─────────────────────────────────────────────────────


class TestChromeResolution:
    """Registry and filesystem are mocked so these hold on any machine."""

    def test_registry_hit_wins(self):
        expected = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        with patch("skills.system_skills.platform.system", return_value="Windows"), \
             patch("skills.system_skills._chrome_from_registry", return_value=expected):
            assert find_chrome() == expected

    def test_falls_back_to_program_files_when_the_registry_misses(self):
        expected = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        with patch("skills.system_skills.platform.system", return_value="Windows"), \
             patch("skills.system_skills._chrome_from_registry", return_value=None), \
             patch("skills.system_skills.os.path.expandvars",
                   side_effect=lambda p: p.replace("%PROGRAMFILES%", r"C:\Program Files")
                                          .replace("%PROGRAMFILES(X86)%", r"C:\Program Files (x86)")
                                          .replace("%LOCALAPPDATA%", r"C:\Users\x\AppData\Local")), \
             patch("skills.system_skills.os.path.isfile",
                   side_effect=lambda p: p == expected):
            assert find_chrome() == expected

    def test_returns_none_when_chrome_is_absent(self):
        with patch("skills.system_skills.platform.system", return_value="Windows"), \
             patch("skills.system_skills._chrome_from_registry", return_value=None), \
             patch("skills.system_skills.os.path.isfile", return_value=False), \
             patch("skills.system_skills.shutil.which", return_value=None):
            assert find_chrome() is None

    def test_unexpanded_variables_are_never_treated_as_paths(self):
        """expandvars leaves an unset %VAR% verbatim; that is not a real path."""
        with patch("skills.system_skills.platform.system", return_value="Windows"), \
             patch("skills.system_skills._chrome_from_registry", return_value=None), \
             patch("skills.system_skills.os.path.expandvars", side_effect=lambda p: p), \
             patch("skills.system_skills.os.path.isfile", return_value=True), \
             patch("skills.system_skills.shutil.which", return_value=None):
            assert find_chrome() is None

    def test_open_in_chrome_launches_chrome_directly(self):
        chrome = r"C:\chrome.exe"
        with patch("skills.system_skills.find_chrome", return_value=chrome), \
             patch("skills.system_skills.subprocess.Popen") as popen:
            used_chrome, message = open_in_chrome("https://example.com")

        assert used_chrome is True
        popen.assert_called_once_with([chrome, "--new-tab", "https://example.com"])
        assert "Chrome" in message

    def test_open_in_chrome_falls_back_and_says_so(self):
        """A missing Chrome must not mean a missing tab — but say which browser."""
        with patch("skills.system_skills.find_chrome", return_value=None), \
             patch("skills.system_skills.webbrowser.open", return_value=True) as opener:
            used_chrome, message = open_in_chrome("https://example.com")

        assert used_chrome is False
        opener.assert_called_once_with("https://example.com")
        assert "default browser" in message

    def test_open_in_chrome_reports_total_failure(self):
        with patch("skills.system_skills.find_chrome", return_value=None), \
             patch("skills.system_skills.webbrowser.open", return_value=False):
            used_chrome, message = open_in_chrome("https://example.com")

        assert used_chrome is False
        assert "Failed" in message


class TestWebLookupSkill:
    async def test_opens_a_chrome_tab_for_the_query(self):
        with patch("skills.system_skills.open_in_chrome",
                   return_value=(True, "Opened in Chrome.")) as opener:
            result = await WebLookupSkill().execute(
                make_task("web_lookup", query="who won the election")
            )

        url = opener.call_args[0][0]
        assert url.startswith("https://www.google.com/search?q=")
        assert "who+won+the+election" in url or "who%20won%20the%20election" in url
        assert "Chrome tab" in result

    async def test_builds_the_query_from_the_utterance_when_none_was_extracted(self):
        with patch("skills.system_skills.open_in_chrome",
                   return_value=(True, "Opened in Chrome.")) as opener:
            await WebLookupSkill().execute(
                make_task("web_lookup", text="look up the mars rover")
            )

        assert "mars" in opener.call_args[0][0]
        assert "look" not in opener.call_args[0][0]

    async def test_missing_query_is_an_error(self):
        with pytest.raises(ValueError):
            await WebLookupSkill().execute(make_task("web_lookup"))


# ── MediaSkill ────────────────────────────────────────────────────────────


class TestMediaSkillTransportState:
    """Playback state is read from Spotify's window title, so test that."""

    @pytest.mark.parametrize(
        "title,playing",
        [
            ("Ed Sheeran - Shape of You", True),
            ("Spotify Premium", False),
            ("Spotify Free", False),
            ("", False),
        ],
    )
    def test_is_playing(self, title, playing):
        skill = MediaSkill()
        with patch.object(MediaSkill, "_spotify_window_title", return_value=title):
            assert skill.is_playing() is playing

    def test_transient_helper_windows_are_ignored(self):
        """A "GDI+ Window (Spotify.exe)" briefly appears as a track starts."""
        csv_output = (
            '"Image Name","PID","Window Title"\n'
            '"Spotify.exe","1","GDI+ Window (Spotify.exe)"\n'
            '"Spotify.exe","2","Ed Sheeran - Shape of You"\n'
        )
        with patch("skills.media_skill.subprocess.run") as run:
            run.return_value.stdout = csv_output
            assert MediaSkill()._spotify_window_title() == "Ed Sheeran - Shape of You"

    def test_no_spotify_process_reads_as_not_running(self):
        with patch("skills.media_skill.subprocess.run") as run:
            run.return_value.stdout = "INFO: No tasks are running.\n"
            skill = MediaSkill()
            assert skill._spotify_window_title() is None
            assert skill.is_spotify_running() is False


class TestMediaSkillPlayback:
    async def test_pauses_before_firing_the_track_uri(self):
        """
        Verified on Windows: spotify:track: only *starts* playback when the
        client is idle. Pausing first is what makes "play X" deterministic.
        """
        skill = MediaSkill()
        with patch.object(MediaSkill, "is_playing", return_value=True), \
             patch("skills.media_skill.send_media_key") as key, \
             patch.object(MediaSkill, "_open_uri") as open_uri:
            await skill.play_track_uri("7qiZfU4dY1lWllzX7mPBI3")

        key.assert_called_once()
        open_uri.assert_called_once_with("spotify:track:7qiZfU4dY1lWllzX7mPBI3")

    async def test_does_not_pause_when_already_idle(self):
        skill = MediaSkill()
        with patch.object(MediaSkill, "is_playing", return_value=False), \
             patch("skills.media_skill.send_media_key") as key, \
             patch.object(MediaSkill, "_open_uri") as open_uri:
            await skill.play_track_uri("7qiZfU4dY1lWllzX7mPBI3")

        key.assert_not_called()
        open_uri.assert_called_once()

    async def test_unresolvable_song_opens_search_and_admits_it(self):
        """The honest fallback: no OAuth means no guaranteed exact match."""
        skill = MediaSkill()
        with patch.object(MediaSkill, "ensure_spotify_running", return_value=True), \
             patch.object(MediaSkill, "resolve_track_id", return_value=None), \
             patch.object(MediaSkill, "open_search") as search:
            result = await skill.execute(make_task("play_music", query="some obscure b-side"))

        search.assert_called_once_with("some obscure b-side")
        assert "could not pin down" in result
        assert "search results" in result

    async def test_missing_spotify_degrades_with_a_clear_message(self):
        skill = MediaSkill()
        with patch.object(MediaSkill, "ensure_spotify_running", return_value=False):
            result = await skill.execute(make_task("play_music", query="anything"))

        assert "could not find the Spotify desktop app" in result

    async def test_pause_when_nothing_plays_does_not_toggle_playback(self):
        """The media key is a toggle, so a blind tap would start the music."""
        skill = MediaSkill()
        with patch.object(MediaSkill, "is_playing", return_value=False), \
             patch("skills.media_skill.send_media_key") as key:
            result = await skill.execute(make_task("media_control", action="pause"))

        key.assert_not_called()
        assert "Nothing is playing" in result

    async def test_next_track_sends_the_next_media_key(self):
        from skills.media_skill import VK_MEDIA_NEXT_TRACK

        skill = MediaSkill()
        with patch.object(MediaSkill, "is_playing", return_value=True), \
             patch.object(MediaSkill, "_spotify_window_title", return_value="A - B"), \
             patch("skills.media_skill.send_media_key") as key:
            result = await skill.execute(make_task("media_control", action="next"))

        key.assert_called_once_with(VK_MEDIA_NEXT_TRACK)
        assert "next track" in result

    async def test_unknown_action_is_rejected(self):
        with pytest.raises(ValueError):
            await MediaSkill().execute(make_task("media_control", action="rewind"))


class TestTrackVerification:
    """Scraped track ids are confirmed via Spotify's public oEmbed endpoint."""

    @pytest.mark.parametrize(
        "wanted,found,agree",
        [
            ("ed sheeran shape of you", "Shape of You", True),
            ("blinding lights", "Blinding Lights", True),
            # A live cut is not what "shape of you" asked for.
            ("shape of you", "Shape of You - Live", False),
            ("bohemian rhapsody", "The Show Must Go On", False),
        ],
    )
    def test_titles_agree(self, wanted, found, agree):
        assert MediaSkill()._titles_agree(wanted, found) is agree

    def test_track_id_pattern_matches_real_spotify_urls(self):
        from skills.media_skill import SPOTIFY_TRACK_RE

        assert SPOTIFY_TRACK_RE.findall(
            "https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3?si=abc"
        ) == ["7qiZfU4dY1lWllzX7mPBI3"]
        # Spotify localises track URLs with an intl- prefix.
        assert SPOTIFY_TRACK_RE.findall(
            "https://open.spotify.com/intl-de/track/0VjIjW4GlUZAMYd2vXMi3b"
        ) == ["0VjIjW4GlUZAMYd2vXMi3b"]
        assert SPOTIFY_TRACK_RE.findall(
            "https://open.spotify.com/album/1ATL5GLyefJaxhQzSPVrLX"
        ) == []
