"""
Tests for provider-level function calling.

Two providers, two wire formats that are nearly but not quite the same:

  * NVIDIA NIM is OpenAI-compatible, so tool calls arrive as objects with a
    ``function.arguments`` JSON **string**;
  * Ollama returns ``function.arguments`` as a **dict** already, and older
    models simply ignore the ``tools`` argument.

Both are normalised to :class:`~llm.tools.ToolCallResponse` so the agent loop
never has to know which one answered.

A provider that cannot call tools must raise ToolsUnsupportedError rather than
returning something plausible-looking, because the assistant uses that
exception to fall back to the old classifier pipeline.

No network here: both clients are replaced with fakes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from config.settings import Settings
from llm.tools import ToolCallResponse, ToolsUnsupportedError

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "The time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]


def _settings(provider="nvidia", key="sk-test"):
    s = Settings()
    s.llm_provider = provider
    s.nvidia_api_key = SecretStr(key)
    return s


# ── NVIDIA / OpenAI-compatible ────────────────────────────────────────────


def _openai_reply(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
    )


def _openai_tool_call(id="call_1", name="get_time", arguments="{}"):
    return SimpleNamespace(
        id=id, function=SimpleNamespace(name=name, arguments=arguments)
    )


class FakeOpenAIClient:
    def __init__(self, reply):
        self._reply = reply
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.kwargs = kwargs
        return self._reply


@pytest.fixture
def nvidia():
    from llm.nvidia import NvidiaLLM

    llm = NvidiaLLM(_settings())
    return llm


class TestNvidiaToolCalling:
    @pytest.mark.asyncio
    async def test_plain_text_comes_back_with_no_tool_calls(self, nvidia):
        nvidia._client = FakeOpenAIClient(_openai_reply(content="It is four."))

        result = await nvidia.complete_with_tools([{"role": "user", "content": "hi"}], TOOLS)

        assert isinstance(result, ToolCallResponse)
        assert result.content == "It is four."
        assert result.wants_tools is False

    @pytest.mark.asyncio
    async def test_a_tool_call_is_parsed(self, nvidia):
        nvidia._client = FakeOpenAIClient(
            _openai_reply(tool_calls=[_openai_tool_call(arguments='{"level": 40}')])
        )

        result = await nvidia.complete_with_tools([], TOOLS)

        assert result.wants_tools is True
        assert result.tool_calls[0].name == "get_time"
        assert result.tool_calls[0].arguments == {"level": 40}

    @pytest.mark.asyncio
    async def test_the_tools_are_sent_to_the_api(self, nvidia):
        client = FakeOpenAIClient(_openai_reply(content="ok"))
        nvidia._client = client

        await nvidia.complete_with_tools([], TOOLS)

        assert client.kwargs["tools"] == TOOLS

    @pytest.mark.asyncio
    async def test_broken_argument_json_does_not_raise(self, nvidia):
        """A model that emits a missing brace must not end the conversation."""
        nvidia._client = FakeOpenAIClient(
            _openai_reply(tool_calls=[_openai_tool_call(arguments="{oops")])
        )

        result = await nvidia.complete_with_tools([], TOOLS)

        assert result.tool_calls[0].arguments == {}

    @pytest.mark.asyncio
    async def test_a_null_content_becomes_an_empty_string(self, nvidia):
        """OpenAI sends content=None alongside tool calls."""
        nvidia._client = FakeOpenAIClient(
            _openai_reply(content=None, tool_calls=[_openai_tool_call()])
        )

        result = await nvidia.complete_with_tools([], TOOLS)

        assert result.content == ""


# ── Ollama / local ────────────────────────────────────────────────────────


class FakeOllamaClient:
    def __init__(self, reply):
        self._reply = reply
        self.kwargs = None

    async def chat(self, **kwargs):
        self.kwargs = kwargs
        return self._reply


def _ollama_reply(content="", tool_calls=None):
    return SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=tool_calls),
        prompt_eval_count=1,
        eval_count=2,
    )


@pytest.fixture
def qwen():
    from llm.qwen import QwenLLM

    return QwenLLM(_settings(provider="qwen"))


class TestQwenToolCalling:
    @pytest.mark.asyncio
    async def test_a_dict_argument_is_kept(self, qwen):
        """Ollama already decodes the arguments, unlike OpenAI."""
        qwen._client = FakeOllamaClient(
            _ollama_reply(
                tool_calls=[
                    SimpleNamespace(
                        function=SimpleNamespace(name="get_time", arguments={"tz": "IST"})
                    )
                ]
            )
        )

        result = await qwen.complete_with_tools([], TOOLS)

        assert result.tool_calls[0].name == "get_time"
        assert result.tool_calls[0].arguments == {"tz": "IST"}

    @pytest.mark.asyncio
    async def test_a_tool_call_without_an_id_still_gets_one(self, qwen):
        """Ollama does not send call ids, but the transcript needs them to
        match each result back to the call that produced it."""
        qwen._client = FakeOllamaClient(
            _ollama_reply(
                tool_calls=[
                    SimpleNamespace(function=SimpleNamespace(name="get_time", arguments={}))
                ]
            )
        )

        result = await qwen.complete_with_tools([], TOOLS)

        assert result.tool_calls[0].id

    @pytest.mark.asyncio
    async def test_plain_text_is_returned(self, qwen):
        qwen._client = FakeOllamaClient(_ollama_reply(content="hello"))

        result = await qwen.complete_with_tools([], TOOLS)

        assert result.content == "hello"
        assert result.wants_tools is False

    @pytest.mark.asyncio
    async def test_a_model_that_ignores_tools_is_reported_as_unsupported(self, qwen):
        """Ollama raises for a model without tool support. The assistant needs
        that surfaced as ToolsUnsupportedError so it can fall back."""

        class Refusing:
            async def chat(self, **kwargs):
                raise Exception("registry.ollama.ai/library/qwen2.5:3b does not support tools")

        qwen._client = Refusing()

        with pytest.raises(ToolsUnsupportedError):
            await qwen.complete_with_tools([], TOOLS)


# ── switcher ──────────────────────────────────────────────────────────────


class TestSwitcherDelegates:
    @pytest.mark.asyncio
    async def test_the_active_provider_handles_the_call(self):
        from llm.switcher import LLMSwitcher

        switcher = LLMSwitcher(_settings(provider="nvidia"))

        class Recording:
            def __init__(self):
                self.seen = None

            async def complete_with_tools(self, messages, tools, **kwargs):
                self.seen = tools
                return ToolCallResponse(content="delegated")

        inner = Recording()
        switcher._nvidia = inner

        result = await switcher.complete_with_tools([], TOOLS)

        assert result.content == "delegated"
        assert inner.seen == TOOLS


class TestBaseDefault:
    @pytest.mark.asyncio
    async def test_a_provider_that_does_not_override_reports_unsupported(self):
        """The mock provider used in tests, for instance. Better an explicit
        exception the caller handles than a silent lack of tool use."""
        from llm.mock import MockLLM

        llm = MockLLM()

        with pytest.raises(ToolsUnsupportedError):
            await llm.complete_with_tools([], TOOLS)


# ── the transcript sent back ──────────────────────────────────────────────


class TestAssistantTurnFormat:
    """The two providers disagree about one field, and it is easy to miss.

    Ollama's Message model validates ``tool_calls[].function.arguments`` as a
    **dict** and rejects a string. OpenAI's API specifies the same field as a
    JSON **string**. The agent loop keeps the neutral Python form -- a dict --
    and the OpenAI-compatible provider serialises on the way out.

    Found end-to-end, not in a unit test: every unit test until now stopped at
    the first model reply, and this only bites on the *second* round trip,
    when the first round's tool calls are echoed back in the transcript.
    """

    def test_the_loop_keeps_arguments_as_a_dict(self):
        from intelligence.agent_loop import AgentLoop
        from llm.tools import ToolCall

        turn = AgentLoop._assistant_turn(
            ToolCallResponse(tool_calls=[ToolCall(id="1", name="set_volume",
                                                  arguments={"level": 40})])
        )

        assert turn["tool_calls"][0]["function"]["arguments"] == {"level": 40}

    @pytest.mark.asyncio
    async def test_nvidia_serialises_arguments_to_a_string(self, nvidia):
        client = FakeOpenAIClient(_openai_reply(content="ok"))
        nvidia._client = client

        await nvidia.complete_with_tools(
            [
                {"role": "user", "content": "louder"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "type": "function",
                            "function": {"name": "set_volume", "arguments": {"level": 40}},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "1", "name": "set_volume", "content": "done"},
            ],
            TOOLS,
        )

        sent = client.kwargs["messages"]
        assert sent[1]["tool_calls"][0]["function"]["arguments"] == '{"level": 40}'

    @pytest.mark.asyncio
    async def test_an_already_serialised_argument_string_is_left_alone(self, nvidia):
        client = FakeOpenAIClient(_openai_reply(content="ok"))
        nvidia._client = client

        await nvidia.complete_with_tools(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "1",
                            "type": "function",
                            "function": {"name": "x", "arguments": '{"a": 1}'},
                        }
                    ],
                }
            ],
            TOOLS,
        )

        assert client.kwargs["messages"][0]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_ordinary_messages_are_untouched(self, nvidia):
        client = FakeOpenAIClient(_openai_reply(content="ok"))
        nvidia._client = client

        original = [{"role": "user", "content": "hello"}]
        await nvidia.complete_with_tools(original, TOOLS)

        assert client.kwargs["messages"] == [{"role": "user", "content": "hello"}]


class TestAgentTokenBudget:
    """A tool-calling turn needs far more output budget than a chat reply.

    llm_max_tokens is 256, tuned for a spoken sentence. Found live: nemotron
    reasons before it acts, and 256 tokens ran out mid-thought -- the loop got
    three steps in, then returned "Let's edit the copy to return 0 or maybe
    None? U" as its final answer. Truncation looks exactly like a model that
    decided to stop, so the loop cannot detect it; the budget has to be right.
    """

    @pytest.mark.asyncio
    async def test_tool_turns_get_the_agent_budget_not_the_chat_one(self, nvidia):
        client = FakeOpenAIClient(_openai_reply(content="ok"))
        nvidia._client = client

        await nvidia.complete_with_tools([], TOOLS)

        assert client.kwargs["max_tokens"] >= 1024, (
            "a reasoning model truncated mid-thought at 256"
        )

    @pytest.mark.asyncio
    async def test_an_explicit_override_still_wins(self, nvidia):
        client = FakeOpenAIClient(_openai_reply(content="ok"))
        nvidia._client = client

        await nvidia.complete_with_tools([], TOOLS, max_tokens=64)

        assert client.kwargs["max_tokens"] == 64


class TestTransientServerErrors:
    """NIM returns sporadic 500s. One must not lose the user's turn.

    Seen live: three identical fix-loop runs, one succeeded and two died on
    "Error code: 500 - Internal server error". Retrying is correct here
    because a 500 carries no state -- nothing was executed on their side.
    """

    @pytest.mark.asyncio
    async def test_a_500_is_retried(self, nvidia):
        attempts = []

        class Flaky(FakeOpenAIClient):
            async def _create(self, **kwargs):
                attempts.append(1)
                if len(attempts) < 2:
                    raise RuntimeError("Error code: 500 - Internal server error")
                return _openai_reply(content="second time lucky")

        nvidia._client = Flaky(None)

        result = await nvidia.complete_with_tools([], TOOLS)

        assert result.content == "second time lucky"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_retries_are_bounded(self, nvidia):
        attempts = []

        class Broken(FakeOpenAIClient):
            async def _create(self, **kwargs):
                attempts.append(1)
                raise RuntimeError("Error code: 500 - Internal server error")

        nvidia._client = Broken(None)

        with pytest.raises(Exception):
            await nvidia.complete_with_tools([], TOOLS)

        assert len(attempts) <= 3, "a dead endpoint must not be hammered"

    @pytest.mark.asyncio
    async def test_a_retired_model_is_not_retried(self, nvidia):
        """410 Gone is permanent. Retrying wastes the user's turn."""
        attempts = []

        class Gone(FakeOpenAIClient):
            async def _create(self, **kwargs):
                attempts.append(1)
                raise RuntimeError("Error code: 410 - The model has been retired")

        nvidia._client = Gone(None)

        with pytest.raises(Exception):
            await nvidia.complete_with_tools([], TOOLS)

        assert len(attempts) == 1
