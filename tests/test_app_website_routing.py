"""
tests/test_app_website_routing.py – "open youtube" is a site, not a program
===========================================================================
A user asked ULTRON to "open youtube in chrome and look up <youtuber>" and
got the YouTube Music desktop app instead. Three separate faults lined up:

* The Start menu's containment score treated "youtube" inside "youtube music"
  as a 0.95 match, so any site the user named was captured by whatever
  installed program was spelled similarly.
* BrowserSkill turned a bare site name into "https://" + the word, so even
  when the request was routed correctly the URL was unresolvable.
* Nothing modelled "open site X and search it for Y", so the query was either
  dropped or opened as a second, separate Google tab.

These tests pin all three, plus the matches the shortcut finder's comments
say must keep working.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from intelligence.intent_detector import IntentDetector
from intelligence.parser import STTParser
from intelligence.task import Task, TaskStatus
from skills.system_skills import (
    ApplicationSkill,
    BrowserSkill,
    build_website_url,
    resolve_website,
)


def make_task(intent: str, **parameters) -> Task:
    return Task(
        task_id="test-routing",
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


@pytest.fixture
def opened(monkeypatch):
    """Capture the URL that would have been opened instead of opening it."""
    seen: list[str] = []

    def fake_open_in_chrome(url: str):
        seen.append(url)
        return True, "Opened in Chrome."

    monkeypatch.setattr(
        "skills.system_skills.open_in_chrome", fake_open_in_chrome
    )
    return seen


@pytest.fixture
def start_menu(monkeypatch, tmp_path):
    """A Start menu containing exactly the shortcuts a test asks for."""

    def install(*names: str) -> None:
        for name in names:
            (tmp_path / f"{name}.lnk").write_text("", encoding="utf-8")
        monkeypatch.setattr(
            ApplicationSkill, "START_MENU_DIRS", (str(tmp_path),)
        )

    return install


class TestStartMenuDoesNotStealWebsiteNames:
    def test_youtube_does_not_match_youtube_music(self, start_menu):
        """The reported bug: the app that shares the site's first word won."""
        start_menu("YouTube Music")
        assert ApplicationSkill()._find_start_menu_shortcut("youtube") is None

    def test_recovery_does_not_match_recovery_drive(self, start_menu):
        """Documented regression: this one formats a USB drive."""
        start_menu("Recovery Drive", "RecoveryDrive")
        assert ApplicationSkill()._find_start_menu_shortcut("recovery") is None

    def test_obs_studio_does_not_match_roblox_studio(self, start_menu):
        """Documented regression, guarded by the fuzzy-ratio floor."""
        start_menu("Roblox Studio")
        assert ApplicationSkill()._find_start_menu_shortcut("obs studio") is None


class TestStartMenuStillFindsRealApps:
    def test_exact_name_matches(self, start_menu):
        start_menu("Claude")
        found = ApplicationSkill()._find_start_menu_shortcut("claude")
        assert found is not None and found.endswith("Claude.lnk")

    def test_parenthetical_variant_still_matches(self, start_menu):
        """"(uninstall)" is decoration, not a different product's name."""
        start_menu("Claude (uninstall)")
        found = ApplicationSkill()._find_start_menu_shortcut("claude")
        assert found is not None and "Claude (uninstall)" in found

    def test_plain_name_beats_the_parenthetical_variant(self, start_menu):
        start_menu("Claude", "Claude (uninstall)")
        found = ApplicationSkill()._find_start_menu_shortcut("claude")
        assert found.endswith("Claude.lnk")

    def test_decorated_suffix_still_matches(self, start_menu):
        """Coverage stays high, so "++" is not treated as another product."""
        start_menu("Notepad++")
        assert ApplicationSkill()._find_start_menu_shortcut("notepad") is not None

    def test_the_canonical_alias_is_tried_too(self, start_menu):
        """"open claude desktop" resolves to the alias the shortcut uses."""
        start_menu("Claude")
        assert (
            ApplicationSkill()._find_start_menu_shortcut("claude", "claude desktop")
            is not None
        )


class TestWebsiteUrls:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("youtube", "https://www.youtube.com"),
            ("gmail", "https://mail.google.com"),
            ("github", "https://github.com"),
            ("google maps", "https://www.google.com/maps"),
            ("twitter", "https://x.com"),
            ("wiki", "https://en.wikipedia.org"),
        ],
    )
    def test_bare_known_name_becomes_a_real_url(self, name, expected):
        """It used to become "https://youtube", which resolves to nothing."""
        assert build_website_url(name) == expected

    @pytest.mark.parametrize(
        "name,query,expected",
        [
            (
                "youtube",
                "MKBHD",
                "https://www.youtube.com/results?search_query=MKBHD",
            ),
            ("github", "ripgrep", "https://github.com/search?q=ripgrep"),
            (
                "reddit",
                "mechanical keyboards",
                "https://www.reddit.com/search/?q=mechanical+keyboards",
            ),
            (
                "wikipedia",
                "alan turing",
                "https://en.wikipedia.org/w/index.php?search=alan+turing",
            ),
            ("amazon", "usb c cable", "https://www.amazon.com/s?k=usb+c+cable"),
            ("stack overflow", "asyncio", "https://stackoverflow.com/search?q=asyncio"),
        ],
    )
    def test_query_uses_the_sites_own_search(self, name, query, expected):
        assert build_website_url(name, query) == expected

    def test_a_domain_resolves_to_its_registry_entry(self):
        """So "open youtube.com and look up X" still reaches YouTube's search."""
        assert resolve_website("https://www.youtube.com/").label == "YouTube"
        assert (
            build_website_url("youtube.com", "MKBHD")
            == "https://www.youtube.com/results?search_query=MKBHD"
        )

    def test_site_without_its_own_search_falls_back_to_google(self):
        url = build_website_url("claude", "context windows")
        assert url.startswith("https://www.google.com/search?q=site%3Aclaude.ai")

    def test_unregistered_domain_is_passed_through(self):
        assert build_website_url("hackernews.org") == "https://hackernews.org"

    def test_urls_are_never_left_unresolvable(self):
        """Every branch has to end at something a browser can actually load."""
        for name in ("youtube", "pinterest", "example.com", "https://example.com"):
            assert build_website_url(name).startswith("https://")


class TestBrowserSkill:
    @pytest.mark.asyncio
    async def test_bare_site_name_opens_the_site(self, opened):
        result = await BrowserSkill().execute(
            make_task("open_website", website="youtube")
        )
        assert opened == ["https://www.youtube.com"]
        assert "YouTube" in result

    @pytest.mark.asyncio
    async def test_site_and_query_open_one_tab_on_the_sites_results(self, opened):
        await BrowserSkill().execute(
            make_task("open_website", website="youtube", query="MKBHD")
        )
        assert opened == ["https://www.youtube.com/results?search_query=MKBHD"]

    @pytest.mark.asyncio
    async def test_the_extractors_key_for_a_query_is_understood_too(self, opened):
        await BrowserSkill().execute(
            make_task("open_website", website="youtube", search_query="MKBHD")
        )
        assert opened == ["https://www.youtube.com/results?search_query=MKBHD"]

    @pytest.mark.asyncio
    async def test_a_query_alone_is_still_a_web_search(self, opened):
        await BrowserSkill().execute(make_task("open_website", query="ai news"))
        assert opened == ["https://www.google.com/search?q=ai%20news"]

    @pytest.mark.asyncio
    async def test_neither_parameter_is_an_error(self):
        with pytest.raises(ValueError):
            await BrowserSkill().execute(make_task("open_website"))


class TestApplicationSkillDefersToTheBrowser:
    @pytest.mark.asyncio
    async def test_a_website_name_never_reaches_the_start_menu(
        self, opened, start_menu
    ):
        """The reported bug, end to end: the app is installed and still loses."""
        start_menu("YouTube Music")
        result = await ApplicationSkill().execute(
            make_task("open_application", application="youtube", query="MKBHD")
        )
        assert opened == ["https://www.youtube.com/results?search_query=MKBHD"]
        assert "YouTube" in result

    @pytest.mark.asyncio
    async def test_an_app_that_shares_its_name_with_a_site_stays_an_app(
        self, opened, start_menu
    ):
        """Claude, ChatGPT and WhatsApp ship real desktop apps."""
        start_menu("Claude")
        for name in ("claude", "chatgpt", "whatsapp", "spotify"):
            assert name not in ApplicationSkill.WEBSITE_FIRST_NAMES
        assert opened == []

    @pytest.mark.asyncio
    async def test_closing_is_not_redirected_to_the_browser(self, opened):
        """Only "open" means the site; "close youtube" is still about a program."""
        with pytest.raises(RuntimeError):
            await ApplicationSkill().execute(
                make_task("close_application", application="youtube")
            )
        assert opened == []


class TestRuleBasedFallbackAgrees:
    """The 3B local model fails often enough that this path is load-bearing."""

    @pytest.fixture
    def detector(self):
        instance = IntentDetector.__new__(IntentDetector)
        instance.llm = None
        instance.confidence_threshold = 0.75
        return instance

    def classify(self, detector, utterance):
        return detector._fallback(utterance, STTParser.parse(utterance))[0]

    def test_the_reported_utterance(self, detector):
        result = self.classify(detector, "open youtube in chrome and look up MKBHD")
        assert result.intent == "open_website"
        assert result.entities["website"] == "youtube"
        assert result.entities["query"] == "mkbhd"
        assert "application" not in result.entities

    @pytest.mark.parametrize(
        "utterance,website",
        [
            ("open youtube", "youtube"),
            ("open gmail", "gmail"),
            ("go to reddit", "reddit"),
            ("open google maps", "google maps"),
            ("visit wikipedia", "wikipedia"),
            ("pull up amazon", "amazon"),
        ],
    )
    def test_known_sites_are_websites(self, detector, utterance, website):
        result = self.classify(detector, utterance)
        assert result.intent == "open_website"
        assert result.entities["website"] == website

    @pytest.mark.parametrize(
        "utterance,application",
        [
            ("open chrome", "chrome"),
            ("open spotify", "spotify"),
            ("open notepad", "notepad"),
            ("open claude", "claude"),
            ("open whatsapp", "whatsapp"),
            ("open google chrome", "google chrome"),
            ("open visual studio code", "visual studio code"),
        ],
    )
    def test_installed_programs_are_applications(
        self, detector, utterance, application
    ):
        result = self.classify(detector, utterance)
        assert result.intent == "open_application"
        assert result.entities["application"] == application

    def test_a_site_name_inside_an_app_name_is_not_a_site(self, detector):
        """"google chrome" must not be shortened to "google"."""
        result = self.classify(detector, "open google chrome")
        assert result.intent == "open_application"

    def test_no_phantom_query_from_the_word_google(self, detector):
        """The extractor's search pattern fires on "google"; it is ignored."""
        assert "query" not in self.classify(detector, "open google maps").entities


class TestThePromptTeachesTheDistinction:
    """The LLM path and the fallback have to agree on what these intents mean."""

    @pytest.fixture
    def prompt(self):
        instance = IntentDetector.__new__(IntentDetector)
        instance.llm = None
        instance.confidence_threshold = 0.75
        return instance._system_prompt()

    def test_both_intents_have_an_entity_specification(self, prompt):
        assert 'For "open_application", entities must be:' in prompt
        assert 'For "open_website", entities must be:' in prompt
        assert '"website"' in prompt and '"query"' in prompt

    def test_the_reported_utterance_is_a_worked_example(self, prompt):
        assert "open youtube in chrome and look up MKBHD" in prompt.lower() or (
            "Open youtube in chrome and look up MKBHD" in prompt
        )
        assert '{"website": "youtube", "query": "MKBHD"}' in prompt

    def test_a_named_browser_is_not_a_second_intent(self, prompt):
        assert "in chrome" in prompt


class TestSiteSearchCoalescing:
    """Regression: "open youtube in chrome and look up MKBHD".

    qwen2.5:3b reliably splits this into open_website + search_web. Executed
    as two intents it opens a blank youtube.com AND runs a web research pass
    on "MKBHD" — the user gets neither the video search they asked for nor a
    single coherent action. The detector folds the pair back together.
    """

    @staticmethod
    def _detected(intent, entities):
        from intelligence.intent_detector import DetectedIntent

        return DetectedIntent(
            intent=intent, confidence=0.98, entities=entities, raw_utterance="x"
        )

    def _coalesce(self, pairs):
        from intelligence.intent_detector import IntentDetector

        detector = IntentDetector.__new__(IntentDetector)
        return detector._coalesce_site_search(
            [self._detected(i, e) for i, e in pairs]
        )

    def test_open_site_plus_search_becomes_one_in_site_search(self):
        out = self._coalesce(
            [("open_website", {"website": "youtube"}), ("search_web", {"query": "MKBHD"})]
        )

        assert len(out) == 1
        assert out[0].intent == "open_website"
        assert out[0].entities == {"website": "youtube", "query": "MKBHD"}

    def test_web_lookup_is_folded_the_same_way(self):
        out = self._coalesce(
            [("open_website", {"website": "reddit"}), ("web_lookup", {"query": "keyboards"})]
        )
        assert len(out) == 1
        assert out[0].entities["query"] == "keyboards"

    def test_a_site_without_its_own_search_is_left_alone(self):
        """A Google `site:` query is a worse answer than doing both things."""
        out = self._coalesce(
            [("open_website", {"website": "claude"}), ("search_web", {"query": "rust"})]
        )
        assert len(out) == 2

    def test_a_lone_web_lookup_is_untouched(self):
        out = self._coalesce([("web_lookup", {"query": "who won the election"})])
        assert len(out) == 1
        assert out[0].intent == "web_lookup"

    def test_an_unrelated_pair_is_not_merged(self):
        out = self._coalesce(
            [("open_website", {"website": "youtube"}), ("system_control", {"action": "up"})]
        )
        assert len(out) == 2

    def test_an_existing_query_is_not_overwritten(self):
        out = self._coalesce(
            [
                ("open_website", {"website": "youtube", "query": "already here"}),
                ("search_web", {"query": "something else"}),
            ]
        )
        assert len(out) == 2
        assert out[0].entities["query"] == "already here"

    def test_opening_an_app_then_searching_is_still_two_actions(self):
        """"open chrome and search for cats" really is two things."""
        out = self._coalesce(
            [("open_application", {"application": "chrome"}), ("search_web", {"query": "cats"})]
        )
        assert len(out) == 2
