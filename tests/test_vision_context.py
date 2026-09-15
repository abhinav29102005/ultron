"""
tests/test_vision_context.py – A screen answer survives the next question
==========================================================================
FRIDAY looked at the screen, answered, and forgot everything about it. The
user's next words — "what does the second one say?" — name no screen, so they
fell through to ChatSkill, which has never seen one and answered anyway.

Two halves have to hold for that to stop. The context has to keep the image,
the question and the answer for long enough to be followed up on, and no
longer. And the follow-up has to be recognised *only* after a screen turn: an
"what about that one?" out of the blue must stay where it was going, or every
vague sentence in the conversation hijacks the vision model.
"""

from __future__ import annotations

import types

import pytest

from intelligence.intent_detector import IntentDetector
from intelligence.router import TaskRouter
from skills.vision_skill import VisionSkill
from vision.screen_context import DEFAULT_TTL_SECONDS, ScreenContext

JPEG = b"\xff\xd8fake-jpeg-bytes"


class FakeClock:
    """A monotonic clock the test drives, so TTLs need no real waiting."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    from vision import screen_context

    fake = FakeClock()
    monkeypatch.setattr(screen_context, "time", fake)
    return fake


@pytest.fixture
def context():
    return ScreenContext()


# ------------------------------------------------------------------- storage
class TestRememberAndRecall:
    def test_round_trips_everything_the_follow_up_needs(self, context, clock):
        context.remember(
            JPEG,
            "what's on my screen",
            "Two errors in a terminal.",
            width=1280,
            height=720,
        )

        look = context.recall()
        assert look is not None
        assert look.image == JPEG
        assert (look.width, look.height) == (1280, 720)
        assert look.question == "what's on my screen"
        assert look.answer == "Two errors in a terminal."

    def test_nothing_remembered_recalls_nothing(self, context):
        assert context.recall() is None
        assert context.is_fresh() is False
        assert context.age_seconds() is None

    def test_only_the_latest_look_is_kept(self, context, clock):
        context.remember(b"old", "first", "first answer")
        context.remember(JPEG, "second", "second answer")

        look = context.recall()
        assert look.image == JPEG
        assert look.question == "second"

    def test_a_look_expires(self, context, clock):
        context.remember(JPEG, "what's on my screen", "A terminal.")
        assert context.is_fresh() is True

        clock.now += DEFAULT_TTL_SECONDS + 1
        assert context.is_fresh() is False
        assert context.recall() is None, "a ten-minute-old screen is not 'this'"

    def test_expiry_drops_the_image_rather_than_hiding_it(self, context, clock):
        context.remember(JPEG, "q", "a")
        clock.now += DEFAULT_TTL_SECONDS + 1

        context.recall()
        assert context.age_seconds() is None

    def test_ttl_can_be_overridden_per_call(self, context, clock):
        context.remember(JPEG, "q", "a")
        clock.now += 10

        assert context.is_fresh(ttl_seconds=30) is True
        assert context.is_fresh(ttl_seconds=5) is False

    def test_a_chain_of_follow_ups_builds_on_the_turn_before(self, context, clock):
        context.remember(JPEG, "what's on my screen", "Two errors.")
        clock.now += 20

        assert context.remember_follow_up("what does the second one say", "E404.")

        look = context.recall()
        assert look.image is JPEG, "the image must not be re-captured or copied"
        assert look.question == "what does the second one say"
        assert look.answer == "E404."
        assert look.captured_at == 1000.0, (
            "the picture is what goes stale; asking about it again does not "
            "make it younger"
        )

    def test_a_follow_up_with_nothing_held_is_refused(self, context, clock):
        assert context.remember_follow_up("q", "a") is False
        assert context.recall() is None

    def test_clear_wipes_the_image(self, context, clock):
        context.remember(JPEG, "q", "a")
        context.clear()

        assert context.recall() is None
        assert context.is_fresh() is False
        assert context.follow_up_messages("and the second one?") == []


# ------------------------------------------------------------------ messages
class TestFollowUpMessages:
    def test_builds_the_prior_turn_then_the_new_question(self, context, clock):
        context.remember(JPEG, "what's on my screen", "Two errors in a terminal.")

        messages = context.follow_up_messages("what does the second one say?")

        assert [m["role"] for m in messages] == ["user", "assistant", "user"]
        assert messages[0]["content"] == "what's on my screen"
        assert messages[1]["content"] == "Two errors in a terminal."
        assert messages[2]["content"] == "what does the second one say?"

    def test_the_image_rides_only_on_the_first_user_turn(self, context, clock):
        context.remember(JPEG, "what's on my screen", "Two errors.")

        messages = context.follow_up_messages("and the second one?")

        assert messages[0]["images"] == [JPEG]
        assert "images" not in messages[1]
        assert "images" not in messages[2], (
            "re-sending the image would pay for a second encode and invite the "
            "model to describe the screen again instead of answering"
        )

    def test_a_stale_look_builds_nothing(self, context, clock):
        context.remember(JPEG, "what's on my screen", "Two errors.")
        clock.now += DEFAULT_TTL_SECONDS + 1

        assert context.follow_up_messages("and the second one?") == []

    def test_nothing_remembered_builds_nothing(self, context):
        assert context.follow_up_messages("and the second one?") == []


# ------------------------------------------------------------------- routing
@pytest.fixture
def detector():
    instance = IntentDetector.__new__(IntentDetector)
    instance.llm = None
    instance.confidence_threshold = 0.75
    instance.last_intent = None
    return instance


def classify(detector, utterance):
    result = detector._fallback(
        utterance, {"normalized_text": utterance.lower(), "entities": {}}
    )
    return result[0]


def routed_skill(intent: str):
    from skills.system_skills import DefaultSkill

    return TaskRouter.ROUTING_TABLE.get(intent, DefaultSkill)


#: Deliberately none of these name a screen. "read that one" is left out on
#: purpose — SCREEN_READ_RE already catches it with or without a turn behind
#: it, so it proves nothing about follow-ups.
FOLLOW_UPS = [
    "what about the second one",
    "and the button next to it",
    "read the second one",
    "what about that",
    "and?",
    "the third line",
    "explain it",
    "what else",
]


class TestFollowUpsReachVision:
    @pytest.mark.parametrize("utterance", FOLLOW_UPS)
    def test_after_a_screen_turn_they_go_to_the_vision_skill(
        self, detector, utterance
    ):
        detector.last_intent = "screen_query"
        result = classify(detector, utterance)

        assert result.intent in {"screen_query", "screen_read"}
        assert routed_skill(result.intent) is VisionSkill

    @pytest.mark.parametrize("utterance", FOLLOW_UPS)
    def test_with_no_screen_turn_behind_them_they_do_not(self, detector, utterance):
        """The one that matters: "what about that" is usually not about a screen.

        Letting the words alone decide would send an arbitrary share of
        ordinary conversation to a vision model and a screenshot with it.
        """
        detector.last_intent = None
        assert routed_skill(classify(detector, utterance).intent) is not VisionSkill

    def test_a_screen_turn_two_turns_ago_is_not_followed_up(self, detector):
        detector.last_intent = "weather"
        assert (
            routed_skill(classify(detector, "what about the second one").intent)
            is not VisionSkill
        )

    def test_the_follow_up_carries_the_users_words_as_the_question(self, detector):
        detector.last_intent = "screen_read"
        result = classify(detector, "what does the second one say")

        assert result.entities["question"] == "what does the second one say"
        assert result.entities["follow_up"] is True

    @pytest.mark.parametrize(
        "utterance,intent",
        [
            ("play the next one", "play_music"),
            ("turn the volume up", "system_control"),
            ("open chrome", "open_application"),
            ("what's the weather", "weather"),
            # Not a screen intent, and that is the point: the web-lookup
            # blockers veto commands and small talk before the follow-up
            # patterns ever get a look at them.
            ("thanks", "general_chat"),
            ("bye bye", "farewell"),
        ],
    )
    def test_real_requests_after_a_screen_turn_are_untouched(
        self, detector, utterance, intent
    ):
        detector.last_intent = "screen_query"
        assert classify(detector, utterance).intent == intent


# ------------------------------------------------------------- the whole path
class FakeLLM:
    """Returns canned intent JSON, in order, one per detect() call."""

    def __init__(self, replies):
        self._replies = list(replies)

    def build_system_message(self, content):
        return {"role": "system", "content": content}

    def build_user_message(self, content):
        return {"role": "user", "content": content}

    async def complete(self, messages, json_mode=False):
        return types.SimpleNamespace(content=self._replies.pop(0))


SCREEN_JSON = '{"intents":[{"intent":"screen_query","confidence":0.95,"entities":{}}]}'
CHAT_JSON = '{"intents":[{"intent":"general_chat","confidence":0.6,"entities":{}}]}'


class TestDetectRemembersTheTurnBefore:
    async def test_a_follow_up_is_corrected_off_general_chat(self):
        """The model never sees the previous turn, so it always says chat."""
        detector = IntentDetector(llm=FakeLLM([SCREEN_JSON, CHAT_JSON]))

        first = await detector.detect("what's on my screen")
        assert first[0].intent == "screen_query"

        second = await detector.detect("what does the second one say")
        assert second[0].intent == "screen_query"
        assert second[0].entities["follow_up"] is True

    async def test_the_same_words_after_ordinary_chat_stay_chat(self):
        detector = IntentDetector(llm=FakeLLM([CHAT_JSON, CHAT_JSON]))

        await detector.detect("tell me a joke")
        second = await detector.detect("what does the second one say")

        assert second[0].intent != "screen_query"

    async def test_the_last_leg_of_a_compound_request_is_what_is_remembered(self):
        compound = (
            '{"intents":['
            '{"intent":"screen_query","confidence":0.9,"entities":{}},'
            '{"intent":"system_control","confidence":0.9,'
            '"entities":{"action":"up"}}]}'
        )
        detector = IntentDetector(llm=FakeLLM([compound, CHAT_JSON]))

        await detector.detect("look at my screen and turn the volume up")
        second = await detector.detect("what about the second one")

        assert second[0].intent != "screen_query", (
            "the turn ended on the volume, so nothing is being followed up"
        )


class TestStateCarriesTheContext:
    def test_runtime_state_starts_with_an_empty_screen_context(self):
        from core.state import AssistantRuntimeState

        state = AssistantRuntimeState()
        assert isinstance(state.screen_context, ScreenContext)
        assert state.screen_context.recall() is None

    def test_each_state_gets_its_own(self):
        from core.state import AssistantRuntimeState

        one = AssistantRuntimeState()
        two = AssistantRuntimeState()
        one.screen_context.remember(JPEG, "q", "a")

        assert two.screen_context.recall() is None
