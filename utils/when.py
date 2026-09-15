"""
utils/when.py – Turning spoken time into a datetime
====================================================
"Remind me in ten minutes" and "remind me to call mum at 5pm" are the two
shapes a spoken reminder actually arrives in. Neither is a timestamp.

Hand-rolled rather than pulled from a date library on purpose. The set of
phrasings a voice assistant really receives is small and the cost of a wrong
answer is high, so the grammar is written out explicitly and everything
outside it is refused. A general parser that confidently resolves "later" to
some hour would set a reminder the user never hears.

**None is a first-class answer.** A reminder at the wrong time is worse than
one that was never set, because the user stops watching for it. When this
returns None the caller asks.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

#: Number words that turn up in spoken durations. Past twelve, people say the
#: digits.
_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty five": 45, "fortyfive": 45, "fifty": 50, "sixty": 60, "ninety": 90,
}

_UNIT_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}

#: "in half an hour" / "in half a minute" -- common enough to be worth its own
#: rule, and unparseable by the numeric one.
_HALF_RE = re.compile(r"\bin\s+half\s+an?\s+(hour|minute)\b", re.IGNORECASE)

#: "in 10 minutes", "in ten minutes", "in a minute".
_OFFSET_RE = re.compile(
    r"\bin\s+(\d+|[a-z]+(?:\s+[a-z]+)?)\s+"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b",
    re.IGNORECASE,
)

#: "at 5pm", "at 6:45 pm", "at 11:15", "at 9 am".
_CLOCK_RE = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b",
    re.IGNORECASE,
)

_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
_TONIGHT_RE = re.compile(r"\b(tonight|this evening)\b", re.IGNORECASE)

#: Hours filled in when a day is named without a time.
DEFAULT_MORNING_HOUR = 9
DEFAULT_EVENING_HOUR = 20

#: Anything further out than this is a misparse, not a reminder. A year is
#: already far beyond what a voice assistant is trusted to remember.
MAX_OFFSET = timedelta(days=365)


def _number(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def parse_when(text: str | None, now: datetime | None = None) -> datetime | None:
    """The moment ``text`` names, or None when it does not name one.

    ``now`` is injected rather than read from the clock so this is testable at
    any hour; a parser verified only against the real clock passes in the
    afternoon and fails at midnight.
    """
    if not text or not text.strip():
        return None

    now = now or datetime.now()

    # ── "in half an hour" ─────────────────────────────────────────────────
    half = _HALF_RE.search(text)
    if half:
        unit = half.group(1).lower()
        return now + timedelta(minutes=30 if unit == "hour" else 0.5)

    # ── "in N <unit>" ─────────────────────────────────────────────────────
    offset = _OFFSET_RE.search(text)
    if offset:
        count = _number(offset.group(1))
        unit = _UNIT_SECONDS.get(offset.group(2).lower())

        if count and unit:
            delta = timedelta(seconds=count * unit)
            # Zero is "now", which is not a reminder; anything past the
            # ceiling is a misparse ("in 500 years").
            if timedelta(0) < delta <= MAX_OFFSET:
                return now + delta
        return None

    # ── a named day, with or without a clock time ─────────────────────────
    tomorrow = bool(_TOMORROW_RE.search(text))
    clock = _CLOCK_RE.search(text)

    if clock:
        hour = int(clock.group(1))
        minute = int(clock.group(2) or 0)
        meridiem = (clock.group(3) or "").replace(".", "").lower()

        if minute > 59:
            return None

        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        if hour > 23:
            return None

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if tomorrow:
            return target + timedelta(days=1)

        # A bare time that has already passed today means tomorrow -- "at 9am"
        # said at half past two in the afternoon cannot mean this morning.
        return target if target > now else target + timedelta(days=1)

    if _TONIGHT_RE.search(text):
        target = now.replace(
            hour=DEFAULT_EVENING_HOUR, minute=0, second=0, microsecond=0
        )
        return target if target > now else target + timedelta(days=1)

    if tomorrow:
        return (now + timedelta(days=1)).replace(
            hour=DEFAULT_MORNING_HOUR, minute=0, second=0, microsecond=0
        )

    return None


#: Phrases removed when recovering what the reminder is *about*.
_STRIP_PATTERNS = (
    _HALF_RE,
    _OFFSET_RE,
    _CLOCK_RE,
    _TOMORROW_RE,
    _TONIGHT_RE,
    re.compile(r"^\s*(?:hey\s+\w+[,\s]+)?(?:please\s+)?remind\s+me\s*", re.IGNORECASE),
    re.compile(r"\bset\s+a\s+reminder\s*", re.IGNORECASE),
    re.compile(r"^\s*to\s+", re.IGNORECASE),
)


def strip_when(text: str | None) -> str:
    """What the reminder is about, with the time words taken out.

    "remind me in 5 minutes to check the oven" leaves "check the oven", which
    is what gets spoken back when it fires. Without this the user hears their
    own scheduling instruction read out to them.
    """
    remaining = text or ""

    for pattern in _STRIP_PATTERNS:
        remaining = pattern.sub(" ", remaining)

    # The leading "to" often only appears once the time phrase in front of it
    # is gone, so it is stripped after the others rather than with them.
    remaining = re.sub(r"^\s*to\s+", "", remaining.strip(), flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", remaining).strip(" .,!?")
