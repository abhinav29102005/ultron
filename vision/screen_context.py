"""
vision/screen_context.py – Remember the last look at the screen
===============================================================
A screen question is almost never the end of it. The user asks "what's on my
screen", hears the answer, and then asks "what does the second one say?" —
which means nothing on its own. Answering it needs the picture FRIDAY was
already looking at, the question it was already asked, and the answer it
already gave.

Without that, a follow-up goes one of two wrong ways: it reaches ChatSkill,
which has never seen a screen and answers confidently anyway, or it comes back
to the vision model and triggers a second capture — a fresh screenshot of a
screen that may have moved on, at the cost of another encode and another
vision-model turn.

This module holds one look, in memory, for as long as it can still plausibly
be what "this" means.

Privacy
-------
``screen_capture`` is explicit that screenshots are not retained, and that is
still true. This is a single in-memory slot on the running process: never
written to disk, never logged, never sent anywhere the screenshot was not
already going. It holds exactly one look — each :meth:`ScreenContext.remember`
drops the previous image — it expires on its own after ``DEFAULT_TTL_SECONDS``,
and it dies with the process. "Not retained" means nothing outlives the
conversation it belongs to, not that FRIDAY has to forget between one sentence
and the next.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from config.logging_config import get_logger

logger = get_logger("vision.context")

#: How long a remembered look still counts as "this" or "that", in seconds.
#:
#: Two minutes. A spoken follow-up lands within seconds — the user hears the
#: answer, thinks, and asks again — and two minutes leaves room for a long
#: spoken reply plus a pause without stretching so far that the screen has
#: moved on to unrelated work. Past that, "the second one" far more likely
#: means something newly on screen, and a confidently stale answer is worse
#: than the single extra screenshot that re-capturing costs.
DEFAULT_TTL_SECONDS = 120.0


@dataclass(frozen=True)
class ScreenLook:
    """One remembered look at the screen: what was seen, asked, and answered."""

    #: The encoded image exactly as it was handed to the model. Opaque here on
    #: purpose — this module never decodes it, so it neither knows nor cares
    #: whether it is JPEG, PNG, or something else entirely.
    image: bytes
    width: int
    height: int
    question: str
    answer: str
    #: ``time.monotonic``, not wall clock: a clock change or a laptop resume
    #: must not make a stale look look fresh, or a fresh one expire.
    captured_at: float


class ScreenContext:
    """The most recent look at the screen, and nothing before it.

    One slot, deliberately. A history of screens would be a growing pile of
    pictures of the user's desktop held in memory for no gain: a follow-up
    refers to what was just discussed, never to the screen from four turns
    ago.

    No lock. Every mutation is a single attribute rebind, which the GIL makes
    atomic, and a reader either sees the whole previous look or the whole new
    one — never a half-written mixture of the two. That is all the
    thread-safety a single assistant process needs.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._look: ScreenLook | None = None

    def remember(
        self,
        image: bytes,
        question: str,
        answer: str,
        *,
        width: int = 0,
        height: int = 0,
    ) -> None:
        """Record the look just taken, replacing whatever was held before."""
        self._look = ScreenLook(
            image=image,
            width=width,
            height=height,
            question=(question or "").strip(),
            answer=(answer or "").strip(),
            captured_at=time.monotonic(),
        )
        logger.debug(
            "Remembered a %dx%d screen look (%d KB) for %.0fs.",
            width,
            height,
            len(image or b"") // 1024,
            self.ttl_seconds,
        )

    def remember_follow_up(self, question: str, answer: str) -> bool:
        """Re-point the held look at a later question about the same image.

        A chain of follow-ups ("...and the one below that?") should build on
        the turn immediately before it, not on the first thing ever asked
        about this screen. Returns False when nothing is held.

        The capture time is deliberately *not* reset. The picture is what goes
        stale, and it is no younger for having been asked about again.
        """
        look = self._look
        if look is None:
            return False

        self._look = ScreenLook(
            image=look.image,
            width=look.width,
            height=look.height,
            question=(question or "").strip(),
            answer=(answer or "").strip(),
            captured_at=look.captured_at,
        )
        return True

    def recall(self, ttl_seconds: float | None = None) -> ScreenLook | None:
        """The remembered look, or None if there is none or it has expired.

        Expiry drops the image rather than merely hiding it: once a look can
        no longer be used there is no reason to keep a picture of the user's
        desktop in memory.
        """
        look = self._look
        if look is None:
            return None

        if not self._is_fresh(look, ttl_seconds):
            self.clear()
            return None

        return look

    def is_fresh(self, ttl_seconds: float | None = None) -> bool:
        """True when a look is held and is still recent enough to refer to."""
        return self._is_fresh(self._look, ttl_seconds)

    def age_seconds(self) -> float | None:
        """How long ago the held look was taken, or None if nothing is held."""
        look = self._look
        if look is None:
            return None
        return time.monotonic() - look.captured_at

    def clear(self) -> None:
        """Forget the held look and its image.

        Called on shutdown, and whenever the conversation has plainly moved
        on. Cheap enough to call unconditionally.
        """
        self._look = None

    def follow_up_messages(
        self,
        new_question: str,
        ttl_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        """Chat messages that continue the previous screen turn.

        The image rides on the *first* user turn only, where it belongs: it is
        what that question was asked about. Repeating it on the new turn would
        re-send the whole payload and invite the model to describe the screen
        again instead of answering the follow-up.

        Returns an empty list when there is nothing fresh to build on, so a
        caller can branch on truthiness and fall back to capturing.
        """
        look = self.recall(ttl_seconds)
        if look is None:
            return []

        return [
            {"role": "user", "content": look.question, "images": [look.image]},
            {"role": "assistant", "content": look.answer},
            {"role": "user", "content": (new_question or "").strip()},
        ]

    def _is_fresh(self, look: ScreenLook | None, ttl_seconds: float | None) -> bool:
        if look is None:
            return False
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        return (time.monotonic() - look.captured_at) <= ttl
