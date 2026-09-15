"""
Tests for skills/browser_skill.py and skills/desktop_skill.py – W3.

These drive the user's real machine, so the behaviour worth pinning is mostly
about restraint:

  * a keystroke tool that will send anything a model produces is a liability;
    only ordinary keys and shortcuts get through;
  * an attached browser is the user's own logged-in Chrome, and closing it
    because ULTRON is shutting down would take their tabs with it;
  * the browser session is shared across calls, or "open the page, then click
    the button" cannot work at all.

No test here launches a browser or sends a real keystroke.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from intelligence.task import Task, TaskStatus


def _task(intent: str, **params) -> Task:
    return Task(
        task_id="t1",
        skill_name="",
        intent=intent,
        parameters=params,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


# ── desktop ───────────────────────────────────────────────────────────────


class TestKeyValidation:
    """The allowlist is the safety property; everything else is convenience."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("ctrl+s", ["ctrl", "s"]),
            ("CTRL+S", ["ctrl", "s"]),
            ("ctrl+shift+p", ["ctrl", "shift", "p"]),
            ("alt+tab", ["alt", "tab"]),
            ("control+c", ["ctrl", "c"]),
            ("f5", ["f5"]),
            ("enter", ["enter"]),
            ("return", ["enter"]),
            ("win+d", ["win", "d"]),
        ],
    )
    def test_ordinary_shortcuts_are_accepted(self, raw, expected):
        from skills.desktop_skill import DesktopSkill

        assert DesktopSkill._normalise(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "rm -rf /",
            "ctrl+alt+notakey",
            "; shutdown now",
            "ctrl+<script>",
        ],
    )
    def test_anything_outside_the_allowlist_is_refused(self, raw):
        from skills.desktop_skill import DesktopSkill

        assert DesktopSkill._normalise(raw) is None

    @pytest.mark.asyncio
    async def test_a_refused_shortcut_explains_itself_and_sends_nothing(
        self, monkeypatch
    ):
        from skills import desktop_skill

        sent = []
        monkeypatch.setattr(desktop_skill, "_press", sent.append)

        out = await desktop_skill.DesktopSkill().execute(
            _task("press_keys", keys="ctrl+notakey")
        )

        assert sent == []
        assert "won't" in out.lower() or "only" in out.lower()

    @pytest.mark.asyncio
    async def test_a_valid_shortcut_is_sent(self, monkeypatch):
        from skills import desktop_skill

        sent = []
        monkeypatch.setattr(desktop_skill, "_press", sent.append)

        await desktop_skill.DesktopSkill().execute(_task("press_keys", keys="ctrl+s"))

        assert sent == [["ctrl", "s"]]


class TestFocusWindow:
    @pytest.mark.asyncio
    async def test_a_matched_window_is_reported(self, monkeypatch):
        from skills import desktop_skill

        monkeypatch.setattr(
            desktop_skill, "_focus", lambda q: "app.py - Visual Studio Code"
        )

        out = await desktop_skill.DesktopSkill().execute(
            _task("focus_window", title="code")
        )

        assert "Visual Studio Code" in out

    @pytest.mark.asyncio
    async def test_no_match_says_so_rather_than_claiming_success(self, monkeypatch):
        from skills import desktop_skill

        monkeypatch.setattr(desktop_skill, "_focus", lambda q: None)

        out = await desktop_skill.DesktopSkill().execute(
            _task("focus_window", title="excel")
        )

        assert "couldn't find" in out.lower()

    @pytest.mark.asyncio
    async def test_a_missing_title_asks(self, monkeypatch):
        from skills import desktop_skill

        out = await desktop_skill.DesktopSkill().execute(_task("focus_window"))
        assert "which" in out.lower()


# ── browser ───────────────────────────────────────────────────────────────


class TestBrowserSession:
    @pytest.mark.asyncio
    async def test_the_session_is_shared_across_calls(self):
        """Otherwise "open the page, then click the button" cannot work: the
        second call would get a fresh browser on a blank page."""
        from skills import browser_skill

        await browser_skill.close_session()
        first = browser_skill.get_session()
        second = browser_skill.get_session()

        assert first is second
        await browser_skill.close_session()

    @pytest.mark.asyncio
    async def test_an_attached_browser_is_never_closed_by_us(self):
        """It is the user's own Chrome. Closing it would take their tabs."""
        from skills.browser_skill import BrowserSession

        closed = []

        class Browser:
            def is_connected(self):
                return True

            async def close(self):
                closed.append(True)

        session = BrowserSession(attach=True)
        session._browser = Browser()

        await session.close()

        assert closed == [], "an attached browser must be left running"

    @pytest.mark.asyncio
    async def test_an_owned_browser_is_closed(self):
        from skills.browser_skill import BrowserSession

        closed = []

        class Browser:
            def is_connected(self):
                return True

            async def close(self):
                closed.append(True)

        session = BrowserSession(attach=False)
        session._browser = Browser()

        await session.close()

        assert closed == [True]


class TestBrowserActions:
    @pytest.fixture
    def page(self):
        class Keyboard:
            def __init__(self):
                self.typed = []
                self.pressed = []

            async def type(self, text):
                self.typed.append(text)

            async def press(self, key):
                self.pressed.append(key)

        class Locator:
            def __init__(self, sink, name):
                self._sink = sink
                self._name = name

            @property
            def first(self):
                return self

            async def count(self):
                return 1

            async def evaluate(self, _script):
                return "INPUT"

            async def click(self):
                self._sink.append(("click", self._name))

            async def fill(self, text):
                self._sink.append(("fill", self._name, text))

            def or_(self, other):
                return self

        class Page:
            def __init__(self):
                self.url = "https://example.com/"
                self.actions = []
                self.keyboard = Keyboard()
                self.goto_calls = []

            def is_closed(self):
                return False

            def set_default_timeout(self, ms):
                pass

            async def goto(self, url, wait_until=None):
                self.goto_calls.append(url)
                self.url = url

            async def title(self):
                return "Example Domain"

            async def inner_text(self, selector):
                return "Hello from the page"

            def locator(self, selector):
                return Locator(self.actions, selector)

            def get_by_role(self, role, name=None, exact=None):
                return Locator(self.actions, name)

            def get_by_placeholder(self, t, exact=None):
                return Locator(self.actions, t)

            def get_by_label(self, t, exact=None):
                return Locator(self.actions, t)

            def get_by_text(self, t, exact=None):
                return Locator(self.actions, t)

        return Page()

    @pytest.fixture
    def skill(self, page, monkeypatch):
        from skills import browser_skill

        class Session:
            async def page(self):
                return page

        monkeypatch.setattr(browser_skill, "get_session", lambda settings=None: Session())
        return browser_skill.BrowserControlSkill()

    @pytest.mark.asyncio
    async def test_a_bare_domain_gets_a_scheme(self, skill, page):
        """Spoken URLs never include https://."""
        await skill.execute(_task("browser_open", url="github.com"))
        assert page.goto_calls == ["https://github.com"]

    @pytest.mark.asyncio
    async def test_an_explicit_url_is_left_alone(self, skill, page):
        await skill.execute(_task("browser_open", url="http://localhost:3000"))
        assert page.goto_calls == ["http://localhost:3000"]

    @pytest.mark.asyncio
    async def test_clicking_names_the_target(self, skill, page):
        await skill.execute(_task("browser_click", target="Sign in"))
        assert ("click", "Sign in") in page.actions

    @pytest.mark.asyncio
    async def test_typing_into_a_named_field_fills_it(self, skill, page):
        await skill.execute(_task("browser_type", text="hello", target="Search"))
        assert ("fill", "Search", "hello") in page.actions

    @pytest.mark.asyncio
    async def test_typing_with_no_field_goes_to_the_keyboard(self, skill, page):
        await skill.execute(_task("browser_type", text="hello"))
        assert page.keyboard.typed == ["hello"]

    @pytest.mark.asyncio
    async def test_submit_presses_enter(self, skill, page):
        await skill.execute(_task("browser_type", text="cats", submit=True))
        assert page.keyboard.pressed == ["Enter"]

    @pytest.mark.asyncio
    async def test_reading_returns_the_page_text(self, skill):
        out = await skill.execute(_task("browser_read"))
        assert "Hello from the page" in out

    @pytest.mark.asyncio
    async def test_a_playwright_failure_is_reported_as_one_line(self, skill, page):
        """Playwright errors are dozens of lines of selector internals; the
        model only needs the part it can act on."""

        async def boom(url, wait_until=None):
            raise Exception("net::ERR_NAME_NOT_RESOLVED\n  at Frame.goto\n  ...many lines")

        page.goto = boom

        out = await skill.execute(_task("browser_open", url="nope.invalid"))

        assert "ERR_NAME_NOT_RESOLVED" in out
        assert "at Frame.goto" not in out


class TestSelectorPassthrough:
    def test_a_css_selector_is_used_directly(self):
        """A model that has just read the page may produce a real selector."""
        from skills.browser_skill import BrowserControlSkill

        used = []

        class Page:
            def locator(self, selector):
                used.append(selector)
                return "locator"

        assert BrowserControlSkill._locate(Page(), "#submit") == "locator"
        assert used == ["#submit"]

    def test_plain_words_do_not_go_to_the_css_engine(self):
        from skills.browser_skill import BrowserControlSkill

        class Page:
            def locator(self, selector):
                raise AssertionError("plain text must not be treated as a selector")

            def get_by_role(self, role, name=None, exact=None):
                return _Chain()

            def get_by_placeholder(self, t, exact=None):
                return _Chain()

            def get_by_label(self, t, exact=None):
                return _Chain()

            def get_by_text(self, t, exact=None):
                return _Chain()

        class _Chain:
            def or_(self, other):
                return self

        BrowserControlSkill._locate(Page(), "Sign in")


class TestHeadfulFallback:
    """A visible browser is the point, but an invisible one still works.

    Launching headful Chromium needs a real interactive desktop session. It
    fails with "spawn UNKNOWN" from a service, a scheduled task, or any
    non-interactive context -- and ULTRON does run from an autostart entry.
    Falling back to headless there keeps every browser tool working (the agent
    can still open, read, click and type); refusing to launch at all would
    lose the whole capability over a window nobody was going to look at.
    """

    @pytest.mark.asyncio
    async def test_headful_is_tried_first(self):
        from skills.browser_skill import BrowserSession

        attempts = []

        class Chromium:
            async def launch(self, headless):
                attempts.append(headless)
                return "browser"

        session = BrowserSession()
        session._playwright = type("P", (), {"chromium": Chromium()})()

        await session._connect()

        assert attempts == [False], "the user should get a visible browser when possible"

    @pytest.mark.asyncio
    async def test_a_headful_failure_falls_back_to_headless(self):
        from skills.browser_skill import BrowserSession

        attempts = []

        class Chromium:
            async def launch(self, headless):
                attempts.append(headless)
                if not headless:
                    raise Exception("BrowserType.launch: spawn UNKNOWN")
                return "headless browser"

        session = BrowserSession()
        session._playwright = type("P", (), {"chromium": Chromium()})()

        assert await session._connect() == "headless browser"
        assert attempts == [False, True]

    @pytest.mark.asyncio
    async def test_both_failing_reports_the_install_hint(self):
        from skills.browser_skill import BrowserSession

        class Chromium:
            async def launch(self, headless):
                raise Exception("no browser anywhere")

        session = BrowserSession()
        session._playwright = type("P", (), {"chromium": Chromium()})()

        with pytest.raises(RuntimeError, match="playwright install"):
            await session._connect()


class TestClickTargetsStayBroad:
    """Clicking and typing need different locators.

    A link or a bare text node is exactly what you want to click, so the click
    chain stays wide. The typing chain is the restricted one -- see
    TestInputResolutionOrder.
    """

    class _Page:
        def __init__(self):
            self.tried = []

        def _record(self, kind):
            self.tried.append(kind)
            return self

        def locator(self, selector):
            return self._record(f"css:{selector}")

        def get_by_role(self, role, name=None, exact=None):
            return self._record(f"role:{role}")

        def get_by_placeholder(self, t, exact=None):
            return self._record("placeholder")

        def get_by_label(self, t, exact=None):
            return self._record("label")

        def get_by_text(self, t, exact=None):
            return self._record("text")

        def or_(self, other):
            return self

    def test_a_click_target_matches_links_and_text(self):
        from skills.browser_skill import BrowserControlSkill

        page = self._Page()
        BrowserControlSkill._locate(page, "Learn more")

        assert "role:link" in page.tried
        assert "text" in page.tried


class TestInputResolutionOrder:
    """`.or_()` resolves in DOM order, not in the order you chained it.

    Found live on DuckDuckGo. Chaining role=textbox.or_(placeholder).or_(label)
    and taking `.first` does NOT mean "textbox if there is one" -- it means
    "whichever of those appears earliest in the document". get_by_label
    ("Search") matched a <form> sitting above the real <textarea>, so `.first`
    was the form and fill() refused it.

    So the typing target is resolved by trying each strategy in turn and
    keeping the first that yields something actually fillable, which is what
    "prefer a textbox" has to mean.
    """

    class _Locator:
        def __init__(self, count, tag):
            self._count = count
            self._tag = tag
            self.filled = None

        @property
        def first(self):
            return self

        async def count(self):
            return self._count

        async def evaluate(self, _script):
            return self._tag

        async def fill(self, text):
            self.filled = text

    class _Page:
        def __init__(self, by_strategy):
            self._by = by_strategy
            self.asked = []

        def _get(self, key):
            self.asked.append(key)
            return self._by.get(key, TestInputResolutionOrder._Locator(0, None))

        def locator(self, selector):
            return self._get(f"css:{selector}")

        def get_by_role(self, role, name=None, exact=None):
            return self._get(f"role:{role}")

        def get_by_placeholder(self, t, exact=None):
            return self._get("placeholder")

        def get_by_label(self, t, exact=None):
            return self._get("label")

        def get_by_text(self, t, exact=None):
            return self._get("text")

    @pytest.mark.asyncio
    async def test_a_fillable_textbox_wins_over_an_earlier_form(self):
        from skills.browser_skill import BrowserControlSkill

        textbox = self._Locator(1, "TEXTAREA")
        page = self._Page({"role:textbox": textbox, "label": self._Locator(6, "FORM")})

        found = await BrowserControlSkill._locate_input(page, "Search")

        assert found is textbox

    @pytest.mark.asyncio
    async def test_an_unfillable_match_is_skipped_for_a_later_fillable_one(self):
        from skills.browser_skill import BrowserControlSkill

        real = self._Locator(1, "INPUT")
        page = self._Page({"role:textbox": self._Locator(2, "DIV"), "placeholder": real})

        assert await BrowserControlSkill._locate_input(page, "Search") is real

    @pytest.mark.asyncio
    async def test_contenteditable_counts_as_fillable(self):
        from skills.browser_skill import BrowserControlSkill

        editable = self._Locator(1, "DIV[contenteditable]")
        page = self._Page({"role:textbox": editable})

        assert await BrowserControlSkill._locate_input(page, "Body") is editable

    @pytest.mark.asyncio
    async def test_nothing_fillable_returns_none(self):
        from skills.browser_skill import BrowserControlSkill

        page = self._Page({"label": self._Locator(3, "FORM")})

        assert await BrowserControlSkill._locate_input(page, "Nope") is None

    @pytest.mark.asyncio
    async def test_an_explicit_selector_is_used_without_probing(self):
        from skills.browser_skill import BrowserControlSkill

        target = self._Locator(1, "INPUT")
        page = self._Page({"css:#q": target})

        assert await BrowserControlSkill._locate_input(page, "#q") is target
        assert page.asked == ["css:#q"]
