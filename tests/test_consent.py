"""
Tests for utils/consent.py – reading yes and no out of a spoken reply.

The agent asks before it writes a file or closes an app, and the answer
arrives through the same speech-to-text path as everything else: lowercase,
unpunctuated, sometimes with a filler word in front, sometimes with the
transcriber's own guess at a mumble.

Two rules shape this:

  * anything that is not clearly a yes is not a yes. The cost of misreading
    "no, don't" as consent is an overwritten file; the cost of misreading a
    yes is being asked again;
  * a negation anywhere wins. "yeah don't do that" is a refusal, and a naive
    keyword search for "yeah" gets it exactly backwards.
"""

from __future__ import annotations

import pytest

from utils.consent import is_affirmative


class TestYes:
    @pytest.mark.parametrize(
        "reply",
        [
            "yes",
            "Yes.",
            "yeah",
            "yep",
            "yup",
            "sure",
            "okay",
            "ok",
            "go ahead",
            "do it",
            "please do",
            "confirm",
            "sounds good",
            "yes please",
            "go for it",
            "absolutely",
            "affirmative",
            "yeah go ahead",
        ],
    )
    def test_clear_consent_is_accepted(self, reply):
        assert is_affirmative(reply) is True


class TestNo:
    @pytest.mark.parametrize(
        "reply",
        [
            "no",
            "nope",
            "don't",
            "do not",
            "stop",
            "cancel",
            "wait",
            "no thanks",
            "not now",
            "leave it",
            "never mind",
            "hold on",
        ],
    )
    def test_refusal_is_rejected(self, reply):
        assert is_affirmative(reply) is False

    def test_a_negation_beats_an_affirmative_word(self):
        """The failure mode a keyword search walks straight into."""
        assert is_affirmative("yeah don't do that") is False
        assert is_affirmative("yes but not that file") is False
        assert is_affirmative("ok no wait") is False


class TestAmbiguous:
    @pytest.mark.parametrize(
        "reply",
        ["", "   ", "what", "hmm", "what do you mean", "read it again", "the other one"],
    )
    def test_anything_unclear_is_not_consent(self, reply):
        """Silence and confusion are not permission."""
        assert is_affirmative(reply) is False

    def test_none_is_not_consent(self):
        assert is_affirmative(None) is False

    def test_a_whole_new_request_is_not_consent(self):
        """The user changed their mind and asked for something else."""
        assert is_affirmative("actually what's the weather") is False
