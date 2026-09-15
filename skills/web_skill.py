"""
skills/web_skill.py – Live Web Access Skill
============================================
Performs real-time web search and content extraction.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

if TYPE_CHECKING:
    from intelligence.task import Task
from skills.base import Skill


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


#: Query words that carry no search value once the utterance is a query.
#:
#: Module level rather than a class attribute because two skills now need the
#: same answer to "what did the user actually want looked up" — WebLookupSkill,
#: which opens a tab, and DeepResearchSkill, which reads the web itself. Two
#: copies of this regex would drift, and the second copy would be the one that
#: forgets "could you".
LEADING_NOISE = re.compile(
    r"^(?:hey\s+)?(?:friday|jarvis)?[,\s]*"
    r"(?:can you\s+|could you\s+|please\s+|)"
    r"(?:go\s+)?(?:and\s+)?"
    r"(?:search(?:\s+the\s+web)?(?:\s+for)?|look\s+up|look\s+for|google|"
    r"web\s?search|find(?:\s+out)?(?:\s+about)?|tell me about)\s+",
    re.IGNORECASE,
)


def build_search_query(task: "Task") -> str:
    """Prefer the entity the detector pulled out; fall back to the words the
    user actually said, minus the 'search for' framing.

    The detector only fills in ``query`` when it is confident about the span,
    so the raw utterance is the common path in practice — stripping the framing
    is what stops "look up the mars rover" from being searched verbatim.
    """
    query = str(task.parameters.get("query") or "").strip()

    if not query:
        query = str(
            task.parameters.get("text")
            or task.parameters.get("raw_utterance")
            or (task.metadata or {}).get("raw_utterance")
            or ""
        ).strip()
        query = LEADING_NOISE.sub("", query).strip()

    return query


#: (host suffix, path prefix) pairs that are search-engine plumbing rather than
#: destinations. An empty path prefix bans the whole host.
#:
#: Matched on host *and* path, never as a bare substring of the URL. The old
#: code tested ``"duckduckgo" in url``, which threw away any article that
#: merely talked about DuckDuckGo — and, worse, threw away correctly unwrapped
#: targets because the wrapper's own host was still in the string it tested.
_ENGINE_INTERNAL: tuple[tuple[str, str], ...] = (
    ("duckduckgo.com", "/l/"),
    ("duckduckgo.com", "/y.js"),
    ("bing.com", "/ck/"),
    ("bing.com", "/aclick"),
    ("bing.com", "/aclk"),
    ("google.com", "/url"),
    ("google.com", "/aclk"),
    ("googleadservices.com", ""),
    ("googleusercontent.com", "/search"),
    ("webcache.googleusercontent.com", ""),
    ("r.msn.com", ""),
    # The scrape endpoints themselves: a result linking back to a SERP would
    # have fetch_page read a page of links instead of an article.
    ("html.duckduckgo.com", ""),
    ("lite.duckduckgo.com", ""),
)


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def _is_engine_internal(url: str) -> bool:
    """True when following ``url`` would land on a redirect stub or a SERP.

    ``fetch_page`` on one of these returns the engine's own boilerplate, which
    reads to the research loop as a source that had nothing to say.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return True

    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    path = parsed.path or "/"

    return any(
        _host_matches(host, suffix) and (not prefix or path.startswith(prefix))
        for suffix, prefix in _ENGINE_INTERNAL
    )


def _query_param(url: str, name: str) -> str:
    """Read one query parameter without ``parse_qs``'s plus-to-space rule.

    Bing hides the destination in base64 whose alphabet can legitimately
    contain ``+``; ``parse_qs`` would turn those into spaces and corrupt every
    URL it touched.
    """
    match = re.search(rf"[?&]{re.escape(name)}=([^&#]*)", url)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1))


def _unwrap_duckduckgo(url: str) -> str:
    """``//duckduckgo.com/l/?uddg=<target>&rut=...`` -> ``<target>``."""
    parsed = urllib.parse.urlparse(url)
    if not _host_matches(parsed.netloc.lower(), "duckduckgo.com"):
        return ""
    if not parsed.path.startswith("/l/"):
        return ""
    # Single unquote only. The previous code unquoted the already-decoded
    # parse_qs output a second time, which silently mangled any target
    # containing a literal percent sign.
    return _query_param(url, "uddg").strip()


def _unwrap_bing(url: str) -> str:
    """``bing.com/ck/a?...&u=a1<base64>`` -> the real destination.

    Bing prefixes the payload with ``a1`` and strips the base64 padding, so
    both have to be put back before decoding. Without this the research loop
    fetched Bing's redirect stub instead of the article, and every "successful"
    Bing result carried no text at all.
    """
    parsed = urllib.parse.urlparse(url)
    if not _host_matches(parsed.netloc.lower(), "bing.com"):
        return ""
    if not parsed.path.startswith("/ck/"):
        return ""

    payload = _query_param(url, "u")
    if payload.startswith("a1"):
        payload = payload[2:]
    if not payload:
        return ""

    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return ""

    return decoded.strip()


def _unwrap_google(url: str) -> str:
    """``/url?q=<target>`` and ``google.com/url?url=<target>`` -> ``<target>``."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host and "google." not in host:
        return ""
    if not parsed.path.startswith("/url"):
        return ""

    return (_query_param(url, "q") or _query_param(url, "url")).strip()


def _clean_result_url(href: str) -> str:
    """Turn a SERP href into a fetchable destination, or ``""`` if there is none.

    Every parser routes through this so the "is this a real page?" rule lives
    in one place. Callers may treat ``""`` as "drop this result".
    """
    url = (href or "").strip()
    if not url:
        return ""

    # DuckDuckGo emits protocol-relative wrappers ("//duckduckgo.com/l/?uddg=").
    # Testing ``startswith("http")`` before this rejected all ten results on a
    # page that had ten, which is the whole reason DDG parsed to nothing.
    if url.startswith("//"):
        url = "https:" + url

    # Bounded rather than ``while True``: a wrapper that unwraps to itself
    # would otherwise spin forever on a malformed SERP.
    for _ in range(3):
        for unwrap in (_unwrap_duckduckgo, _unwrap_bing, _unwrap_google):
            target = unwrap(url)
            if target and target != url:
                url = "https:" + target if target.startswith("//") else target
                break
        else:
            break

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    if _is_engine_internal(url):
        return ""

    return url


def _domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


#: Short function words that say nothing about *what* was searched for. Words
#: under four characters are dropped by length, so this only needs the longer
#: ones.
_QUERY_STOPWORDS = frozenset(
    {
        "what", "when", "where", "which", "whom", "whose", "that", "this",
        "these", "those", "with", "from", "into", "about", "there", "here",
        "have", "been", "were", "does", "will", "would", "could", "should",
        "your", "their", "them", "then", "than", "such", "some", "most",
        "much", "many", "more", "over", "under", "also", "just", "like",
        # Short words, which used to be excluded by a length floor instead.
        # See _query_tokens for why that floor had to go.
        "a", "an", "the", "is", "are", "was", "be", "am", "of", "in", "on",
        "at", "to", "for", "and", "or", "by", "it", "its", "as", "do", "did",
        "how", "why", "who", "can", "get", "me", "my", "i", "you", "we",
        "if", "so", "up", "out", "not", "new", "any", "all", "has", "had",
    }
)

#: Shortest token that can carry meaning. Two, not four: the distinctive word
#: in a technical question is very often a short acronym -- GIL, API, SQL,
#: CSS, JWT, GPU, F1 -- and a four-character floor silently deleted exactly
#: the term that made the question specific. Observed: "what is the python
#: GIL" reduced to the single token {python}, so Bing's decoy SERP of generic
#: Python pages passed the relevance guard and the assistant cited
#: python.org's homepage as its source on the GIL.
MIN_QUERY_TOKEN_CHARS = 2

#: Fraction of a query's distinctive words a batch must mention somewhere to
#: be believed. One shared word is not enough: "python" alone is satisfied by
#: any page about Python, which is precisely how the decoys got through.
MIN_TOPIC_COVERAGE = 0.6


def _query_tokens(query: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", query.lower())
        if len(word) >= MIN_QUERY_TOKEN_CHARS and word not in _QUERY_STOPWORDS
    }


def _batch_is_on_topic(query: str, results: Sequence["SearchResult"]) -> bool:
    """Reject a whole engine's answer when none of it mentions the question.

    Bing answers an unauthenticated scraper with a *decoy* SERP: it echoes the
    query in the page title and then lists results for something else entirely
    (a Formula 1 question came back as Gmail sign-in pages, then Ookla speed
    tests, then pizzerias in Madrid). Those parse perfectly and are worthless,
    and feeding them to the research loop is worse than feeding it nothing.

    Compared as whole words, not substrings — a decoy page about Gmail being
    "the largest email service worldwide" otherwise passed a Formula 1 query
    on the "world" inside "worldwide".

    The test is *coverage*, not a single hit. Requiring one shared word was
    too weak to catch the subtler decoy: asked "what is the python GIL", Bing
    returned python.org, the W3Schools Python tutorial and an online Python
    compiler. Every one of them matches "python", none of them mentions the
    GIL, and the research loop cited all three as its source on the GIL --
    fabricated citations, which are worse than no answer. Demanding that the
    batch collectively mention most of what made the question specific
    separates that from a genuinely relevant set.
    """
    tokens = _query_tokens(query)
    if not tokens or not results:
        return True

    covered: set[str] = set()
    for result in results:
        haystack = set(
            re.findall(r"[a-z0-9]+", f"{result.title} {result.snippet} {result.url}".lower())
        )
        covered |= tokens & haystack

    return (len(covered) / len(tokens)) >= MIN_TOPIC_COVERAGE


def _diversify(results: Sequence["SearchResult"], limit: int) -> list["SearchResult"]:
    """Put the first hit from each distinct domain first, then the rest.

    DeepResearchSkill keeps one page per domain for a whole run, so whatever
    is at the front of this list is what it actually reads. Ten Wikipedia URLs
    ahead of one news site is a single-source answer; this ordering makes the
    truncation to ``limit`` keep breadth instead of depth.
    """
    first_of_domain: list[SearchResult] = []
    remainder: list[SearchResult] = []
    seen_domains: set[str] = set()

    for result in results:
        domain = _domain_of(result.url)
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            first_of_domain.append(result)
        else:
            remainder.append(result)

    return (first_of_domain + remainder)[:limit]


class WebSkill(Skill):
    name = "WebSkill"
    description = "Performs live web search and extracts content from pages."
    version = "1.0.0"
    enabled = True

    # Search engine endpoints
    SEARCH_ENGINES = {
        "duckduckgo": "https://html.duckduckgo.com/html/?q={query}",
        "google": "https://www.google.com/search?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
    }

    # Default search engine
    DEFAULT_ENGINE = "duckduckgo"

    # Request timeout
    TIMEOUT = 10.0

    # User agent
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    #: Seconds to leave between two DuckDuckGo requests. See _pace_duckduckgo.
    DDG_MIN_INTERVAL = 1.5

    #: How long to stop asking DuckDuckGo after it answers with its challenge
    #: page. Measured: the block outlasts a whole research run — three requests
    #: 20 seconds apart still tripped it, and it then stayed tripped for over
    #: ten minutes. Anything longer than one run is equivalent; the point is
    #: that sub-queries 2..n skip straight to the next engine instead of each
    #: spending a round trip to be told 202 again.
    DDG_BLOCK_SECONDS = 180.0

    #: Wikimedia answers the browser user agent above with "403 Please respect
    #: our robot policy", and that policy is satisfied by identifying yourself
    #: with a contact URL — a name alone still gets the 403, the "+https://..."
    #: is the part they check for. Wikipedia is the top hit for most research
    #: queries, so losing it costs the loop its best source. Other sites
    #: (autosport.com, for one) do the reverse and 403 anything that is not a
    #: browser, which is why fetch_page keeps both and retries rather than
    #: picking a winner.
    FETCH_USER_AGENT = (
        "FridayAgent/1.0 (+https://github.com/MicrosoftStudentChapter/friday-agent) httpx"
    )

    def __init__(self, container: "Any" = None) -> None:
        super().__init__(container)
        self._client: Optional[httpx.AsyncClient] = None
        self._ddg_lock = asyncio.Lock()
        self._ddg_last_request = 0.0
        self._ddg_blocked_until = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.TIMEOUT,
                headers={"User-Agent": self.USER_AGENT},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _pace_duckduckgo(self) -> None:
        """Serialise DuckDuckGo requests and leave a gap between them.

        The html endpoint answers 202 with a bot-challenge page once it has
        seen a handful of requests, and then keeps answering 202 for minutes.
        DeepResearch fans every sub-query out with ``asyncio.gather``, which
        arrives as one burst — so the engine that parses best was also the one
        that never got a parseable page.

        Spacing does not buy much on its own (three requests twenty seconds
        apart still tripped it), but queueing instead of racing at least means
        the first sub-queries get served rather than all of them colliding.
        We do not attempt the challenge.
        """
        async with self._ddg_lock:
            gap = self.DDG_MIN_INTERVAL - (time.monotonic() - self._ddg_last_request)
            if gap > 0:
                await asyncio.sleep(gap)
            self._ddg_last_request = time.monotonic()

    async def _search_engine(
        self, engine: str, query: str, max_results: int
    ) -> list[SearchResult]:
        """One engine's answer, or ``[]`` for any reason at all."""
        template = self.SEARCH_ENGINES.get(engine)
        if not template:
            return []

        if engine == "duckduckgo":
            if time.monotonic() < self._ddg_blocked_until:
                return []
            await self._pace_duckduckgo()

        url = template.format(query=urllib.parse.quote(query))
        client = await self._get_client()
        response = await client.get(url)

        # 202 is DuckDuckGo's anomaly/challenge page, not a result set. Once
        # it appears every later sub-query gets the same answer, so remember it
        # and let them fall through to the next engine without the round trip.
        if engine == "duckduckgo" and response.status_code == 202:
            self._ddg_blocked_until = time.monotonic() + self.DDG_BLOCK_SECONDS
            return []

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        parser = {
            "duckduckgo": self._parse_duckduckgo,
            "bing": self._parse_bing,
            "google": self._parse_google,
        }.get(engine)
        if parser is None:
            return []

        results = parser(soup, max_results)

        if not _batch_is_on_topic(query, results):
            return []

        return results

    async def search(
        self,
        query: str,
        max_results: int = 5,
        engine: str = None,
    ) -> list[SearchResult]:
        """Search the web, merging what several engines return.

        The old loop returned the first engine that produced anything, which
        made a single flaky engine the whole answer: DuckDuckGo throttles, so
        in practice the caller got Bing's list or nothing. The research loop
        wants *distinct sites*, so we keep collecting until we have enough
        different domains, then stop — an engine that already gave us breadth
        costs the later engines nothing, and a broken one just contributes
        zero instead of ending the search.
        """
        engines = [engine] if engine else ["duckduckgo", "bing", "google"]

        merged: list[SearchResult] = []
        seen_urls: set[str] = set()
        seen_domains: set[str] = set()

        for eng in engines:
            try:
                batch = await self._search_engine(eng, query, max_results)
            except Exception:
                # A dead engine must not end the search; try the next one.
                continue

            for result in batch:
                key = result.url.rstrip("/").lower()
                if not key or key in seen_urls:
                    continue
                seen_urls.add(key)
                seen_domains.add(_domain_of(result.url))
                merged.append(result)

            if len(seen_domains) >= max_results:
                break

        return _diversify(merged, max_results)

    @staticmethod
    def _in_ad_block(node: Tag, ad_classes: Iterable[str]) -> bool:
        """Ads nest the organic markup inside an ad container, so the class has
        to be looked for on the ancestors, not just on the block itself."""
        wanted = set(ad_classes)
        for element in (node, *node.parents):
            if wanted & set(element.get("class") or []):
                return True
        return False

    #: DuckDuckGo reuses the organic classes for sponsored blocks and adds one
    #: of these; ``result--more`` is the "more results" footer, not a page.
    DDG_SKIP_CLASSES = frozenset(
        {"result--ad", "result--ad--small", "result--sponsored", "result--more",
         "result--no-result", "result--spelling"}
    )

    def _parse_duckduckgo(self, soup: BeautifulSoup, max_results: int) -> list[SearchResult]:
        """Parse html.duckduckgo.com.

        Two bugs lived here. The selector listed both ``.results_links`` (the
        outer container) and ``.result__body`` (its own child), so every result
        was collected twice and ``[:max_results]`` then halved the real yield.
        And the URL filter tested ``startswith("http")`` against a wrapper that
        is protocol-relative, then tested ``"duckduckgo" not in url`` against a
        string that still held the wrapper's host — so a page with ten good
        results parsed to zero.
        """
        results: list[SearchResult] = []

        for block in soup.select("div.result"):
            if self.DDG_SKIP_CLASSES & set(block.get("class") or []):
                continue

            link = block.select_one("a.result__a[href]") or block.select_one(
                "a.result__url[href]"
            )
            if link is None:
                continue

            url = _clean_result_url(link.get("href", ""))
            if not url:
                continue

            title_elem = block.select_one(".result__title, a.result__a")
            title = (title_elem.get_text(strip=True) if title_elem else "")[:120]

            snippet_elem = block.select_one(".result__snippet")
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

            results.append(
                SearchResult(title=title, url=url, snippet=snippet, source="web")
            )
            if len(results) >= max_results:
                break

        return results

    #: Read off Bing's own SERP script rather than guessed: it sets
    #: ``_G.adc = "b_ad"`` and its scroll-offset helper scans
    #: ``["#b_results ."+_G.adc, ".sb_adsWv2", ".ads", "#b_topw ."+_G.adc]``
    #: while testing class names for ``b_adTop``. ``.b_algo`` matches the
    #: markup *inside* those containers too, so selecting on it alone returns
    #: sponsored rows as results.
    BING_AD_CLASSES = frozenset({"b_ad", "b_adTop", "b_adBottom", "sb_adsWv2", "ads"})

    def _parse_bing(self, soup: BeautifulSoup, max_results: int) -> list[SearchResult]:
        results: list[SearchResult] = []

        for block in soup.select("li.b_algo"):
            if self._in_ad_block(block, self.BING_AD_CLASSES):
                continue

            link = block.select_one("h2 a[href]")
            if link is None:
                continue

            # Bing links every result through bing.com/ck/a. _clean_result_url
            # decodes it; when it cannot, the result is dropped rather than
            # handed on as a bing.com URL that fetch_page would turn into a
            # redirect stub.
            url = _clean_result_url(link.get("href", ""))
            if not url:
                continue

            snippet_elem = block.select_one(".b_caption p, .b_algoSlug, p")
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

            results.append(
                SearchResult(
                    title=link.get_text(strip=True)[:120],
                    url=url,
                    snippet=snippet,
                    source="bing",
                )
            )
            if len(results) >= max_results:
                break

        return results

    def _parse_google(self, soup: BeautifulSoup, max_results: int) -> list[SearchResult]:
        """Best effort only.

        Google answers this client with HTTP 429 and rotates its result
        container classes (``.g`` has not been reliable for years), so this is
        the last engine tried and is expected to contribute nothing most of the
        time. Anchoring on the ``h3`` heading inside an anchor is the one shape
        both the classic and the no-JavaScript markup still share.
        """
        results: list[SearchResult] = []
        seen: set[str] = set()

        for heading in soup.select("h3"):
            link = heading.find_parent("a", href=True)
            if link is None:
                container = heading.find_parent(["div", "li"])
                link = container.select_one("a[href]") if container else None
            if link is None:
                continue

            url = _clean_result_url(link.get("href", ""))
            if not url or url in seen:
                continue
            seen.add(url)

            snippet = ""
            container = heading.find_parent(["div", "li"])
            if container is not None:
                snippet_elem = container.select_one(
                    ".VwiC3b, .IsZvec, [data-sncf], .st, .s"
                )
                if snippet_elem is not None:
                    snippet = snippet_elem.get_text(strip=True)

            results.append(
                SearchResult(
                    title=heading.get_text(strip=True)[:120],
                    url=url,
                    snippet=snippet,
                    source="google",
                )
            )
            if len(results) >= max_results:
                break

        return results

    async def fetch_page(self, url: str, max_chars: int = 3000) -> str:
        """Fetch and extract readable text from a web page."""
        client = await self._get_client()
        response = await client.get(url)

        if response.status_code in (401, 403):
            response = await client.get(
                url, headers={"User-Agent": self.FETCH_USER_AGENT}
            )

        response.raise_for_status()

        # A PDF or an image decoded as text is thousands of characters of
        # binary noise, which the research loop would happily quote.
        content_type = response.headers.get("content-type", "")
        if content_type and "html" not in content_type.lower():
            if "xml" not in content_type.lower() and "text/plain" not in content_type.lower():
                return ""

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script/style elements
        for elem in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form"]):
            elem.decompose()

        # Prefer the article body when the page marks one; otherwise the text
        # is dominated by menus that survived the tag removal above.
        body = soup.select_one("article, main, [role=main]") or soup

        text = body.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        return text[:max_chars]

    async def search_and_summarize(
        self,
        query: str,
        max_results: int = 3,
        llm=None,
    ) -> str:
        """Search web and optionally summarize with LLM."""
        results = await self.search(query, max_results=max_results)

        if not results:
            return f"No results found for: {query}"

        # Build context from search results
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(f"{i}. {r.title}\n   {r.snippet}\n   Source: {r.url}")

        context = "\n\n".join(context_parts)

        if llm:
            # Use LLM to synthesize answer
            messages = [
                llm.build_system_message("""
You are a helpful assistant that answers questions using web search results.
Synthesize a concise, accurate answer from the provided search results.
Cite sources using [1], [2], etc. format.
Be direct and informative.
"""),
                llm.build_user_message(f"Question: {query}\n\nSearch Results:\n{context}"),
            ]
            response = await llm.complete(messages)
            return response.content

        # Fallback: return raw results
        return f"Search results for '{query}':\n\n" + "\n\n".join(
            f"{i}. {r.title}\n   {r.snippet}\n   {r.url}"
            for i, r in enumerate(results, 1)
        )

    async def execute(self, task: "Task") -> str:
        query = task.parameters.get("query")
        if not query:
            raise ValueError("Missing 'query' parameter.")

        # Get LLM from container if available
        llm = None
        if hasattr(task, "metadata") and task.metadata.get("llm"):
            llm = task.metadata["llm"]

        return await self.search_and_summarize(query, llm=llm)


class WebLookupSkill(Skill):
    """
    Answers a question that needs live information by *showing* the search.

    WebSkill scrapes and summarises silently, which is fine for a spoken answer
    but leaves the user with nothing to read or click. This skill opens the
    search in a real Chrome tab first — that is the behaviour the user asked
    for — and then, best effort, also speaks a short summary so the answer is
    not purely visual. A failed summary is not a failed lookup: the tab is
    already open, which was the point.
    """

    name = "WebLookupSkill"
    description = (
        "Looks a question up on the web by opening a Google search in a new "
        "Chrome tab, and speaks a short summary of what it finds."
    )
    version = "1.0.0"
    enabled = True

    #: Kept as a class attribute so existing callers that reach for
    #: ``WebLookupSkill.LEADING_NOISE`` keep working; the regex itself now
    #: lives at module scope and is shared with DeepResearchSkill.
    LEADING_NOISE = LEADING_NOISE

    SEARCH_URL = "https://www.google.com/search?q={q}"

    def _build_query(self, task: "Task") -> str:
        return build_search_query(task)

    async def execute(self, task: "Task") -> str:
        query = self._build_query(task)

        if not query:
            raise ValueError("Missing 'query' parameter.")

        # Imported here rather than at module scope: system_skills pulls in
        # WebSkill for the weather, so a top-level import would close the loop.
        from skills.system_skills import open_in_chrome

        url = self.SEARCH_URL.format(q=urllib.parse.quote(query))
        used_chrome, browser_message = open_in_chrome(url)

        opened = (
            f"I've opened a Chrome tab with the results for '{query}'."
            if used_chrome
            else browser_message
        )

        llm = None
        if getattr(task, "metadata", None):
            llm = task.metadata.get("llm")

        # Without an LLM to synthesise them, search_and_summarize returns the
        # raw scraped titles, which for "who won the election" reads back as an
        # unrelated Wikipedia headline. Better to say nothing than to speak a
        # wrong answer over a tab that already has the right one.
        if llm is None:
            return opened

        web = None
        if getattr(task, "metadata", None):
            web = task.metadata.get("web_skill")
        if web is None:
            web = WebSkill(self.container)

        # The tab is already open, so a scrape that gets rate-limited costs the
        # user nothing. Never let it turn the lookup into an error.
        try:
            summary = await web.search_and_summarize(query, max_results=3, llm=llm)
        except Exception:
            summary = ""

        summary = (summary or "").strip()

        if summary and not summary.startswith("No results found"):
            return f"{opened} {summary}"

        return opened