"""
tests/test_web_search_parsing.py – SERP Parsing Tests
======================================================
Covers WebSkill's search-engine parsers against saved HTML, so the thing that
feeds the research loop is testable without a network.

Every one of these assertions exists because the live parsers once returned
something useless: DuckDuckGo parsed a page holding ten results into zero,
Bing handed back its own redirect stubs and its sponsored blocks, and both
happily emitted URLs that fetch_page could only turn into engine boilerplate.
The fixtures are trimmed captures of the real endpoints — see the comment at
the top of each one for what is verbatim and what is a hand-written edge case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.web_skill import (
    SearchResult,
    WebSkill,
    _batch_is_on_topic,
    _clean_result_url,
    _diversify,
    _is_engine_internal,
    _unwrap_bing,
    _unwrap_duckduckgo,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(encoding="utf-8"), "html.parser")


@pytest.fixture()
def skill() -> WebSkill:
    return WebSkill()


@pytest.fixture()
def ddg_results(skill: WebSkill) -> list[SearchResult]:
    return skill._parse_duckduckgo(load("duckduckgo_f1.html"), 20)


@pytest.fixture()
def bing_results(skill: WebSkill) -> list[SearchResult]:
    return skill._parse_bing(load("bing_f1.html"), 20)


# ── DuckDuckGo ────────────────────────────────────────────────────────────


def test_duckduckgo_returns_every_organic_result(ddg_results):
    """The regression: a page with this many results used to parse to zero.

    It also used to parse each result twice, because the selector listed both
    ``.results_links`` and its own ``.result__body`` child — so max_results
    silently halved the real yield.
    """
    assert len(ddg_results) == 7
    assert len({r.url for r in ddg_results}) == len(ddg_results)


def test_duckduckgo_unwraps_protocol_relative_redirect(ddg_results):
    """``//duckduckgo.com/l/?uddg=`` has no scheme, so the old
    ``startswith("http")`` gate rejected every single result."""
    assert ddg_results[0].url == (
        "https://en.wikipedia.org/wiki/2024_Formula_One_World_Championship"
    )


def test_duckduckgo_keeps_titles_and_snippets(ddg_results):
    first = ddg_results[0]
    assert first.title == "2024 Formula One World Championship - Wikipedia"
    assert "Formula" in first.snippet
    assert all(r.title for r in ddg_results)


def test_duckduckgo_unquotes_the_target_exactly_once():
    """parse_qs already decodes; the old code unquoted a second time, which
    turned a target's literal ``%25`` into a stray ``%`` sequence."""
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%2520b&rut=x"
    assert _clean_result_url(href) == "https://example.com/a%20b"


def test_duckduckgo_drops_sponsored_rows(ddg_results):
    """DDG reuses the organic classes for ads and only adds ``result--ad``."""
    assert not any("Sponsored" in r.title for r in ddg_results)
    assert not any("spokeo" in r.url.lower() for r in ddg_results)


def test_duckduckgo_drops_wrapper_with_no_target(ddg_results):
    assert not any("duckduckgo.com" in r.url for r in ddg_results)
    assert not any("no uddg target" in r.title for r in ddg_results)


def test_duckduckgo_keeps_an_unwrapped_absolute_href(ddg_results):
    assert "https://www.autosport.com/f1/news/2024-championship/" in {
        r.url for r in ddg_results
    }


def test_duckduckgo_target_about_duckduckgo_survives():
    """The old filter tested ``"duckduckgo" not in url`` against the whole
    string, so a page *about* DuckDuckGo was indistinguishable from a wrapper.
    """
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FDuckDuckGo"
    assert _clean_result_url(href) == "https://en.wikipedia.org/wiki/DuckDuckGo"


def test_duckduckgo_respects_max_results(skill):
    assert len(skill._parse_duckduckgo(load("duckduckgo_f1.html"), 3)) == 3


# ── Bing ──────────────────────────────────────────────────────────────────


def test_bing_decodes_ck_redirects_to_real_destinations(bing_results):
    """No caller may ever see a bing.com/ck/a URL: fetch_page would retrieve
    the redirect stub instead of the article."""
    assert bing_results
    assert not any("bing.com" in r.url for r in bing_results)
    assert bing_results[0].url == "https://mail.google.com/mail/"


@pytest.mark.parametrize(
    "payload, expected",
    [
        # Live payloads, chosen so all three padding cases are covered:
        # len % 4 == 3 (one "=" restored), == 2 (two), and == 0 (none).
        ("aHR0cHM6Ly9tYWlsLmdvb2dsZS5jb20vbWFpbC8", "https://mail.google.com/mail/"),
        (
            "aHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL2xvZ2luP3NlcnZpY2U9bWFpbA",
            "https://accounts.google.com/login?service=mail",
        ),
        ("aHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL0xvZ2lu", "https://accounts.google.com/Login"),
    ],
)
def test_bing_restores_stripped_base64_padding(payload, expected):
    url = f"https://www.bing.com/ck/a?!&&p=abc&ptn=3&u=a1{payload}&ntb=1"
    assert _unwrap_bing(url) == expected
    assert _clean_result_url(url) == expected


def test_bing_payload_prefix_is_stripped():
    """Bing prefixes the base64 with a literal ``a1``. Decoding without
    removing it shifts the alphabet and yields bytes that are not a URL."""
    import base64
    import binascii

    payload = "aHR0cHM6Ly9leGFtcGxlLmNvbS8"
    naive = "a1" + payload
    try:
        decoded = base64.urlsafe_b64decode(naive + "=" * (-len(naive) % 4))
    except binascii.Error:
        decoded = b""
    assert not decoded.startswith(b"https://")

    assert (
        _unwrap_bing(f"https://www.bing.com/ck/a?!&&p=abc&u=a1{payload}&ntb=1")
        == "https://example.com/"
    )


def test_bing_drops_undecodable_redirects(bing_results):
    """Better to lose the row than to return a bing.com URL."""
    assert not any("no u parameter" in r.title for r in bing_results)
    assert _clean_result_url("https://www.bing.com/ck/a?!&&p=nopayload&ntb=1") == ""


def test_bing_excludes_ads(bing_results):
    """``.b_algo`` matches sponsored blocks too — they sit inside the ``b_ad``
    container Bing's own SERP script scans for. Selecting on ``.b_algo`` alone
    is how a Formula 1 query came back as Spokeo people-search listings."""
    assert not any("Spokeo" in r.title for r in bing_results)
    assert not any("spokeo.com" in r.url for r in bing_results)


def test_bing_keeps_titles_and_snippets(bing_results):
    assert all(r.title for r in bing_results)
    assert any(r.snippet for r in bing_results)
    assert all(r.source == "bing" for r in bing_results)


# ── Google ────────────────────────────────────────────────────────────────


def test_google_unwraps_url_redirects(skill):
    results = skill._parse_google(load("google_asyncio.html"), 10)
    assert "https://docs.python.org/3/library/asyncio.html" in {r.url for r in results}
    assert "https://realpython.com/async-io-python/" in {r.url for r in results}


def test_google_drops_engine_internal_rows(skill):
    results = skill._parse_google(load("google_asyncio.html"), 10)
    assert not any("google" in r.url for r in results)


# ── URL sanity filter ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bing.com/ck/a?!&&p=0fb6&u=a1",
        "https://duckduckgo.com/l/?uddg=",
        "https://html.duckduckgo.com/html/?q=x",
        "https://www.google.com/url?q=",
        "https://webcache.googleusercontent.com/search?q=cache:example.com",
        "https://r.msn.com/redirect",
        "https://www.googleadservices.com/pagead/aclk?sa=L",
    ],
)
def test_engine_internal_urls_are_rejected(url):
    assert _is_engine_internal(url)
    assert _clean_result_url(url) == ""


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "javascript:void(0)",
        "mailto:someone@example.com",
        "/relative/path",
        "https://",
    ],
)
def test_unusable_urls_are_rejected(url):
    assert _clean_result_url(url) == ""


def test_ordinary_urls_survive():
    """The filter must not be so eager that it eats real pages: these are
    engine *names* in the path or host, not engine plumbing."""
    for url in (
        "https://en.wikipedia.org/wiki/DuckDuckGo",
        "https://news.example.com/2024/bing-ck-redirects-explained",
        "https://blog.google/products/search/",
    ):
        assert _clean_result_url(url) == url


def test_nested_wrapper_is_unwrapped():
    inner = "https%3A%2F%2Fexample.org%2Fstory"
    assert (
        _clean_result_url(f"/url?q=https://duckduckgo.com/l/?uddg={inner}")
        == "https://example.org/story"
    )


# ── Decoy SERP guard ──────────────────────────────────────────────────────


def test_bing_decoy_serp_is_rejected(bing_results):
    """Bing answers an unauthenticated scraper with results for a *different*
    query — this fixture is a live Formula 1 search that came back as Gmail
    pages. They parse perfectly, so only a relevance check catches them.
    """
    assert bing_results, "the decoy still parses; the guard is what drops it"
    assert not _batch_is_on_topic(
        "who won the 2024 formula 1 world championship", bing_results
    )


def test_on_topic_batch_is_kept(ddg_results):
    assert _batch_is_on_topic(
        "who won the 2024 formula 1 world championship", ddg_results
    )


def test_guard_matches_whole_words_only():
    """"worldwide" must not satisfy "world" — that substring hit is exactly
    what let the Gmail decoy through the first version of this guard."""
    decoy = [
        SearchResult(
            title="Gmail - Wikipedia",
            url="https://en.wikipedia.org/wiki/Gmail",
            snippet="The largest email service worldwide, with 1.8 billion users.",
            source="bing",
        )
    ]
    assert not _batch_is_on_topic("2024 formula world championship", decoy)


def test_guard_abstains_when_the_query_has_no_content_words():
    """A query of nothing but short function words gives the guard nothing to
    match on, so it must let the batch through rather than delete it."""
    results = [SearchResult("t", "https://example.com/", "s", "web")]
    assert _batch_is_on_topic("who is it", results)


# ── Merge and ordering ────────────────────────────────────────────────────


def at(domain: str, path: str = "/") -> SearchResult:
    return SearchResult(f"{domain} page", f"https://{domain}{path}", "", "web")


def test_diversify_puts_one_page_per_domain_first():
    """DeepResearchSkill keeps a single page per domain for the whole run, so
    five Wikipedia URLs at the front of the list is a one-source answer."""
    merged = [
        at("en.wikipedia.org", "/a"),
        at("en.wikipedia.org", "/b"),
        at("en.wikipedia.org", "/c"),
        at("bbc.co.uk"),
        at("autosport.com"),
    ]
    ordered = _diversify(merged, 3)
    assert [r.url for r in ordered] == [
        "https://en.wikipedia.org/a",
        "https://bbc.co.uk/",
        "https://autosport.com/",
    ]


def test_diversify_keeps_the_extras_behind_the_first_of_each_domain():
    merged = [at("a.com", "/1"), at("a.com", "/2"), at("b.com")]
    assert [r.url for r in _diversify(merged, 10)] == [
        "https://a.com/1",
        "https://b.com/",
        "https://a.com/2",
    ]


def test_diversify_ignores_www_when_counting_domains():
    merged = [at("www.example.com", "/1"), at("example.com", "/2"), at("other.com")]
    ordered = _diversify(merged, 2)
    assert [r.url for r in ordered] == [
        "https://www.example.com/1",
        "https://other.com/",
    ]


@pytest.mark.anyio
async def test_search_merges_across_engines(monkeypatch, skill):
    """The old loop returned the first engine that produced anything, so one
    thin answer was the whole answer. Now a short batch is topped up."""
    batches = {
        "duckduckgo": [at("wikipedia.org")],
        "bing": [at("bbc.co.uk"), at("wikipedia.org")],
        "google": [at("autosport.com")],
    }

    async def fake(engine, query, max_results):
        return batches[engine]

    monkeypatch.setattr(skill, "_search_engine", fake)

    results = await skill.search("2024 formula 1 champion", max_results=5)
    assert [r.url for r in results] == [
        "https://wikipedia.org/",
        "https://bbc.co.uk/",
        "https://autosport.com/",
    ]


@pytest.mark.anyio
async def test_search_stops_once_it_has_enough_domains(monkeypatch, skill):
    called: list[str] = []

    async def fake(engine, query, max_results):
        called.append(engine)
        return [at("a.com"), at("b.com")]

    monkeypatch.setattr(skill, "_search_engine", fake)

    await skill.search("something", max_results=2)
    assert called == ["duckduckgo"]


@pytest.mark.anyio
async def test_search_survives_a_dead_engine(monkeypatch, skill):
    """A raising engine must not end the search — that resilience is the one
    good part of the original loop."""

    async def fake(engine, query, max_results):
        if engine == "duckduckgo":
            raise RuntimeError("throttled")
        return [at("bbc.co.uk")]

    monkeypatch.setattr(skill, "_search_engine", fake)

    results = await skill.search("something", max_results=5)
    assert [r.url for r in results] == ["https://bbc.co.uk/"]


@pytest.mark.anyio
async def test_duckduckgo_202_is_skipped(monkeypatch, skill):
    """202 is DuckDuckGo's bot-challenge page, not an empty result set."""
    import httpx

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def get(self, url, **kwargs):
            self.calls += 1
            return httpx.Response(202, text="<html>anomaly</html>")

    client = FakeClient()
    monkeypatch.setattr(skill, "DDG_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(skill, "_get_client", lambda: _wrap(client))

    assert await skill._search_engine("duckduckgo", "anything", 5) == []
    assert client.calls == 1


@pytest.mark.anyio
async def test_duckduckgo_202_blocks_later_subqueries(monkeypatch, skill):
    """The research loop runs several sub-queries; once the challenge page has
    appeared, each of the rest would otherwise spend a round trip being told
    202 again. One request, then straight on to the next engine."""
    import httpx

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def get(self, url, **kwargs):
            self.calls += 1
            return httpx.Response(202, text="<html>anomaly</html>")

    client = FakeClient()
    monkeypatch.setattr(skill, "DDG_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(skill, "_get_client", lambda: _wrap(client))

    for _ in range(4):
        assert await skill._search_engine("duckduckgo", "anything", 5) == []

    assert client.calls == 1


async def _wrap(value):
    return value


@pytest.fixture()
def anyio_backend():
    return "asyncio"


class TestTopicCoverageGuard:
    """Regression: the assistant cited python.org as its source on the GIL.

    Two compounding bugs. A four-character floor in _query_tokens deleted
    "gil" — the only word that made the question specific — leaving {python}.
    The guard then accepted any batch where *one* result matched *one* token,
    so Bing's decoy SERP of generic Python pages sailed through and the
    research loop attached [1][2][3] to sources that never mention the GIL.
    """

    @staticmethod
    def _result(title, url="https://example.com/x", snippet=""):
        from skills.web_skill import SearchResult

        return SearchResult(title=title, url=url, snippet=snippet, source="test")

    def test_short_acronyms_survive_tokenisation(self):
        from skills.web_skill import _query_tokens

        assert _query_tokens("what is the python GIL") == {"python", "gil"}

    def test_other_short_technical_terms_survive_too(self):
        from skills.web_skill import _query_tokens

        assert "api" in _query_tokens("how does the stripe API work")
        assert "sql" in _query_tokens("what is a SQL join")

    def test_question_words_are_still_discarded(self):
        from skills.web_skill import _query_tokens

        assert _query_tokens("what is the on a of") == set()

    def test_the_observed_bing_decoy_is_rejected(self):
        from skills.web_skill import _batch_is_on_topic

        decoys = [
            self._result("Welcome to Python.org", "https://www.python.org/"),
            self._result("Python Tutorial - W3Schools", "https://www.w3schools.com/python/"),
            self._result("Online Python Compiler", "https://www.programiz.com/x"),
        ]
        assert _batch_is_on_topic("what is the python GIL", decoys) is False

    def test_genuinely_relevant_results_are_kept(self):
        from skills.web_skill import _batch_is_on_topic

        real = [
            self._result(
                "What is the Python Global Interpreter Lock (GIL)",
                "https://www.geeksforgeeks.org/what-is-the-python-global-interpreter-lock/",
            ),
            self._result("What Is the Python GIL?", "https://realpython.com/python-gil/"),
        ]
        assert _batch_is_on_topic("what is the python GIL", real) is True

    def test_coverage_may_be_spread_across_several_results(self):
        """No single result has to match everything."""
        from skills.web_skill import _batch_is_on_topic

        spread = [
            self._result("The 2024 Formula season"),
            self._result("World championship standings"),
        ]
        assert _batch_is_on_topic("2024 formula world championship", spread) is True

    def test_an_untokenisable_query_is_not_used_to_reject(self):
        from skills.web_skill import _batch_is_on_topic

        assert _batch_is_on_topic("what is the", [self._result("Anything")]) is True
