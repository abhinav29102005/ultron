"""
Tests for the assistant's agent mode – core/assistant.py.

Agent mode is the new default turn: hand the model tools and let it work.
The classifier pipeline is still there underneath, and the point of these
tests is the seam between them.

Three things have to hold or agent mode is not safe to switch on:

  * when the provider can call tools, the agent answers and the classifier is
    not consulted at all;
  * when it cannot, the turn falls back to the classifier rather than failing
    -- this is what keeps FRIDAY working offline on qwen2.5:3b;
  * ``AGENT_MODE=false`` turns the whole thing off.
"""

from __future__ import annotations

import asyncio

import pytest

from core.assistant import Assistant
from llm.tools import ToolCallResponse, ToolsUnsupportedError


class FakeLLM:
    """A provider whose tool support is configurable."""

    def __init__(self, *, supports_tools=True, reply="agent answered"):
        self._supports = supports_tools
        self._reply = reply
        self.seen_tools = None

    async def complete_with_tools(self, messages, tools, **kwargs):
        if not self._supports:
            raise ToolsUnsupportedError("no tool support")
        self.seen_tools = tools
        return ToolCallResponse(content=self._reply)


class FakeSettings:
    agent_mode = True
    agent_max_steps = 6
    agent_time_budget_seconds = 120
    agent_confirm_timeout_seconds = 25


class FakeContainer:
    def __init__(self, llm):
        self.llm = llm
        self.settings = FakeSettings()


@pytest.fixture
def assistant():
    def build(llm):
        return Assistant(FakeContainer(llm))

    return build


class TestAgentTurn:
    @pytest.mark.asyncio
    async def test_the_agent_answers_when_tools_are_supported(self, assistant):
        friday = assistant(FakeLLM(reply="It's 16:05."))

        result = await friday.try_agent_turn("what time is it")

        assert result is not None
        assert result.text == "It's 16:05."

    @pytest.mark.asyncio
    async def test_the_real_tools_are_offered(self, assistant):
        """A turn with an empty tool list is agent mode in name only."""
        llm = FakeLLM()
        friday = assistant(llm)

        await friday.try_agent_turn("hello")

        names = {t["function"]["name"] for t in llm.seen_tools}
        assert "read_screen_text" in names
        assert "read_file" in names


class TestFallback:
    @pytest.mark.asyncio
    async def test_an_unsupported_provider_falls_back(self, assistant):
        """None is the signal to run the classifier pipeline instead."""
        friday = assistant(FakeLLM(supports_tools=False))

        assert await friday.try_agent_turn("what time is it") is None

    @pytest.mark.asyncio
    async def test_agent_mode_can_be_switched_off(self, assistant):
        friday = assistant(FakeLLM())
        friday._container.settings.agent_mode = False

        assert await friday.try_agent_turn("what time is it") is None

    @pytest.mark.asyncio
    async def test_an_unexpected_error_falls_back_rather_than_failing_the_turn(
        self, assistant
    ):
        class Broken(FakeLLM):
            async def complete_with_tools(self, messages, tools, **kwargs):
                raise RuntimeError("the API is down")

        friday = assistant(Broken())

        assert await friday.try_agent_turn("what time is it") is None

    @pytest.mark.asyncio
    async def test_a_barge_in_is_not_swallowed_by_the_fallback(self, assistant):
        """Cancellation means the user interrupted. Falling back to the
        classifier would answer a question they have already moved on from."""

        class Cancelled(FakeLLM):
            async def complete_with_tools(self, messages, tools, **kwargs):
                raise asyncio.CancelledError()

        friday = assistant(Cancelled())

        with pytest.raises(asyncio.CancelledError):
            await friday.try_agent_turn("what time is it")


class TestConfirmation:
    @pytest.mark.asyncio
    async def test_a_pending_question_consumes_the_next_utterance(self, assistant):
        """While FRIDAY is waiting on a yes or no, "yes" is an answer, not a
        new request to classify."""
        friday = assistant(FakeLLM())
        waiter = asyncio.get_running_loop().create_future()
        friday._pending_confirmation = waiter

        consumed = friday.consume_confirmation("yes go ahead")

        assert consumed is True
        assert await waiter is True

    @pytest.mark.asyncio
    async def test_a_refusal_is_delivered_as_false(self, assistant):
        friday = assistant(FakeLLM())
        waiter = asyncio.get_running_loop().create_future()
        friday._pending_confirmation = waiter

        friday.consume_confirmation("no don't")

        assert await waiter is False

    def test_with_nothing_pending_the_utterance_is_left_alone(self, assistant):
        friday = assistant(FakeLLM())
        assert friday.consume_confirmation("yes") is False

    @pytest.mark.asyncio
    async def test_an_already_settled_question_is_not_answered_twice(self, assistant):
        friday = assistant(FakeLLM())
        waiter = asyncio.get_running_loop().create_future()
        waiter.set_result(True)
        friday._pending_confirmation = waiter

        assert friday.consume_confirmation("no") is False
