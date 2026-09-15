"""
tests/test_intent_fallback.py – The rule-based path knows the new intents
=========================================================================
``_fallback`` runs whenever the LLM raises or returns junk, which on a local
3B model is not rare. Before this, it had never heard of the screen or file
intents, so with Ollama down "what's on my screen" reached ChatSkill, which
answered confidently about a screen it cannot see — a plausible wrong answer
rather than an error.

Worse, "open my budget spreadsheet" matched the generic ``open <word>`` rule
and launched whatever Start menu entry best matched the word "my".
"""

from __future__ import annotations

import pytest

from intelligence.intent_detector import IntentDetector


@pytest.fixture
def detector():
    instance = IntentDetector.__new__(IntentDetector)
    instance.llm = None
    instance.confidence_threshold = 0.75
    return instance


def classify(detector, utterance):
    result = detector._fallback(
        utterance, {"normalized_text": utterance.lower(), "entities": {}}
    )
    return result[0]


class TestScreenIntents:
    @pytest.mark.parametrize(
        "utterance",
        [
            "what's on my screen",
            "look at my screen",
            "what am i looking at",
            "help me with this",
            "what does this error mean",
            "can you see my screen",
        ],
    )
    def test_screen_questions_reach_vision(self, detector, utterance):
        assert classify(detector, utterance).intent == "screen_query"

    @pytest.mark.parametrize(
        "utterance", ["read this", "what does that say", "read it out"]
    )
    def test_read_requests_reach_screen_read(self, detector, utterance):
        assert classify(detector, utterance).intent == "screen_read"

    def test_screen_query_carries_the_question(self, detector):
        result = classify(detector, "what does this error mean")
        assert result.entities["question"] == "what does this error mean"

    def test_screenshot_still_saves_a_png(self, detector):
        """The two are different: one answers, one writes a file."""
        assert classify(detector, "take a screenshot").intent == "screenshot"
        assert classify(detector, "screen capture").intent == "screenshot"


class TestFileIntents:
    @pytest.mark.parametrize(
        "utterance,action,target",
        [
            ("find my resume", "find", "resume"),
            ("search for my resume", "find", "resume"),
            ("where is my thesis", "find", "thesis"),
            ("open my budget spreadsheet", "open", "budget spreadsheet"),
            ("open the file called notes", "open", "notes"),
        ],
    )
    def test_file_requests_reach_the_file_skill(
        self, detector, utterance, action, target
    ):
        result = classify(detector, utterance)
        assert result.intent == "file_search"
        assert result.entities["action"] == action
        assert result.entities["target"] == target

    def test_file_request_is_not_swallowed_by_open_application(self, detector):
        """This launched a Start menu entry matching the word "my" before."""
        result = classify(detector, "open my budget spreadsheet")
        assert result.intent != "open_application"
        assert result.entities.get("application") != "my"

    def test_category_word_is_not_part_of_the_name(self, detector):
        assert classify(detector, "find my resume file").entities["target"] == "resume"


class TestExistingIntentsStillWork:
    """The new rules run early, so they are the ones most able to break others."""

    @pytest.mark.parametrize(
        "utterance,intent",
        [
            ("open chrome", "open_application"),
            ("close spotify", "close_application"),
            ("play some music", "play_music"),
            ("pause", "media_control"),
            ("what's the weather", "weather"),
            ("what time is it", "time"),
            ("turn the volume up", "system_control"),
            ("hello", "greeting"),
            ("bye bye", "farewell"),
            ("what do you remember about me", "memory_recall"),
        ],
    )
    def test_unrelated_utterances_are_unaffected(self, detector, utterance, intent):
        assert classify(detector, utterance).intent == intent


class TestEveryRoutedIntentIsReachable:
    def test_no_routing_entry_is_orphaned(self):
        """A routing entry nothing can reach is dead code.

        There are two ways to reach one now. The classifier emits an intent
        from VALID_INTENTS, and the agent loop dispatches a tool whose
        ``intent`` names a routing entry. Some intents are deliberately only
        reachable the second way -- read_file and write_file are not offered
        to the classifier, because a 3B model picking "write_file" out of a
        list of thirty labels, with arguments it invented, is exactly the
        failure tool calling exists to prevent.
        """
        from intelligence.router import TaskRouter
        from intelligence.tool_registry import ALL_TOOLS

        reachable = IntentDetector.VALID_INTENTS | {tool.intent for tool in ALL_TOOLS}
        unreachable = set(TaskRouter.ROUTING_TABLE) - reachable
        assert not unreachable, f"routed but unreachable: {sorted(unreachable)}"

    def test_new_intents_are_in_the_llm_prompt_too(self, detector):
        """The fallback and the LLM path must agree on what exists."""
        prompt = detector._system_prompt()
        for intent in ("screen_query", "screen_read", "file_search"):
            assert intent in prompt
