"""
skills/research_skill.py – Iterative Multi-Source Research
===========================================================
Answers an informational question the way a research agent does: plan a few
focused sub-queries, search them all at once, *read the pages themselves*,
decide whether the material actually covers the question, and only then write
a single cited answer.

This replaces "open a Google tab and let the user do the reading" as the
default for informational intents. WebLookupSkill still exists and is still
correct for "open a search for me"; it is simply no longer what happens when
somebody asks a question and expects an answer.

Two things make the old path thin, and both are fixed here:

  * ``search_and_summarize`` fed the model search-result *snippets* only. A
    snippet is a sales pitch for a page, not its content, so the summary was
    a paraphrase of ad copy. This fetches the page bodies.
  * one search, one shot. A 3B model writes a much better answer from four
    angles on a question than from one, so the query is decomposed first and
    the round is repeated if the material has a hole in it.

Everything is budgeted, because the caller is a voice assistant and the model
is a local 3B running on the user's own CPU: a round cap, a wall-clock budget,
a per-page timeout, and a per-source character budget so the synthesis prompt
cannot outgrow the context window.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from intelligence.task import Task

from skills.base import Skill
from skills.web_skill import SearchResult, WebSkill, build_search_query

logger = logging.getLogger("research")


# ── Budgets ───────────────────────────────────────────────────────────────
#
# These are the fallbacks used when no Settings object is reachable (a skill
# constructed bare in a test, or a container without settings). config/settings
# carries the same numbers as the tunable copy.

DEFAULT_MAX_ROUNDS = 2
DEFAULT_MAX_SOURCES = 5
DEFAULT_TIME_BUDGET_SECONDS = 45.0
DEFAULT_CHARS_PER_SOURCE = 2500

#: One slow site must not eat the whole run, so each page gets its own ceiling
#: well below the wall-clock budget.
PER_PAGE_TIMEOUT_SECONDS = 8.0

#: Planning and assessment are optimisations — a fallback exists for both — so
#: they get a short leash. Synthesis is the answer itself and gets a long one.
PLANNING_TIMEOUT_SECONDS = 12.0
SYNTHESIS_TIMEOUT_SECONDS = 40.0

#: Search results per sub-query. Deduplication throws most of these away, so
#: asking for a few more than needed is what keeps a round from coming back
#: with three copies of the same site.
RESULTS_PER_SUBQUERY = 4

#: Below this a "page" is a cookie wall, a JS shell or an error page. Keeping
#: it would spend the model's context on nothing.
MIN_USEFUL_EXCERPT_CHARS = 200

#: Sub-queries are typed into a search box, not spoken. Anything longer is the
#: model having ignored the instruction and written a sentence.
MAX_SUBQUERY_CHARS = 160
MAX_SUBQUERIES = 4


# ── Result types ──────────────────────────────────────────────────────────


@dataclass
class ResearchSource:
    """One page that was actually read, not merely listed."""

    index: int
    title: str
    url: str
    excerpt: str
    snippet: str = ""

    @property
    def domain(self) -> str:
        try:
            return urllib.parse.urlparse(self.url).netloc.replace("www.", "")
        except Exception:
            return self.url

    @property
    def label(self) -> str:
        """A title if the page had one, the domain if it did not."""
        return (self.title or "").strip() or self.domain


@dataclass
class ResearchResult:
    """The finished piece of research.

    Structured rather than a bare string so callers can render it differently
    — the console wants clickable URLs, a spoken reply wants neither URLs nor
    ``[1]`` markers — and so tests can assert on the sources without parsing
    prose back out again.
    """

    query: str
    answer: str
    sources: list[ResearchSource] = field(default_factory=list)
    rounds: int = 0
    #: Set when the answer is not the full product: no network, no LLM, or the
    #: budget ran out. Callers can use it to explain themselves; it is never an
    #: exception, because a partial answer still beats a traceback.
    degraded: str | None = None

    def render(self) -> str:
        """The console form: the cited answer followed by its sources.

        Full URLs are kept here rather than bare domains because the whole
        complaint being answered is that the user wanted the reading done
        *and* wanted to see where it came from. ``spoken()`` is the form that
        drops them.
        """
        if not self.sources:
            return self.answer

        lines = [self.answer.strip(), "", "Sources:"]
        for source in self.sources:
            lines.append(f"[{source.index}] {source.label} — {source.url}")
        return "\n".join(lines)

    def spoken(self) -> str:
        """The same answer with the citation scaffolding removed.

        A URL read aloud is unlistenable and "[1]" is read as "one", which
        lands mid-sentence as a number that is not part of the answer.
        """
        text = re.sub(r"\s*\[\d+\]", "", self.answer).strip()
        if self.sources:
            count = len(self.sources)
            text += f" I read {count} source{'s' if count != 1 else ''} for that."
        return text

    def __str__(self) -> str:
        return self.render()


# ── Prompts ───────────────────────────────────────────────────────────────
#
# Deliberately terse. A 3B model follows a short instruction with one example
# far more reliably than a long one with none, and every token here is decode
# time the user spends waiting.

_PLAN_SYSTEM = (
    "You turn a question into web search queries.\n"
    "Reply with JSON only: {\"queries\": [\"...\", \"...\"]}\n"
    "Give 2 to 4 short keyword queries covering different angles of the "
    "question. No sentences, no explanations, no markdown."
)

_ASSESS_SYSTEM = (
    "You judge whether collected notes answer a question.\n"
    "Reply with JSON only: {\"covered\": true} if the notes answer it, or "
    "{\"covered\": false, \"queries\": [\"...\"]} with 1 to 3 short search "
    "queries for what is still missing. No explanations."
)

_SYNTHESIS_SYSTEM = (
    "You answer a question using only the numbered sources given to you.\n"
    "Write a direct answer in 3 to 6 sentences. Put a citation marker like "
    "[1] or [2] after each claim, matching the source number it came from.\n"
    "Use only what the sources say. If they do not answer the question, say "
    "so plainly. Do not list the sources at the end and do not add headings."
)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of an LLM reply.

    Small models wrap JSON in prose or a ```json fence even when told not to,
    and ``json_mode`` is only honoured by some providers. Grabbing the outer
    braces recovers the reply instead of discarding a usable plan over a
    formatting habit.
    """
    if not text:
        return None

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", candidate).strip()

    try:
        parsed = json.loads(candidate)
    except Exception:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None

    return parsed if isinstance(parsed, dict) else None


def _clean_queries(raw: Any, limit: int = MAX_SUBQUERIES) -> list[str]:
    """Keep only the entries that are usable as a search box input."""
    if not isinstance(raw, (list, tuple)):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, str):
            continue
        query = item.strip().strip('"').strip()
        if not query or len(query) > MAX_SUBQUERY_CHARS:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(query)
        if len(cleaned) >= limit:
            break

    return cleaned


class DeepResearcher:
    """The research loop itself, with no Task and no Skill in sight.

    Split out from the skill so it can be driven directly — by a test with two
    stubs, or later by anything else that wants a researched answer rather
    than a routed utterance.
    """

    def __init__(
        self,
        web: Any,
        llm: Any = None,
        *,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        max_sources: int = DEFAULT_MAX_SOURCES,
        time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
        chars_per_source: int = DEFAULT_CHARS_PER_SOURCE,
    ) -> None:
        self.web = web
        self.llm = llm
        self.max_rounds = max(1, int(max_rounds))
        self.max_sources = max(1, int(max_sources))
        self.time_budget_seconds = float(time_budget_seconds)
        self.chars_per_source = max(200, int(chars_per_source))

    # ── Budget helpers ────────────────────────────────────────────────

    def _remaining(self, deadline: float) -> float:
        return deadline - time.monotonic()

    # ── Step 1: plan ──────────────────────────────────────────────────

    def _fallback_queries(self, query: str) -> list[str]:
        """Decomposition without a model.

        The original wording is always kept first — it is what the user
        actually asked and is the single most likely query to hit the right
        page. The variants exist to pull in explanatory and recent coverage,
        which are the two angles a bare query most often misses.
        """
        base = query.strip()
        variants = [base]

        lowered = base.lower()
        if not lowered.startswith(("how ", "what ", "why ")):
            variants.append(f"what is {base}")
        variants.append(f"{base} explained")
        variants.append(f"{base} latest")

        return _clean_queries(variants, limit=3)

    async def _plan(self, query: str, deadline: float) -> list[str]:
        """Ask the model for sub-queries; never let it stop the run."""
        planned = await self._ask_json(
            _PLAN_SYSTEM,
            f"Question: {query}",
            deadline,
            PLANNING_TIMEOUT_SECONDS,
        )

        if planned:
            queries = _clean_queries(planned.get("queries"))
            if queries:
                # The user's own wording is a strong query and the model tends
                # to paraphrase it away. Putting it back costs one search and
                # protects against a plan that drifted off the question.
                if not any(q.lower() == query.lower() for q in queries):
                    queries.insert(0, query)
                return queries[:MAX_SUBQUERIES]

        return self._fallback_queries(query)

    # ── Step 2: gather ────────────────────────────────────────────────

    async def _search_all(
        self, queries: Sequence[str], deadline: float, enough: int = DEFAULT_MAX_SOURCES
    ) -> list[SearchResult]:
        """Search for the sub-queries, spending as few requests as will do.

        The primary query runs alone first, and the rest only run if it came
        back thin.

        Firing every sub-query at once is the obvious shape and it was the
        wrong one. DuckDuckGo -- currently the only engine returning usable
        results, with Bing serving decoy SERPs and Google answering 429 --
        tolerates roughly two or three requests before blocking for minutes.
        A four-way fan-out exhausted that budget inside the first round, so
        round two searched against a blocked engine and the run ended with
        "no sources reachable" on a question the very first search had
        already answered.

        Breadth here comes from *reading several pages*, not from issuing
        several searches: one query returns ten links across distinct
        domains, which is more than max_sources needs. The remaining
        sub-queries are a fallback for a genuinely thin first answer, and
        they still run concurrently when they are needed at all.
        """
        if self._remaining(deadline) <= 0 or not queries:
            return []

        async def one(sub_query: str) -> list[SearchResult]:
            try:
                return await asyncio.wait_for(
                    self.web.search(sub_query, max_results=RESULTS_PER_SUBQUERY),
                    timeout=max(1.0, min(PER_PAGE_TIMEOUT_SECONDS * 2,
                                         self._remaining(deadline))),
                )
            except Exception as exc:
                logger.debug(f"Search failed for '{sub_query}': {exc}")
                return []

        primary = await one(queries[0])

        # Distinct domains, not raw hits: ten pages from one site is not the
        # breadth the synthesis step needs, and should still pull in the
        # other sub-queries.
        domains = {self._domain_of(r.url) for r in primary if r.url}
        if len(domains) >= enough or self._remaining(deadline) <= 0:
            return list(primary)

        batches = await asyncio.gather(
            *(one(q) for q in queries[1:]), return_exceptions=True
        )
        batches = [primary, *batches]

        results: list[SearchResult] = []
        for batch in batches:
            if isinstance(batch, BaseException) or not batch:
                continue
            results.extend(batch)
        return results

    @staticmethod
    def _domain_of(url: str) -> str:
        try:
            return urllib.parse.urlparse(url).netloc.replace("www.", "").lower()
        except Exception:
            return url.lower()

    def _dedupe(
        self,
        results: Sequence[SearchResult],
        seen_urls: set[str],
        seen_domains: set[str],
    ) -> list[SearchResult]:
        """One page per URL, and one page per domain for the whole run.

        Domain-level deduplication is the part that matters: four sub-queries
        about the same topic will all surface the same Wikipedia article, and
        five excerpts from one site is a single-source answer wearing five
        citations.

        The persistent sets are read but not written. A candidate is only
        burned once it has actually been picked for fetching — otherwise a
        result the first round listed and never opened would be invisible to
        the second round, which is precisely when we need more material.
        """
        urls = set(seen_urls)
        domains = set(seen_domains)
        distinct: list[SearchResult] = []

        for result in results:
            url = (getattr(result, "url", "") or "").strip()
            if not url.startswith("http"):
                continue

            key = url.rstrip("/").lower()
            if key in urls:
                continue

            domain = self._domain_of(url)
            if not domain or domain in domains:
                continue

            urls.add(key)
            domains.add(domain)
            distinct.append(result)

        return distinct

    def _commit_seen(
        self,
        chosen: Sequence[SearchResult],
        seen_urls: set[str],
        seen_domains: set[str],
    ) -> None:
        for result in chosen:
            seen_urls.add((result.url or "").rstrip("/").lower())
            seen_domains.add(self._domain_of(result.url or ""))

    async def _fetch_all(
        self,
        candidates: Sequence[SearchResult],
        deadline: float,
        start_index: int,
    ) -> list[ResearchSource]:
        """Read the page bodies concurrently, tolerating dead ones.

        ``return_exceptions=True`` plus a per-page ``wait_for`` is the whole
        contract here: a 403, a parked domain or a site that never finishes
        its response drops out of the results instead of aborting the round.
        """
        if not candidates or self._remaining(deadline) <= 0:
            return []

        async def one(result: SearchResult) -> tuple[SearchResult, str]:
            timeout = min(PER_PAGE_TIMEOUT_SECONDS, self._remaining(deadline))
            if timeout <= 0:
                return result, ""
            text = await asyncio.wait_for(
                self.web.fetch_page(result.url, max_chars=self.chars_per_source),
                timeout=timeout,
            )
            return result, (text or "")

        outcomes = await asyncio.gather(
            *(one(c) for c in candidates), return_exceptions=True
        )

        sources: list[ResearchSource] = []
        index = start_index

        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                logger.debug(f"Skipping unreadable source: {outcome}")
                continue

            result, text = outcome
            excerpt = (text or "").strip()

            # A page that gave us nothing readable is worse than no page: it
            # takes a citation slot, and the model will duly cite it. Falling
            # back to the search snippet here was tempting and wrong — thin
            # snippet-only answers are the exact complaint this loop exists to
            # fix, so an unreadable page simply does not become a source.
            if len(excerpt) < MIN_USEFUL_EXCERPT_CHARS:
                logger.debug(f"Discarding unreadable page: {result.url}")
                continue

            sources.append(
                ResearchSource(
                    index=index,
                    title=(getattr(result, "title", "") or "").strip(),
                    url=result.url,
                    excerpt=excerpt[: self.chars_per_source],
                    snippet=(getattr(result, "snippet", "") or "").strip(),
                )
            )
            index += 1

        return sources

    # ── Step 3: assess ────────────────────────────────────────────────

    async def _assess(
        self, query: str, sources: Sequence[ResearchSource], deadline: float
    ) -> list[str]:
        """Decide whether another round is worth its latency.

        Returns the follow-up queries, or an empty list to stop. Without a
        usable judgement the deterministic rule is "only go again if the round
        came back thin", which is the case another round actually helps.
        """
        if not sources:
            return self._fallback_queries(query)

        notes = "\n".join(
            f"[{s.index}] {s.label}: {s.excerpt[:400]}" for s in sources
        )

        verdict = await self._ask_json(
            _ASSESS_SYSTEM,
            f"Question: {query}\n\nNotes:\n{notes}",
            deadline,
            PLANNING_TIMEOUT_SECONDS,
        )

        if verdict is not None:
            if verdict.get("covered") is True:
                return []
            follow_ups = _clean_queries(verdict.get("queries"), limit=3)
            if follow_ups:
                return follow_ups

        if len(sources) < max(2, self.max_sources // 2):
            return self._fallback_queries(query)

        return []

    # ── Step 4: synthesise ────────────────────────────────────────────

    def _build_context(self, sources: Sequence[ResearchSource]) -> str:
        """Chunk the excerpts to a fixed per-source budget.

        The budget is per source rather than a single overall cap so that one
        long page cannot crowd the others out of the prompt entirely — the
        answer would then cite four sources it never actually saw.
        """
        blocks = []
        for source in sources:
            excerpt = source.excerpt[: self.chars_per_source].strip()
            blocks.append(
                f"[{source.index}] {source.label} ({source.domain})\n{excerpt}"
            )
        return "\n\n".join(blocks)

    def _sources_only(self, query: str, sources: Sequence[ResearchSource]) -> str:
        """What to say when there is material but nothing to write it with."""
        lines = [f"Here is what I found on '{query}':"]
        for source in sources:
            gist = (source.snippet or source.excerpt)[:200].strip()
            lines.append(f"[{source.index}] {source.label} — {gist}")
        return "\n".join(lines)

    async def _synthesize(
        self, query: str, sources: Sequence[ResearchSource], deadline: float
    ) -> tuple[str, str | None]:
        """Return ``(answer, degradation_reason)``."""
        if self.llm is None:
            return self._sources_only(query, sources), "no language model available"

        context = self._build_context(sources)
        messages = [
            self.llm.build_system_message(_SYNTHESIS_SYSTEM),
            self.llm.build_user_message(f"Question: {query}\n\nSources:\n{context}"),
        ]

        try:
            # Synthesis is given its own allowance rather than whatever the
            # gathering rounds left behind: the budget exists to stop us
            # reading forever, not to truncate the answer we already paid for.
            response = await asyncio.wait_for(
                self.llm.complete(messages, max_tokens=512),
                timeout=SYNTHESIS_TIMEOUT_SECONDS,
            )
            answer = (getattr(response, "content", "") or "").strip()
        except Exception as exc:
            logger.warning(f"Synthesis failed: {exc}")
            return self._sources_only(query, sources), f"summary step failed ({exc})"

        if not answer:
            return self._sources_only(query, sources), "the model returned nothing"

        return answer, None

    # ── Shared LLM plumbing ───────────────────────────────────────────

    async def _ask_json(
        self,
        system: str,
        user: str,
        deadline: float,
        timeout: float,
    ) -> dict[str, Any] | None:
        """A JSON-mode completion that returns None instead of raising.

        Both callers have a deterministic fallback, so every failure mode —
        no LLM, a timeout, a refusal, prose instead of JSON — collapses to the
        same "None" and the loop carries on.
        """
        if self.llm is None:
            return None

        budget = min(timeout, self._remaining(deadline))
        if budget <= 0:
            return None

        try:
            response = await asyncio.wait_for(
                self.llm.complete(
                    [
                        self.llm.build_system_message(system),
                        self.llm.build_user_message(user),
                    ],
                    json_mode=True,
                    max_tokens=200,
                ),
                timeout=budget,
            )
        except Exception as exc:
            logger.debug(f"JSON step failed, falling back: {exc}")
            return None

        return _extract_json(getattr(response, "content", "") or "")

    # ── The loop ──────────────────────────────────────────────────────

    async def research(self, query: str) -> ResearchResult:
        """Plan, gather, assess, iterate, synthesise.

        Never raises: every failure becomes a ResearchResult carrying a plain
        explanation, because the caller speaks whatever comes back and
        "Error: ClientConnectorError" is not an answer.
        """
        query = (query or "").strip()
        if not query:
            return ResearchResult(
                query=query,
                answer="I need something to look into — what would you like me to research?",
                degraded="empty query",
            )

        deadline = time.monotonic() + self.time_budget_seconds

        seen_urls: set[str] = set()
        seen_domains: set[str] = set()
        sources: list[ResearchSource] = []
        rounds = 0

        try:
            queries = await self._plan(query, deadline)

            for _ in range(self.max_rounds):
                rounds += 1

                results = await self._search_all(
                    queries, deadline, enough=self.max_sources
                )
                candidates = self._dedupe(results, seen_urls, seen_domains)

                needed = self.max_sources - len(sources)
                if needed > 0 and candidates:
                    # Fetch a couple more than needed: some will 403 or time
                    # out, and finding that out after the round has closed
                    # means an answer built on three sources instead of five.
                    chosen = candidates[: needed + 2]
                    self._commit_seen(chosen, seen_urls, seen_domains)
                    fetched = await self._fetch_all(
                        chosen, deadline, start_index=len(sources) + 1
                    )
                    sources.extend(fetched[:needed])
                    # Indices are assigned during the fetch, before the slice,
                    # so they have to be renumbered to stay contiguous with
                    # the citation markers the model will be shown.
                    for position, source in enumerate(sources, start=1):
                        source.index = position

                if len(sources) >= self.max_sources:
                    break
                if self._remaining(deadline) <= 0:
                    break
                # Assessing on the final round buys nothing and costs a model
                # round-trip the user waits through before hearing anything.
                if rounds >= self.max_rounds:
                    break

                queries = await self._assess(query, sources, deadline)
                if not queries:
                    break

        except Exception as exc:
            # The loop is defensive at every step, so reaching here means
            # something genuinely unforeseen. Anything already gathered is
            # still worth answering from.
            logger.exception(f"Research loop failed for '{query}': {exc}")
            if not sources:
                return ResearchResult(
                    query=query,
                    answer=(
                        f"I ran into a problem researching '{query}' and could not "
                        "get an answer together."
                    ),
                    rounds=rounds,
                    degraded=str(exc),
                )

        if not sources:
            return ResearchResult(
                query=query,
                answer=(
                    f"I couldn't reach the web to research '{query}'. Check the "
                    "network connection and ask me again."
                ),
                rounds=rounds,
                degraded="no sources reachable",
            )

        answer, degraded = await self._synthesize(query, sources, deadline)

        return ResearchResult(
            query=query,
            answer=answer,
            sources=sources,
            rounds=rounds,
            degraded=degraded,
        )


class DeepResearchSkill(Skill):
    """
    Researches a question across several sites and answers it directly.

    This is now the default for ``web_lookup``, ``search_web`` and ``news``.
    The user's complaint was precise: they did not want a Chrome tab handed to
    them, they wanted the reading done and a curated answer back. Opening a tab
    is still the right response to "open a search for me", which is what
    WebLookupSkill remains for.
    """

    name = "DeepResearchSkill"
    description = (
        "Researches a question by searching the web from several angles, "
        "reading the pages it finds, and writing a single cited answer."
    )
    version = "1.0.0"
    enabled = True

    def _settings(self) -> Any:
        return getattr(self.container, "settings", None)

    def _budget(self, name: str, default: Any) -> Any:
        """Read a tunable from Settings, tolerating its absence.

        Skills are constructed with a bare container in tests and with a real
        one at runtime; neither is allowed to be the case that crashes.
        """
        settings = self._settings()
        if settings is None:
            return default
        value = getattr(settings, name, None)
        return default if value is None else value

    def _resolve_web(self, task: "Task") -> Any:
        """The router injects a shared WebSkill so its HTTP client — and its
        connection pool — is reused across turns. A private one is the
        fallback, not the intent."""
        web = None
        if getattr(task, "metadata", None):
            web = task.metadata.get("web_skill")
        if web is None:
            web = getattr(self.container, "web_skill", None)
        if web is None:
            web = WebSkill(self.container)
        return web

    def build_researcher(self, task: "Task") -> DeepResearcher:
        llm = None
        if getattr(task, "metadata", None):
            llm = task.metadata.get("llm")

        return DeepResearcher(
            web=self._resolve_web(task),
            llm=llm,
            max_rounds=self._budget("research_max_rounds", DEFAULT_MAX_ROUNDS),
            max_sources=self._budget("research_max_sources", DEFAULT_MAX_SOURCES),
            time_budget_seconds=self._budget(
                "research_time_budget_seconds", DEFAULT_TIME_BUDGET_SECONDS
            ),
            chars_per_source=self._budget(
                "research_chars_per_source", DEFAULT_CHARS_PER_SOURCE
            ),
        )

    async def execute(self, task: "Task") -> "str | ResearchResult":
        query = build_search_query(task)

        # Deliberately not a ValueError. The Executor turns exceptions into
        # "Error: Missing 'query' parameter.", which is spoken at the user
        # verbatim; a question is both friendlier and actionable.
        if not query:
            return "I didn't catch what you'd like me to look into. What should I research?"

        # The result object rather than render(): the Executor stringifies it
        # (so the screen still gets the full cited answer via __str__), but it
        # also keeps the object on the Task, which is what lets the assistant
        # ask it for spoken() instead of reading source URLs out loud.
        return await self.build_researcher(task).research(query)
