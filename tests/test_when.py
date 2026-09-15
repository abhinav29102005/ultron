"""
Tests for utils/when.py – turning spoken time into a datetime.

"Remind me in ten minutes" and "remind me at half five" are the two shapes a
voice reminder actually arrives in, and neither is a timestamp. This parses
the handful of forms people really say and returns None for everything else,
so the caller can ask rather than guess.

Returning None matters as much as parsing does: a reminder set for the wrong
time is worse than one that was never set, because the user stops watching
for it.

Every test pins ``now`` explicitly. A parser tested against the real clock
passes at 3pm and fails at midnight.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from utils.when import parse_when

#: A fixed Monday afternoon to reason from.
NOW = datetime(2026, 3, 9, 14, 30, 0)


def _p(text):
    return parse_when(text, now=NOW)


class TestRelative:
    @pytest.mark.parametrize(
        "text,delta",
        [
            ("in 10 minutes", timedelta(minutes=10)),
            ("in ten minutes", timedelta(minutes=10)),
            ("in 1 minute", timedelta(minutes=1)),
            ("in a minute", timedelta(minutes=1)),
            ("in 2 hours", timedelta(hours=2)),
            ("in an hour", timedelta(hours=1)),
            ("in half an hour", timedelta(minutes=30)),
            ("in 30 seconds", timedelta(seconds=30)),
            ("in 3 days", timedelta(days=3)),
        ],
    )
    def test_relative_offsets(self, text, delta):
        assert _p(text) == NOW + delta

    def test_the_offset_is_found_inside_a_sentence(self):
        assert _p("remind me in 5 minutes to check the oven") == NOW + timedelta(minutes=5)


class TestClockTimes:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("at 5pm", datetime(2026, 3, 9, 17, 0)),
            ("at 5 pm", datetime(2026, 3, 9, 17, 0)),
            ("at 6:45pm", datetime(2026, 3, 9, 18, 45)),
            ("at 11:15", datetime(2026, 3, 10, 11, 15)),
            ("at 9am", datetime(2026, 3, 10, 9, 0)),
        ],
    )
    def test_clock_times(self, text, expected):
        assert _p(text) == expected

    def test_a_time_already_past_today_rolls_to_tomorrow(self):
        """At 14:30, "at 9am" can only mean tomorrow morning."""
        assert _p("at 9am") == datetime(2026, 3, 10, 9, 0)

    def test_a_time_still_ahead_stays_today(self):
        assert _p("at 5pm") == datetime(2026, 3, 9, 17, 0)


class TestTomorrow:
    def test_tomorrow_with_a_time(self):
        assert _p("tomorrow at 9am") == datetime(2026, 3, 10, 9, 0)

    def test_tomorrow_alone_defaults_to_morning(self):
        """No time given, so a sensible hour rather than this time tomorrow."""
        assert _p("tomorrow") == datetime(2026, 3, 10, 9, 0)

    def test_tonight(self):
        assert _p("tonight") == datetime(2026, 3, 9, 20, 0)


class TestRejection:
    @pytest.mark.parametrize(
        "text",
        ["", "   ", "later", "soon", "sometime", "when I get back", "remind me", None],
    )
    def test_vague_or_missing_times_are_rejected(self, text):
        """The caller asks the user instead of inventing a time."""
        assert _p(text) is None

    def test_a_zero_offset_is_rejected(self):
        """"in 0 minutes" is not a reminder, it is now."""
        assert _p("in 0 minutes") is None

    def test_an_absurd_offset_is_rejected(self):
        assert _p("in 500 years") is None

    def test_an_impossible_clock_time_is_rejected(self):
        assert _p("at 25:00") is None


class TestSubjectExtraction:
    """What to actually say when the reminder fires."""

    def test_the_time_words_are_stripped_from_the_subject(self):
        from utils.when import strip_when

        assert strip_when("remind me in 5 minutes to check the oven") == "check the oven"

    def test_a_trailing_time_is_stripped(self):
        from utils.when import strip_when

        assert strip_when("remind me to call mum at 5pm") == "call mum"

    def test_a_subject_with_no_time_survives_intact(self):
        from utils.when import strip_when

        assert strip_when("remind me to call mum") == "call mum"
