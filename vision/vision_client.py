"""
vision/vision_client.py – The Ollama connection the screen questions go over
=============================================================================
Every screen question used to build a throwaway ``AsyncClient``, send one chat
request with no ``keep_alive``, and drop it. That is what made looking at the
screen feel broken rather than slow: Ollama's default ``keep_alive`` is five
minutes, so a multimodal model asked a question, evicted from RAM, and asked
again is *reloaded from disk every time* — tens of seconds before a single
token is generated, on top of however long the answer actually takes.

So this module does two things the skill cannot do for itself:

* holds the model in RAM (``keep_alive``) for long enough that the second
  question is not a cold start, and
* :func:`preload` — pays that first load at startup, in the background, while
  the user is still deciding what to ask.

It is deliberately not a class. There is no per-request state worth keeping,
and Ollama itself owns the only thing that matters (the resident model), so a
long-lived client object would buy nothing but a lifecycle to get wrong.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from config.logging_config import get_logger
from vision.screen_capture import Capture, capture_screen_async

logger = get_logger("vision.client")

#: How long Ollama keeps the vision model resident after a request. Long
#: enough that a follow-up question never pays the load again, short enough
#: that a few GB are not held hostage for the rest of the day.
DEFAULT_KEEP_ALIVE = "30m"

#: Answers are spoken, one to three sentences. 300 tokens of decode budget for
#: a two-sentence reply is time the user spends listening to silence.
DEFAULT_NUM_PREDICT = 128

#: Descriptions, not invention.
DEFAULT_TEMPERATURE = 0.2

#: A generous ceiling, not a target: a cold 3B VLM on a slow CPU legitimately
#: takes a while. Its job is to tell a stall apart from a hang.
DEFAULT_TIMEOUT_SECONDS = 90

#: Same wording the skill used to return itself, kept reachable for callers.
OLLAMA_MISSING_MESSAGE = (
    "I can see the screen but the Ollama client isn't installed. "
    "Install it with: pip install ollama"
)

__all__ = [
    "DEFAULT_KEEP_ALIVE",
    "DEFAULT_NUM_PREDICT",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TIMEOUT_SECONDS",
    "OLLAMA_MISSING_MESSAGE",
    "Capture",
    "ask_vision",
    "capture_screen_async",
    "preload",
]


def _client(host: str):
    """An Ollama async client, or an ImportError worth reading aloud.

    The import is deferred because ``ollama`` is optional in practice: a user
    who never asks about the screen should still be able to import this
    module, and startup must not fail on a package they do not have.
    """
    try:
        from ollama import AsyncClient
    except ImportError as exc:
        raise ImportError(OLLAMA_MISSING_MESSAGE) from exc

    return AsyncClient(host=host)


async def ask_vision(
    *,
    model: str,
    host: str,
    messages: Sequence[Mapping[str, Any]],
    keep_alive: str = DEFAULT_KEEP_ALIVE,
    num_predict: int = DEFAULT_NUM_PREDICT,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Ask the vision model about an image and return the stripped answer.

    Errors are *not* caught. A missing model, a text-only model and an
    unreachable Ollama are the three failures a user actually hits, and each
    one has a specific thing they can do about it — which only the caller,
    holding the model name and the phrasing, is in a position to say. Swallow
    them here and all three become the same shrug.

    A timeout is re-raised as :class:`TimeoutError` carrying a sentence rather
    than an empty string, because ``asyncio.wait_for`` raises with no message
    and "I couldn't read the screen just now:" is not an answer.
    """
    client = _client(host)

    request = client.chat(
        model=model,
        messages=list(messages),
        # Top-level, not an option: this is a server-side residency hint, and
        # putting it in ``options`` silently does nothing.
        keep_alive=keep_alive,
        options={"temperature": temperature, "num_predict": num_predict},
    )

    if timeout is None:
        response = await request
    else:
        try:
            response = await asyncio.wait_for(request, timeout)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise TimeoutError(
                f"{model} took longer than {int(timeout)} seconds to answer. "
                "It may still be loading into memory — try again in a moment."
            ) from exc

    answer = (getattr(response.message, "content", None) or "").strip()
    logger.debug("Vision answer from {} ({} chars).", model, len(answer))
    return answer


async def preload(
    model: str,
    host: str,
    keep_alive: str = DEFAULT_KEEP_ALIVE,
) -> bool:
    """Load the vision model into RAM now, so the first question does not.

    Ollama treats a chat request with no messages as "load this and stop",
    returning as soon as the weights are resident. Calling it at startup moves
    the tens of seconds of disk load off the user's first question and into
    the time they spend getting to it.

    Never raises. Ollama not running and the model not pulled are both normal
    on a fresh machine, and neither is worth failing startup over — the real
    question later reports it properly through :func:`ask_vision`.
    """
    try:
        client = _client(host)
        await client.chat(model=model, messages=[], keep_alive=keep_alive)
    except Exception as exc:
        # Debug, not warning: on a machine with no vision model installed this
        # would otherwise cry wolf on every single launch.
        logger.debug("Vision preload of {} skipped: {}", model, exc)
        return False

    logger.info("Vision model {} preloaded (keep_alive={}).", model, keep_alive)
    return True
