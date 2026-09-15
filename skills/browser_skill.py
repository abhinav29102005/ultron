"""
skills/browser_skill.py – Driving a real browser
=================================================
"Open YouTube" was already possible: it shells out a URL and Chrome opens a
tab. What was not possible is anything *after* that -- clicking, typing,
reading a page back. This is that.

Playwright, not Selenium. Two reasons that matter here specifically:

  * it auto-waits. A voice assistant clicking a button that has not rendered
    yet fails in a way the user cannot diagnose, and Playwright's actionability
    checks remove nearly all of that class of failure without explicit sleeps;
  * it can attach to the user's own Chrome over CDP, which is the difference
    between "log in again in a throwaway browser" and "do this in my Gmail".

Two modes, and the distinction is the whole design:

  * **attached** (``BROWSER_ATTACH=true``): connects to a Chrome the user
    started with ``--remote-debugging-port``. Their cookies, their sessions,
    their tabs. This is what "do it in *my* browser" means, and it is why
    every acting tool here is confirmed with the user first.
  * **owned** (the default): Playwright launches its own Chromium. Nothing is
    logged in, which is safe but cannot touch the user's accounts.

The browser is started lazily on first use and kept alive for the session.
Launching Chromium costs a second or two, which is worth paying once and not
per tool call.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from config.logging_config import get_logger
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.browser")

#: Page text returned to the model in one call.
MAX_PAGE_CHARS = 6_000

#: Per-action ceiling. Playwright's default is 30s, which is a long time to
#: leave a user listening to silence.
ACTION_TIMEOUT_MS = 15_000

#: Where an attached Chrome is expected to be listening.
DEFAULT_CDP_PORT = 9222

_INSTALL_HINT = (
    "Browser control needs Playwright. Install it with: "
    "pip install playwright && python -m playwright install chromium"
)

_ATTACH_HINT = (
    "I couldn't attach to your Chrome. Start it with remote debugging first: "
    "close Chrome, then run it with --remote-debugging-port=9222."
)


class BrowserSession:
    """One lazily-started browser, shared for the life of the process.

    Deliberately a singleton per process rather than per task. Every tool call
    would otherwise pay the launch cost, and worse, a page navigated by one
    call would be gone by the next -- making "open the page, then click the
    button" impossible, which is the entire point of having these tools.
    """

    def __init__(self, *, attach: bool = False, port: int = DEFAULT_CDP_PORT) -> None:
        self._attach = attach
        self._port = port
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._lock = asyncio.Lock()

    @property
    def started(self) -> bool:
        return self._page is not None

    async def page(self) -> Any:
        """The current page, starting the browser on first use."""
        async with self._lock:
            if self._page is not None and not self._page.is_closed():
                return self._page

            if self._playwright is None:
                try:
                    from playwright.async_api import async_playwright
                except ImportError as exc:
                    raise RuntimeError(_INSTALL_HINT) from exc

                self._playwright = await async_playwright().start()

            self._browser = await self._connect()

            # Reuse a tab the user already has open when attached; a new tab
            # in their own window is less surprising than a new window.
            contexts = self._browser.contexts
            context = contexts[0] if contexts else await self._browser.new_context()
            pages = context.pages
            self._page = pages[0] if pages else await context.new_page()
            self._page.set_default_timeout(ACTION_TIMEOUT_MS)

            return self._page

    async def _connect(self) -> Any:
        if self._browser is not None and self._browser.is_connected():
            return self._browser

        if self._attach:
            try:
                return await self._playwright.chromium.connect_over_cdp(
                    f"http://localhost:{self._port}"
                )
            except Exception as exc:
                raise RuntimeError(_ATTACH_HINT) from exc

        # Headful first: the user asked to watch ULTRON use the browser, and a
        # window they can see is also a window they can take over.
        try:
            return await self._playwright.chromium.launch(headless=False)
        except Exception as exc:
            logger.info(f"Headful browser unavailable ({exc}); trying headless.")

        # Headful Chromium needs a real interactive desktop session and fails
        # with "spawn UNKNOWN" without one -- from a service, a scheduled task,
        # or any non-interactive context. ULTRON does start from an autostart
        # entry, so this is a real case rather than a theoretical one. Every
        # browser tool still works headless; only the window is missing, and
        # losing the whole capability over that would be the worse trade.
        try:
            return await self._playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError(f"{_INSTALL_HINT} ({exc})") from exc

    async def close(self) -> None:
        """Shut down cleanly. Never closes a browser we merely attached to."""
        try:
            if self._browser is not None and not self._attach:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception as exc:
            logger.debug(f"Browser shutdown was untidy: {exc}")
        finally:
            self._playwright = self._browser = self._page = None


#: One session per process; see BrowserSession's docstring.
_SESSION: BrowserSession | None = None


def get_session(settings: Any = None) -> BrowserSession:
    global _SESSION
    if _SESSION is None:
        _SESSION = BrowserSession(
            attach=bool(getattr(settings, "browser_attach", False)),
            port=int(getattr(settings, "browser_cdp_port", DEFAULT_CDP_PORT)),
        )
    return _SESSION


async def close_session() -> None:
    global _SESSION
    if _SESSION is not None:
        await _SESSION.close()
        _SESSION = None


class BrowserControlSkill(Skill):
    """Navigate, click, type and read in a real browser."""

    name = "BrowserControlSkill"
    description = "Drives a real browser: navigate, click, type, read the page."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        intent = task.intent
        params = task.parameters or {}

        try:
            session = get_session(getattr(self.container, "settings", None))
            page = await session.page()
        except RuntimeError as exc:
            return str(exc)
        except Exception as exc:
            logger.exception("Could not start the browser")
            return f"I couldn't start the browser: {exc}"

        try:
            if intent == "browser_open":
                return await self._open(page, params)
            if intent == "browser_click":
                return await self._click(page, params)
            if intent == "browser_type":
                return await self._type(page, params)
            if intent == "browser_read":
                return await self._read(page)
            if intent == "browser_screenshot":
                return await self._screenshot(page)
        except Exception as exc:
            # Playwright's own errors are long and full of selector internals.
            # The first line is the part a model can act on.
            first_line = str(exc).strip().splitlines()[0]
            logger.info(f"Browser action failed: {first_line}")
            return f"That didn't work in the browser: {first_line}"

        return f"BrowserControlSkill cannot handle intent: {intent}"

    # ── actions ───────────────────────────────────────────────────────────

    async def _open(self, page: Any, params: dict) -> str:
        url = str(params.get("url") or "").strip()
        if not url:
            return "Which page should I open?"

        # A spoken URL almost never includes the scheme.
        if not url.startswith(("http://", "https://", "file://")):
            url = f"https://{url}"

        await page.goto(url, wait_until="domcontentloaded")
        return f"Opened {page.url} — the page is titled '{await page.title()}'."

    async def _click(self, page: Any, params: dict) -> str:
        target = str(params.get("target") or "").strip()
        if not target:
            return "What should I click?"

        locator = self._locate(page, target)
        await locator.first.click()
        return f"Clicked '{target}'."

    async def _type(self, page: Any, params: dict) -> str:
        text = str(params.get("text") or "")
        if not text:
            return "What should I type?"

        target = str(params.get("target") or "").strip()

        if target:
            field = await self._locate_input(page, target)
            if field is None:
                return (
                    f"I couldn't find a field called '{target}' to type into. "
                    f"Read the page to see what is there."
                )
            await field.fill(text)
        else:
            # No field named: type into whatever has focus. This is what the
            # user means after "click the search box".
            await page.keyboard.type(text)

        if params.get("submit"):
            await page.keyboard.press("Enter")
            return f"Typed '{text}' and submitted."

        return f"Typed '{text}'."

    async def _read(self, page: Any) -> str:
        text = await page.inner_text("body")
        title = await page.title()

        truncated = len(text) > MAX_PAGE_CHARS
        if truncated:
            text = text[:MAX_PAGE_CHARS]

        header = f"{title} ({page.url})"
        if truncated:
            header += f" — first {MAX_PAGE_CHARS} characters"

        return f"{header}\n{text}"

    async def _screenshot(self, page: Any) -> str:
        """Save a picture of the page, and say where it is.

        ``browser_read`` returns text, which is enough to decide what to click
        and useless when the question is about layout or an image. The file is
        also something ``read_screen_text`` can OCR when a page renders its
        content into a canvas.
        """
        import tempfile
        from pathlib import Path

        target = Path(tempfile.gettempdir()) / "ULTRON-page.png"
        await page.screenshot(path=str(target), full_page=False)
        return f"Saved a picture of {page.url} to {target}."

    # ── finding things on the page ────────────────────────────────────────

    #: Tags fill() accepts. Anything else -- a form, a div, a heading that
    #: happens to carry the label -- makes fill() raise "Element is not an
    #: <input>", which is the failure this guards against.
    _FILLABLE = ("INPUT", "TEXTAREA", "SELECT")

    @classmethod
    async def _locate_input(cls, page: Any, target: str) -> Any:
        """The field named ``target``, or None when there is no fillable one.

        Each strategy is tried in turn and the first that yields something
        fillable wins. This cannot be expressed with ``.or_()``: that resolves
        in *document* order, so a <form> carrying the label "Search" beats the
        <textarea> further down the page, and fill() then rejects it. Trying
        them one at a time is what makes "prefer a real textbox" mean what it
        says.
        """
        if target.startswith(("#", ".", "//", "css=", "xpath=")):
            return page.locator(target).first

        candidates = (
            page.get_by_role("textbox", name=target, exact=False),
            page.get_by_role("searchbox", name=target, exact=False),
            page.get_by_role("combobox", name=target, exact=False),
            page.get_by_placeholder(target, exact=False),
            page.get_by_label(target, exact=False),
        )

        for locator in candidates:
            try:
                if not await locator.count():
                    continue
                first = locator.first
                tag = str(await first.evaluate("e => e.tagName") or "")
            except Exception:
                # A detached or cross-origin match: try the next strategy
                # rather than failing the whole action.
                continue

            if tag.upper().startswith(cls._FILLABLE) or "CONTENTEDITABLE" in tag.upper():
                return first

        return None

    @staticmethod
    def _locate(page: Any, target: str, *, for_input: bool = False) -> Any:
        """Find an element from the words a person would use for it.

        A spoken instruction names things the way a human sees them -- "the
        search box", "Sign in" -- never by CSS selector. Playwright's
        role-and-text engine is built for exactly that.

        ``for_input`` picks between two genuinely different chains, and the
        distinction was found the hard way: typing into "Search" on DuckDuckGo
        matched a *heading* named Search before it reached the input, and
        ``fill()`` rejects anything that is not a real form control. So a
        typing target is restricted to things that can hold text, while a
        click target stays broad -- a link or a bare text node is exactly what
        you want to click.

        A target that is obviously a selector is passed straight through: a
        model that has just read the page may well have produced one.
        """
        if target.startswith(("#", ".", "//", "css=", "xpath=")):
            return page.locator(target)

        # role=button/link first: it matches the accessible name, which is
        # what the user is reading off the screen, and it ignores decorative
        # text nodes that happen to contain the same words.
        return page.get_by_role(
            "button", name=target, exact=False
        ).or_(
            page.get_by_role("link", name=target, exact=False)
        ).or_(
            page.get_by_placeholder(target, exact=False)
        ).or_(
            page.get_by_label(target, exact=False)
        ).or_(
            page.get_by_text(target, exact=False)
        )
