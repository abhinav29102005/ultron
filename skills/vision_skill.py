"""
skills/vision_skill.py – Answer questions about what is on screen
=================================================================
Capture the active monitor, hand the image to a local vision model, speak the
answer.

The vision model is configured separately from the chat model. They are asked
to do different jobs and the good local options differ: a 3B text model is a
fine conversationalist and cannot see at all. Keeping ``VISION_MODEL`` apart
from ``QWEN_MODEL`` also means installing vision never changes how ULTRON
talks.

Nothing is captured unless an utterance routes here. There is no background
sampling, no buffer of recent screens, and the image is discarded once the
answer comes back.

The image does not have to come from the screen. An ``image_png`` parameter
makes the skill answer about a picture the caller already has — a screenshot
pasted into the chat panel — instead of grabbing the monitor, which by then
usually shows something else entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncio
import base64

from config.logging_config import get_logger
from skills.base import Skill
from vision.screen_capture import JPEG_QUALITY, MAX_EDGE, CaptureError, encode_image
from vision.vision_client import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_NUM_PREDICT,
    DEFAULT_TIMEOUT_SECONDS,
    ask_vision,
    capture_screen_async,
)

if TYPE_CHECKING:
    from intelligence.task import Task

logger = get_logger("skills.vision")

DEFAULT_VISION_MODEL = "qwen2.5vl:3b"

#: Spoken answers, so: no markdown, no lists, no preamble.
SYSTEM_PROMPT = (
    "You are ULTRON, looking at the user's screen through a screenshot. "
    "Answer what they asked about it directly and briefly, in one to three "
    "spoken sentences. Describe only what is actually visible. If the screen "
    "does not show what they are asking about, say so plainly. Never use "
    "markdown, bullet points, or headings — your answer is read aloud."
)

READ_PROMPT = (
    "Read the text visible on this screen back to the user. Give the text "
    "itself, not a description of it. If there is a lot, read the part that "
    "is most prominent or most likely the one they mean."
)


class VisionSkill(Skill):
    name = "VisionSkill"
    description = "Looks at the user's screen and answers questions about it."
    version = "1.0.0"
    enabled = True

    def _model(self) -> str:
        settings = getattr(self.container, "settings", None)
        return getattr(settings, "vision_model", None) or DEFAULT_VISION_MODEL

    def _host(self) -> str:
        settings = getattr(self.container, "settings", None)
        return getattr(settings, "ollama_base_url", None) or "http://localhost:11434"

    def _setting(self, name: str, fallback):
        """One settings lookup, tolerant of a container without settings."""
        settings = getattr(self.container, "settings", None)
        value = getattr(settings, name, None)
        return fallback if value is None else value

    def _question(self, task: Task) -> str:
        """What the user actually asked, falling back to their raw words."""
        params = task.parameters or {}
        question = (params.get("question") or params.get("query") or "").strip()
        if question:
            return question

        if (task.intent or "") == "screen_read":
            return READ_PROMPT

        raw = (task.metadata or {}).get("raw_utterance", "")
        return raw.strip() or "What is on my screen right now?"

    @staticmethod
    def _provided_image(task: Task) -> bytes | None:
        """PNG bytes the caller supplied, if this is not a screen question.

        A screenshot pasted into the chat is about the image, not about
        whatever is on the monitor now — by the time the user has typed their
        question the screen has usually moved on. Base64 is accepted as well
        as raw bytes because a task built from a tool call carries JSON, which
        has no way to hold bytes.
        """
        raw = (task.parameters or {}).get("image_png")
        if not raw:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        if isinstance(raw, str):
            payload = raw.split(",", 1)[-1] if raw.startswith("data:") else raw
            try:
                return base64.b64decode(payload, validate=False)
            except Exception:
                logger.warning("image_png was a string but not valid base64; ignoring.")
                return None
        return None

    def _screen_context(self):
        """The remembered look, when the process keeps one."""
        state = getattr(self.container, "state", None)
        return getattr(state, "screen_context", None)

    async def execute(self, task: Task) -> str:
        question = self._question(task)
        context = self._screen_context()

        # A follow-up ("what does the second one say?") is about the screen
        # already looked at, not whatever is there now. Re-capturing would
        # answer a different question, and pay for a second encode to do it.
        follow_up = bool((task.parameters or {}).get("follow_up"))
        messages = (
            context.follow_up_messages(question)
            if follow_up and context is not None
            else []
        )

        # An empty list also covers a context gone stale, so freshness never
        # needs a second check here — a stale look simply captures again.
        shot = None
        if not messages:
            max_edge = self._setting("vision_max_edge", MAX_EDGE)
            quality = self._setting("vision_jpeg_quality", JPEG_QUALITY)
            provided = self._provided_image(task)
            try:
                if provided is not None:
                    # Same downscale and JPEG settings as a capture: the model
                    # should see one kind of image whatever the source. The
                    # encode is real CPU work, so it goes off the loop like
                    # capture_screen_async does.
                    shot = await asyncio.to_thread(
                        encode_image, provided, max_edge, quality
                    )
                else:
                    shot = await capture_screen_async(
                        max_edge=max_edge,
                        quality=quality,
                    )
            except CaptureError as exc:
                return str(exc)
            messages = [
                {"role": "user", "content": question, "images": [shot.jpeg]}
            ]

        model = self._model()
        try:
            answer = await ask_vision(
                model=model,
                host=self._host(),
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                keep_alive=self._setting("vision_keep_alive", DEFAULT_KEEP_ALIVE),
                num_predict=self._setting("vision_num_predict", DEFAULT_NUM_PREDICT),
                timeout=self._setting("vision_timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            )
        except ImportError as exc:
            return str(exc)
        except Exception as exc:
            return self._explain_failure(exc, model)

        if not answer:
            return "I looked at your screen but couldn't make anything out."

        # Keep the look, so the next utterance can be a follow-up to it.
        if context is not None:
            if shot is not None:
                context.remember(
                    shot.jpeg,
                    question,
                    answer,
                    width=shot.width,
                    height=shot.height,
                )
            else:
                context.remember_follow_up(question, answer)

        logger.debug("Vision answer from {} ({} chars).", model, len(answer))
        return answer

    def _explain_failure(self, exc: Exception, model: str) -> str:
        """Turn an Ollama error into something the user can act on.

        A missing model is by far the likeliest failure on a fresh install,
        and "model not found" spoken aloud tells the user nothing they can do.
        """
        message = str(exc).lower()

        # A text-only model returns a 400 whose body is raw JSON. Spoken
        # aloud, that is a paragraph of punctuation.
        if "multimodal" in message or "does not support" in message:
            return (
                f"{model} can't look at images — it's a text-only model. "
                f"Set VISION_MODEL to a vision model such as {DEFAULT_VISION_MODEL}."
            )

        if "not found" in message or "no such model" in message or "pull" in message:
            return (
                f"I need the {model} vision model and it isn't installed yet. "
                f"Run: ollama pull {model}"
            )

        if "connection" in message or "refused" in message or "connect" in message:
            return (
                "I can't reach Ollama. Make sure it's running, then ask me again."
            )

        logger.exception("Vision request failed: {}", exc)
        return f"I couldn't read the screen just now: {exc}"
