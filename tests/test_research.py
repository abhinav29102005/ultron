"""
tests/test_research.py – Deep Research Loop Tests
===================================================
Covers the multi-round research loop that replaced "open a Google tab and let
the user read it themselves" for informational questions.

Nothing here touches the network or Ollama. The two collaborators the loop has
— a WebSkill and an LLM — are both stubbed, which is the point: the loop's
whole job is to keep working when one of them misbehaves, and that is only
testable if both can be made to misbehave on demand.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence.router import TaskRouter
from intelligence.task import Task, TaskStatus
from skills.research_skill import (
    DeepResearcher,
    DeepResearchSkill,
    ResearchResult,
    ResearchSource,
    _clean_queries,
    _extract_json,
)
from skills.web_skill import SearchResult, WebLookupSkill


# ── Fixtures and doubles ──────────────────────────────────────────────────


def make_task(intent: str = "web_lookup", metadata=None, **parameters) -> Task:
    return Task(
        task_id="test-research",
        skill_name="test",
        intent=intent,
        parameters=parameters,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata=metadata if metadata is not None else {},
    )


def result_at(domain: str, title: str = "", path: str = "page") -> SearchResult:
    # `path` distinguishes several pages on the SAME domain, which is how
    # breadth-by-domain is told apart from breadth-by-hit-count.
    return SearchResult(
        title=title or f"{domain} article",
        url=f"https://{domain}/{path}",
        snippet=f"A snippet from {domain} that is long enough to be plausible.",
        source="web",
    )


class FakeWeb:
    """Stands in for WebSkill.

    ``batches`` is consumed one entry per ``search()`` call so a test can make
    the second round see different results from the first; once it runs out,
    ``default`` is returned forever.
    """

    def __init__(self, batches=None, default=None, pages=None, failing_urls=()):
        self._batches = list(batches or [])
        self._default = list(default if default is not None else [])
        self._pages = dict(pages or {})
        self._failing_urls = set(failing_urls)
        self.searches: list[str] = []
        self.fetches: list[str] = []

    async def search(self, query, max_results=5, engine=None):
        self.searches.append(query)
        if self._batches:
            return list(self._batches.pop(0))
        return list(self._default)

    async def fetch_page(self, url, max_chars=3000):
        self.fetches.append(url)
        if url in self._failing_urls:
            raise RuntimeError("403 Forbidden")
        body = self._pages.get(url, f"Readable body text for {url}. " * 40)
        return body[:max_chars]


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    """Stands in for BaseLLM, routed by which prompt it was handed.

    The loop makes three different kinds of call and each has its own failure
    behaviour, so the double has to be able to fail exactly one of them.
    """

    def __init__(self, plan=None, assess=None, synthesis="A synthesised answer [1].",
                 fail_on=()):
        self.replies = {
            "plan": plan if plan is not None else '{"queries": ["alpha", "beta"]}',
            "assess": assess if assess is not None else '{"covered": true}',
            "synthesis": synthesis,
        }
        self.fail_on = set(fail_on)
        self.calls: list[str] = []
        self.prompts: list[str] = []

    def build_system_message(self, content):
        return {"role": "system", "content": content}

    def build_user_message(self, content):
        return {"role": "user", "content": content}

    @staticmethod
    def _kind(system: str) -> str:
        # Order matters: the assessment prompt also asks for search queries.
        if "judge whether" in system:
            return "assess"
        if "search queries" in system:
            return "plan"
        return "synthesis"

    async def complete(self, messages, **kwargs):
        kind = self._kind(messages[0]["content"])
        self.calls.append(kind)
        self.prompts.append(messages[-1]["content"])
        if kind in self.fail_on:
            raise RuntimeError(f"{kind} step exploded")
        return FakeResponse(self.replies[kind])


# ── Helpers ───────────────────────────────────────────────────────────────


class TestJSONSalvage:
    def test_plain_json_is_parsed(self):
        assert _extract_json('{"queries": ["a"]}') == {"queries": ["a"]}

    def test_fenced_json_is_recovered(self):
        assert _extract_json('```json\n{"covered": true}\n```') == {"covered": True}

    def test_json_buried_in_prose_is_recovered(self):
        text = 'Sure! Here you go: {"queries": ["a", "b"]} Hope that helps.'
        assert _extract_json(text) == {"queries": ["a", "b"]}

    def test_junk_is_none_rather_than_an_exception(self):
        assert _extract_json("I'm afraid I can't do that") is None
        assert _extract_json("") is None

    def test_queries_are_filtered_and_deduplicated(self):
        raw = ["Mars rover", "mars rover", "", 42, "x" * 500, "Mars weather"]
        assert _clean_queries(raw) == ["Mars rover", "Mars weather"]


# ── The loop ──────────────────────────────────────────────────────────────


class TestHappyPath:
    async def test_pages_are_read_and_the_answer_is_synthesised(self):
        web = FakeWeb(default=[result_at("one.example"), result_at("two.example")])
        llm = FakeLLM(synthesis="Mars has a thin atmosphere [1] and two moons [2].")

        result = await DeepResearcher(web, llm, max_sources=2).research("mars facts")

        assert isinstance(result, ResearchResult)
        assert result.answer == "Mars has a thin atmosphere [1] and two moons [2]."
        assert result.degraded is None
        assert result.rounds == 1
        # The snippets alone were the old failure. Every source must have been
        # opened and read.
        assert web.fetches == [
            "https://one.example/page",
            "https://two.example/page",
        ]
        assert [s.index for s in result.sources] == [1, 2]

    async def test_the_planner_output_is_searched_when_the_first_query_is_thin(self):
        # One domain back, but five wanted: not enough, so the model's other
        # angles are worth spending requests on.
        web = FakeWeb(default=[result_at("one.example")])
        llm = FakeLLM(plan='{"queries": ["mars atmosphere", "mars moons"]}')

        await DeepResearcher(web, llm, max_sources=5).research("mars facts")

        # The user's own wording is re-inserted alongside the model's angles:
        # it is the single most likely query to hit the right page.
        assert "mars facts" in web.searches
        assert "mars atmosphere" in web.searches
        assert "mars moons" in web.searches

    async def test_a_good_first_query_does_not_spend_more_searches(self):
        """DuckDuckGo blocks after two or three requests, and it is currently
        the only engine returning usable results. A first search that already
        covers enough distinct domains must not burn that budget on the
        remaining sub-queries -- doing so left round two searching against a
        blocked engine and answering "no sources reachable"."""
        web = FakeWeb(
            default=[
                result_at("one.example"),
                result_at("two.example"),
                result_at("three.example"),
            ]
        )
        llm = FakeLLM(plan='{"queries": ["mars atmosphere", "mars moons"]}')

        await DeepResearcher(web, llm, max_sources=3).research("mars facts")

        assert web.searches == ["mars facts"]

    async def test_breadth_is_counted_in_domains_not_hits(self):
        """Ten pages from one site is not breadth; the other angles still run."""
        web = FakeWeb(
            default=[
                result_at("one.example", path="a"),
                result_at("one.example", path="b"),
                result_at("one.example", path="c"),
            ]
        )
        llm = FakeLLM(plan='{"queries": ["mars atmosphere"]}')

        await DeepResearcher(web, llm, max_sources=3).research("mars facts")

        assert "mars atmosphere" in web.searches

    async def test_render_carries_the_answer_and_its_sources(self):
        web = FakeWeb(default=[result_at("one.example", title="Mars Overview")])
        llm = FakeLLM(synthesis="Mars is cold [1].")

        rendered = (await DeepResearcher(web, llm, max_sources=1).research("mars")).render()

        assert rendered.startswith("Mars is cold [1].")
        assert "Sources:" in rendered
        assert "[1] Mars Overview — https://one.example/page" in rendered

    async def test_spoken_form_drops_the_citation_scaffolding(self):
        result = ResearchResult(
            query="mars",
            answer="Mars is cold [1] and dusty [2].",
            sources=[ResearchSource(1, "A", "https://a/x", "body")],
        )
        spoken = result.spoken()

        assert "[1]" not in spoken and "https" not in spoken
        assert spoken.startswith("Mars is cold and dusty.")

    async def test_the_same_site_is_only_read_once(self):
        # Four sub-queries all surfacing the same article is the normal case,
        # not the exception.
        duplicates = [result_at("one.example"), result_at("one.example"),
                      result_at("two.example")]
        web = FakeWeb(default=duplicates)

        result = await DeepResearcher(web, FakeLLM(), max_sources=5).research("mars")

        assert web.fetches.count("https://one.example/page") == 1
        assert len(result.sources) == 2


class TestDegradation:
    async def test_llm_planning_failure_falls_back_to_a_deterministic_plan(self):
        web = FakeWeb(default=[result_at("one.example")])
        llm = FakeLLM(fail_on=("plan",))

        result = await DeepResearcher(web, llm, max_sources=1).research("mars facts")

        # A dead planner must not become a dead lookup: the original query is
        # still searched and the answer is still synthesised.
        assert "mars facts" in web.searches
        assert result.answer == "A synthesised answer [1]."
        assert result.degraded is None

    async def test_a_source_that_refuses_to_load_is_skipped(self):
        web = FakeWeb(
            default=[result_at("dead.example"), result_at("live.example")],
            failing_urls={"https://dead.example/page"},
        )

        result = await DeepResearcher(web, FakeLLM(), max_sources=2).research("mars")

        assert [s.url for s in result.sources] == ["https://live.example/page"]
        assert result.answer == "A synthesised answer [1]."

    async def test_a_page_with_no_readable_body_is_not_given_a_citation_slot(self):
        # A cookie wall returns 200 and almost no text. Citing it would put a
        # source number in the answer that stands for nothing.
        web = FakeWeb(
            default=[result_at("wall.example"), result_at("real.example")],
            pages={"https://wall.example/page": "Accept cookies"},
        )

        result = await DeepResearcher(web, FakeLLM(), max_sources=2).research("mars")

        assert [s.url for s in result.sources] == ["https://real.example/page"]

    async def test_no_search_results_is_a_plain_sentence_not_a_crash(self):
        web = FakeWeb(default=[])

        result = await DeepResearcher(web, FakeLLM(), max_sources=3).research("mars")

        assert result.sources == []
        assert result.degraded == "no sources reachable"
        assert "couldn't reach the web" in result.answer
        assert "Error" not in result.answer

    async def test_a_search_that_raises_is_survivable(self):
        class ExplodingWeb(FakeWeb):
            async def search(self, query, max_results=5, engine=None):
                raise RuntimeError("network is down")

        result = await DeepResearcher(ExplodingWeb(), FakeLLM()).research("mars")

        assert result.degraded == "no sources reachable"
        assert "couldn't reach the web" in result.answer

    async def test_without_an_llm_the_sources_are_returned_rather_than_nothing(self):
        web = FakeWeb(default=[result_at("one.example", title="Mars Overview")])

        result = await DeepResearcher(web, llm=None, max_sources=1).research("mars")

        assert result.degraded == "no language model available"
        assert "Mars Overview" in result.answer
        assert len(result.sources) == 1

    async def test_synthesis_failure_still_returns_the_gathered_sources(self):
        web = FakeWeb(default=[result_at("one.example", title="Mars Overview")])
        llm = FakeLLM(fail_on=("synthesis",))

        result = await DeepResearcher(web, llm, max_sources=1).research("mars")

        assert result.degraded is not None
        assert "Mars Overview" in result.answer

    async def test_an_empty_query_asks_rather_than_raising(self):
        result = await DeepResearcher(FakeWeb(), FakeLLM()).research("   ")

        assert result.degraded == "empty query"
        assert "what would you like me to research" in result.answer.lower()

    async def test_an_exhausted_time_budget_ends_the_run_cleanly(self):
        web = FakeWeb(default=[result_at("one.example")])

        result = await DeepResearcher(
            web, FakeLLM(), time_budget_seconds=0
        ).research("mars")

        assert web.fetches == []
        assert result.degraded == "no sources reachable"


class TestIteration:
    async def test_a_second_round_runs_when_the_first_leaves_a_gap(self):
        web = FakeWeb(
            batches=[[result_at("one.example")]],
            default=[result_at("two.example")],
        )
        llm = FakeLLM(assess='{"covered": false, "queries": ["follow up"]}')

        result = await DeepResearcher(web, llm, max_rounds=2, max_sources=5).research("mars")

        assert result.rounds == 2
        assert "follow up" in web.searches
        assert len(result.sources) == 2

    async def test_the_round_cap_is_respected(self):
        # The assessor never admits the question is covered; only the cap can
        # stop the loop.
        web = FakeWeb(
            batches=[[result_at("one.example")], [result_at("two.example")],
                     [result_at("three.example")], [result_at("four.example")]],
            default=[],
        )
        llm = FakeLLM(assess='{"covered": false, "queries": ["again"]}')

        result = await DeepResearcher(web, llm, max_rounds=2, max_sources=9).research("mars")

        assert result.rounds == 2
        assert llm.calls.count("assess") == 1

    async def test_a_covered_verdict_stops_after_one_round(self):
        web = FakeWeb(default=[result_at("one.example")])
        llm = FakeLLM(assess='{"covered": true}')

        result = await DeepResearcher(web, llm, max_rounds=3, max_sources=9).research("mars")

        assert result.rounds == 1

    async def test_enough_sources_stops_the_loop_before_the_assessor_runs(self):
        web = FakeWeb(default=[result_at("one.example"), result_at("two.example")])
        llm = FakeLLM(assess='{"covered": false, "queries": ["again"]}')

        result = await DeepResearcher(web, llm, max_rounds=3, max_sources=2).research("mars")

        assert result.rounds == 1
        assert "assess" not in llm.calls


class TestSynthesisPrompt:
    async def test_page_bodies_reach_the_model_within_the_character_budget(self):
        web = FakeWeb(
            default=[result_at("one.example")],
            pages={"https://one.example/page": "X" * 10_000},
        )
        llm = FakeLLM()

        await DeepResearcher(web, llm, max_sources=1, chars_per_source=500).research("mars")

        synthesis_prompt = llm.prompts[-1]
        assert "XXXX" in synthesis_prompt          # the body, not just the snippet
        assert synthesis_prompt.count("X") <= 500  # and no more than budgeted


# ── The skill and its wiring ──────────────────────────────────────────────


class TestDeepResearchSkill:
    async def test_the_query_is_stripped_of_its_framing(self):
        web = FakeWeb(default=[result_at("one.example")])
        task = make_task(text="look up the mars rover", metadata={"web_skill": web})

        await DeepResearchSkill().execute(task)

        assert any("mars rover" in q for q in web.searches)
        assert not any(q.startswith("look up") for q in web.searches)

    async def test_it_shares_the_query_builder_with_the_tab_opening_skill(self):
        task = make_task(text="could you google the mars rover")
        assert WebLookupSkill()._build_query(task) == "the mars rover"

    async def test_a_missing_query_is_answered_not_raised(self):
        # The Executor speaks exceptions verbatim as "Error: ...", so this
        # path must never raise.
        answer = await DeepResearchSkill().execute(make_task())

        assert "research" in answer.lower()
        assert "Error" not in answer

    async def test_it_returns_a_rendered_answer_with_sources(self):
        web = FakeWeb(default=[result_at("one.example", title="Mars Overview")])
        llm = FakeLLM(synthesis="Mars is cold [1].")
        task = make_task(query="mars", metadata={"web_skill": web, "llm": llm})

        result = await DeepResearchSkill().execute(task)

        # The Executor stringifies whatever a skill returns, so this is the
        # text that actually reaches the screen.
        answer = str(result)
        assert "Mars is cold [1]." in answer
        assert "https://one.example/page" in answer

    async def test_it_returns_the_result_object_so_the_voice_can_differ(self):
        """The assistant speaks result.spoken() and displays str(result); that
        only works while execute hands back the object rather than its text."""
        web = FakeWeb(default=[result_at("one.example", title="Mars Overview")])
        llm = FakeLLM(synthesis="Mars is cold [1].")
        task = make_task(query="mars", metadata={"web_skill": web, "llm": llm})

        result = await DeepResearchSkill().execute(task)

        assert isinstance(result, ResearchResult)
        assert "[1]" not in result.spoken()
        assert "https://" not in result.spoken()

    def test_budgets_come_from_settings_when_a_container_has_them(self):
        container = SimpleNamespace(
            settings=SimpleNamespace(
                research_max_rounds=4,
                research_max_sources=7,
                research_time_budget_seconds=90,
                research_chars_per_source=1000,
            )
        )
        researcher = DeepResearchSkill(container).build_researcher(
            make_task(query="mars", metadata={"web_skill": FakeWeb()})
        )

        assert researcher.max_rounds == 4
        assert researcher.max_sources == 7
        assert researcher.time_budget_seconds == 90
        assert researcher.chars_per_source == 1000

    def test_budgets_fall_back_when_there_is_no_container(self):
        researcher = DeepResearchSkill().build_researcher(
            make_task(query="mars", metadata={"web_skill": FakeWeb()})
        )

        assert researcher.max_rounds == 2
        assert researcher.max_sources == 5


class TestRouting:
    def test_informational_intents_now_research_instead_of_opening_a_tab(self):
        table = TaskRouter.ROUTING_TABLE
        assert table["web_lookup"] is DeepResearchSkill
        assert table["search_web"] is DeepResearchSkill
        assert table["news"] is DeepResearchSkill

    async def test_the_router_injects_the_llm_and_the_shared_web_skill(self):
        web = FakeWeb()
        llm = FakeLLM()
        container = SimpleNamespace(llm=llm, web_skill=web, chat_skill=None)

        tasks = await TaskRouter(container).route([make_task("web_lookup", query="mars")])

        assert tasks[0].metadata["skill_class"] is DeepResearchSkill
        assert tasks[0].metadata["llm"] is llm
        assert tasks[0].metadata["web_skill"] is web

    def test_the_tab_opening_skill_is_still_available(self):
        # Kept deliberately: "open a search for me" still wants a Chrome tab.
        assert WebLookupSkill.enabled is True
