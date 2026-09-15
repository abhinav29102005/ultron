"""
Tests for intelligence/agent_loop.py – the tool-calling turn.

This is the replacement for one-shot intent classification. Instead of the
model labelling an utterance and a table picking one skill, the model is given
typed tools and calls them -- none, one, or several in sequence -- until it can
answer.

The behaviours pinned here are the ones that decide whether the loop is safe
to put in front of a voice assistant:

  * it stops (step budget, wall clock) -- a loop that can spin forever is a
    loop that hangs the microphone;
  * a broken tool call is reported back to the model, never raised -- a model
    that guesses a bad argument should get a chance to fix it;
  * destructive tools are confirmed with the user first;
  * an unavailable provider degrades to the old pipeline rather than failing.

No test here reaches a network or a real model. The LLM is a script.
"""

from __future__ import annotations

import pytest

from intelligence.agent_loop import AgentLoop, AgentResult
from llm.tools import ToolCall, ToolCallResponse, ToolsUnsupportedError


class ScriptedLLM:
    """Returns pre-baked responses in order, recording what it was sent."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    async def complete_with_tools(self, messages, tools, **kwargs):
        self.calls.append(list(messages))
        if not self._responses:
            return ToolCallResponse(content="(no more scripted responses)")
        return self._responses.pop(0)

    def build_system_message(self, content):
        return {"role": "system", "content": content}

    def build_user_message(self, content):
        return {"role": "user", "content": content}


class RecordingDispatcher:
    """Stands in for the router+executor, recording what got run."""

    def __init__(self, results=None, raises=None):
        self.ran: list[ToolCall] = []
        self._results = results or {}
        self._raises = raises or {}

    async def run(self, call: ToolCall) -> str:
        self.ran.append(call)
        if call.name in self._raises:
            raise self._raises[call.name]
        return self._results.get(call.name, f"{call.name} done")

    def is_known(self, name: str) -> bool:
        return name not in ("nonexistent_tool",)

    def needs_confirmation(self, name: str) -> bool:
        return name in ("write_file", "close_application")


def _call(name, **arguments):
    return ToolCall(id=f"call_{name}", name=name, arguments=arguments)


def _loop(llm, dispatcher, **kwargs):
    return AgentLoop(llm=llm, dispatcher=dispatcher, **kwargs)


class TestPlainAnswers:
    @pytest.mark.asyncio
    async def test_a_response_with_no_tool_calls_is_returned_as_is(self):
        llm = ScriptedLLM(ToolCallResponse(content="It's about four o'clock."))
        dispatcher = RecordingDispatcher()

        result = await _loop(llm, dispatcher).run("what time is it roughly")

        assert result.text == "It's about four o'clock."
        assert dispatcher.ran == []

    @pytest.mark.asyncio
    async def test_the_utterance_reaches_the_model(self):
        llm = ScriptedLLM(ToolCallResponse(content="ok"))
        await _loop(llm, RecordingDispatcher()).run("hello there")

        sent = llm.calls[0]
        assert any(m["role"] == "user" and "hello there" in m["content"] for m in sent)
        assert sent[0]["role"] == "system"


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_a_tool_is_run_and_its_result_returned_to_the_model(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("get_time")]),
            ToolCallResponse(content="It's 16:05."),
        )
        dispatcher = RecordingDispatcher(results={"get_time": "16:05"})

        result = await _loop(llm, dispatcher).run("what time is it")

        assert [c.name for c in dispatcher.ran] == ["get_time"]
        assert result.text == "It's 16:05."
        # The second model call must be able to see the tool's output.
        second = llm.calls[1]
        assert any(m.get("role") == "tool" and "16:05" in m["content"] for m in second)

    @pytest.mark.asyncio
    async def test_several_tools_run_in_sequence_across_rounds(self):
        """The compound case: look at the screen, then read the file it named.

        This is what one-shot classification could not do at all -- it had to
        pick a single intent and drop the rest of the request.
        """
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("get_active_window")]),
            ToolCallResponse(tool_calls=[_call("read_file", path="app.py")]),
            ToolCallResponse(content="Line 7 is missing a colon."),
        )
        dispatcher = RecordingDispatcher()

        result = await _loop(llm, dispatcher).run("fix the bug in my code")

        assert [c.name for c in dispatcher.ran] == ["get_active_window", "read_file"]
        assert result.text == "Line 7 is missing a colon."

    @pytest.mark.asyncio
    async def test_two_tools_in_one_response_both_run(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("get_time"), _call("get_date")]),
            ToolCallResponse(content="Monday, 16:05."),
        )
        dispatcher = RecordingDispatcher()

        await _loop(llm, dispatcher).run("what's the time and date")

        assert [c.name for c in dispatcher.ran] == ["get_time", "get_date"]

    @pytest.mark.asyncio
    async def test_the_tools_used_are_reported(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("get_time")]),
            ToolCallResponse(content="done"),
        )
        result = await _loop(llm, RecordingDispatcher()).run("time?")
        assert result.tools_used == ["get_time"]


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_an_unknown_tool_is_reported_back_instead_of_crashing(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("nonexistent_tool")]),
            ToolCallResponse(content="Sorry, I can't do that."),
        )
        dispatcher = RecordingDispatcher()

        result = await _loop(llm, dispatcher).run("do something impossible")

        assert dispatcher.ran == []
        assert result.text == "Sorry, I can't do that."
        assert any(
            m.get("role") == "tool" and "unknown" in m["content"].lower()
            for m in llm.calls[1]
        )

    @pytest.mark.asyncio
    async def test_a_tool_that_raises_feeds_the_error_back(self):
        """The model can often recover -- a bad path becomes a listing and a
        second attempt. Killing the turn removes that chance."""
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("read_file", path="/nope")]),
            ToolCallResponse(content="That file isn't there."),
        )
        dispatcher = RecordingDispatcher(raises={"read_file": OSError("boom")})

        result = await _loop(llm, dispatcher).run("read /nope")

        assert result.text == "That file isn't there."
        assert any("boom" in m.get("content", "") for m in llm.calls[1])

    @pytest.mark.asyncio
    async def test_a_provider_without_tool_support_signals_the_caller(self):
        """So the assistant can fall back to the classifier pipeline."""

        class NoTools(ScriptedLLM):
            async def complete_with_tools(self, messages, tools, **kwargs):
                raise ToolsUnsupportedError("qwen2.5:3b cannot call tools")

        with pytest.raises(ToolsUnsupportedError):
            await _loop(NoTools(), RecordingDispatcher()).run("anything")


class TestBudgets:
    @pytest.mark.asyncio
    async def test_the_step_budget_stops_an_endless_tool_loop(self):
        """A model that keeps calling tools must not hold the mic forever."""
        forever = [ToolCallResponse(tool_calls=[_call("get_time")]) for _ in range(50)]
        llm = ScriptedLLM(*forever)
        dispatcher = RecordingDispatcher()

        result = await _loop(llm, dispatcher, max_steps=3).run("spin")

        assert len(dispatcher.ran) <= 3
        assert result.text, "the user must still be told something"
        assert result.hit_budget is True

    @pytest.mark.asyncio
    async def test_a_normal_turn_does_not_report_hitting_the_budget(self):
        llm = ScriptedLLM(ToolCallResponse(content="fine"))
        result = await _loop(llm, RecordingDispatcher()).run("hi")
        assert result.hit_budget is False


class TestConfirmation:
    @pytest.mark.asyncio
    async def test_a_destructive_tool_is_not_run_without_consent(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("write_file", path="a.py", content="x")]),
            ToolCallResponse(content="Okay, I left it alone."),
        )
        dispatcher = RecordingDispatcher()

        asked = []

        async def refuse(prompt: str) -> bool:
            asked.append(prompt)
            return False

        result = await _loop(llm, dispatcher, confirm=refuse).run("patch it")

        assert dispatcher.ran == []
        assert asked, "the user should have been asked"
        assert result.text == "Okay, I left it alone."

    @pytest.mark.asyncio
    async def test_a_confirmed_tool_runs(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("write_file", path="a.py", content="x")]),
            ToolCallResponse(content="Patched."),
        )
        dispatcher = RecordingDispatcher()

        async def accept(prompt: str) -> bool:
            return True

        await _loop(llm, dispatcher, confirm=accept).run("patch it")

        assert [c.name for c in dispatcher.ran] == ["write_file"]

    @pytest.mark.asyncio
    async def test_without_a_confirmer_destructive_tools_are_declined(self):
        """A missing confirmation channel must fail closed, never open."""
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("write_file", path="a.py", content="x")]),
            ToolCallResponse(content="I need you to confirm that."),
        )
        dispatcher = RecordingDispatcher()

        await _loop(llm, dispatcher, confirm=None).run("patch it")

        assert dispatcher.ran == []

    @pytest.mark.asyncio
    async def test_a_read_only_tool_is_never_confirmed(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("get_time")]),
            ToolCallResponse(content="16:05"),
        )
        asked = []

        async def watcher(prompt):
            asked.append(prompt)
            return True

        await _loop(llm, RecordingDispatcher(), confirm=watcher).run("time?")

        assert asked == []


class TestResultShape:
    def test_agent_result_carries_what_the_assistant_needs(self):
        result = AgentResult(text="hi", tools_used=["get_time"], steps=1, hit_budget=False)
        assert result.text == "hi"
        assert result.tools_used == ["get_time"]
        assert result.steps == 1


class TestRepeatedCalls:
    """A model that repeats one call verbatim is stuck, not working.

    Found live: asked to fix a file whose path it had been given, the model
    called list_directory six times in a row with the same arguments, burned
    all twelve steps and delivered nothing. Every repeat returns the identical
    result, so the transcript grows without gaining information and the model
    has no reason to change course.

    Breaking the tie is cheap: after a couple of identical calls, answer with
    a nudge instead of running the tool again. The step is still spent, so a
    determined loop still terminates on the budget -- but the model gets told
    what is happening and usually recovers within the same turn.
    """

    @pytest.mark.asyncio
    async def test_a_repeated_call_is_not_executed_again(self):
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("list_directory", path="C:/x")]),
            ToolCallResponse(tool_calls=[_call("list_directory", path="C:/x")]),
            ToolCallResponse(tool_calls=[_call("list_directory", path="C:/x")]),
            ToolCallResponse(content="Right, let me try something else."),
        )
        dispatcher = RecordingDispatcher()

        await _loop(llm, dispatcher).run("fix it")

        assert len(dispatcher.ran) == 2, "the third identical call should be short-circuited"

    @pytest.mark.asyncio
    async def test_the_model_is_told_it_is_repeating(self):
        llm = ScriptedLLM(
            *[ToolCallResponse(tool_calls=[_call("list_directory", path="C:/x")])] * 3,
            ToolCallResponse(content="ok"),
        )

        await _loop(llm, RecordingDispatcher()).run("fix it")

        nudges = [
            m for m in llm.calls[-1]
            if m.get("role") == "tool" and "already" in m.get("content", "").lower()
        ]
        assert nudges, "the model should be told it is repeating itself"

    @pytest.mark.asyncio
    async def test_the_same_tool_with_different_arguments_is_fine(self):
        """Reading two files is not a loop."""
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("read_file", path="a.py")]),
            ToolCallResponse(tool_calls=[_call("read_file", path="b.py")]),
            ToolCallResponse(tool_calls=[_call("read_file", path="c.py")]),
            ToolCallResponse(content="done"),
        )
        dispatcher = RecordingDispatcher()

        await _loop(llm, dispatcher).run("compare them")

        assert len(dispatcher.ran) == 3

    @pytest.mark.asyncio
    async def test_re_running_a_command_after_an_edit_is_allowed(self):
        """The fix loop legitimately runs the same command repeatedly -- that
        is how it checks whether the last edit worked. Only *consecutive*
        identical calls with nothing in between count as stuck."""
        llm = ScriptedLLM(
            ToolCallResponse(tool_calls=[_call("run_command", command="python x.py")]),
            ToolCallResponse(tool_calls=[_call("edit_file", path="x.py")]),
            ToolCallResponse(tool_calls=[_call("run_command", command="python x.py")]),
            ToolCallResponse(tool_calls=[_call("edit_file", path="x.py")]),
            ToolCallResponse(tool_calls=[_call("run_command", command="python x.py")]),
            ToolCallResponse(content="fixed"),
        )
        dispatcher = RecordingDispatcher()

        await _loop(llm, dispatcher).run("fix it")

        assert len(dispatcher.ran) == 5, "an edit between runs means progress"
