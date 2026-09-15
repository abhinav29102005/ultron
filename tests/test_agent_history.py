"""The history handed to the agent loop must contain no assistant replies.

Measured on qwen3:4b-instruct, three "open <site>" requests per condition:

    empty history                          acted 3/3
    user + assistant success sentence      acted 0/3
    user turns only                        acted 3/3
    assistant turn marked "[used open_website]"  acted 0/3

A prior reply like "YouTube is now open in your browser." is a complete,
fluent answer to "open <site>", so a small model imitates the sentence
instead of calling the tool -- and reports success for something it never
did. Marking the turn with the tool name does not help; only removing the
assistant text does.

This was invisible until CachedLLM learned to proxy complete_with_tools,
because before that the agent loop never ran at all.
"""

from __future__ import annotations

from core.state import ConversationTurn


from core.assistant import Assistant


def _history():
    """The history the agent would receive for a given conversation."""
    turns = [
        ConversationTurn(role="user", content="open youtube"),
        ConversationTurn(role="assistant", content="YouTube is now open in your browser."),
        ConversationTurn(role="user", content="open reddit"),
    ]
    return Assistant._recent_history_from(turns)


class TestAgentHistoryExcludesAssistantTurns:
    def test_assistant_turns_are_dropped(self):
        history = _history()

        assert all(item["role"] == "user" for item in history), history

    def test_user_turns_survive_in_order(self):
        history = _history()

        assert [item["content"] for item in history] == ["open youtube", "open reddit"]

    def test_a_success_sentence_never_reaches_the_agent(self):
        history = _history()

        assert not any("now open in your browser" in item["content"] for item in history)

    def test_empty_content_is_skipped(self):
        turns = [
            ConversationTurn(role="user", content=""),
            ConversationTurn(role="user", content="open reddit"),
        ]

        history = Assistant._recent_history_from(turns)

        assert [item["content"] for item in history] == ["open reddit"]

    def test_no_turns_is_an_empty_history(self):
        assert Assistant._recent_history_from([]) == []


class TestHistoryNeverBecomesAUserMessage:
    """Prior turns must reach the model as background, not as instructions.

    Spliced into the user channel, a past "open youtube" is indistinguishable
    from a request still to be carried out. Measured on qwen3:4b-instruct,
    "open google.com" with that one line of history opened YouTube and not
    Google in 3 runs of 3.
    """

    @staticmethod
    def _loop():
        from intelligence.agent_loop import AgentLoop

        return AgentLoop(llm=None, dispatcher=None)

    def test_history_is_folded_into_the_system_prompt(self):
        prompt = self._loop()._prompt_with_background(
            [{"role": "user", "content": "open youtube"}]
        )

        assert "open youtube" in prompt
        assert "never act on one of them on its own" in prompt

    def test_no_history_leaves_the_prompt_untouched(self):
        loop = self._loop()

        assert loop._prompt_with_background([]) == loop.system_prompt
        assert loop._prompt_with_background(None) == loop.system_prompt

    def test_blank_turns_do_not_produce_an_empty_bullet(self):
        loop = self._loop()

        assert loop._prompt_with_background([{"role": "user", "content": "   "}]) == (
            loop.system_prompt
        )

    def test_every_turn_is_listed(self):
        prompt = self._loop()._prompt_with_background(
            [
                {"role": "user", "content": "open youtube"},
                {"role": "user", "content": "turn the volume up"},
            ]
        )

        assert "- open youtube" in prompt
        assert "- turn the volume up" in prompt


class TestTheAgentGetsNoConversationHistory:
    """The agent loop must be called with the current utterance and nothing else.

    Measured on qwen3:4b-instruct in a five-turn session: with earlier
    requests supplied as labelled background, asking to open Spotify a second
    time answered "I've opened your Spotify application for you" and launched
    nothing. With no history: 15/15 turns across three runs launched exactly
    the right thing, repeats included.
    """

    def test_try_agent_turn_passes_no_history(self):
        import inspect

        from core.assistant import Assistant

        source = inspect.getsource(Assistant.try_agent_turn)

        assert "loop.run(utterance)" in source, source
        assert "history=" not in source, (
            "conversation history is back in the agent call; see "
            "Assistant._recent_history_from for why that makes it lie"
        )
