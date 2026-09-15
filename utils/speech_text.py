"""
utils/speech_text.py – Spoken vs. Displayed Text
=================================================
Turns a response meant to be *read* into one worth *hearing*.

Why this module exists
----------------------
Every response used to be spoken verbatim, which was fine while skills
returned one sentence ("Chrome opened successfully."). Research answers are
not one sentence: they carry inline citation markers and a list of source
URLs, and a speech synthesiser reads those out loud character by character —
"open bracket one close bracket ... h t t p s colon slash slash ...". The
useful part of the answer is buried in the middle of a minute of noise.

So the displayed text and the spoken text stop being the same string. The
screen keeps the full cited answer; the voice gets the prose.
"""

from __future__ import annotations

import re

#: Past this many characters, an answer is a document rather than a reply and
#: is summarised down for the voice. Roughly 25-30 seconds of speech, which is
#: about as long as anyone wants to be talked at before they can respond.
MAX_SPOKEN_CHARS = 400

#: A trailing source list, in the shapes the research synthesiser emits.
_SOURCES_BLOCK = re.compile(
    r"\n\s*(?:sources|references|citations)\s*:?\s*\n.*\Z",
    re.IGNORECASE | re.DOTALL,
)

#: Inline citation markers: "[1]", "[2][3]", "[1, 2]".
_CITATION_MARKER = re.compile(r"\s*\[\d+(?:\s*[,;]\s*\d+)*\]")

#: A bare URL anywhere in the prose.
_URL = re.compile(r"https?://\S+|www\.\S+")

#: Markdown emphasis and heading punctuation, which is silent on screen and
#: pronounced as "asterisk" / "hash" by some voices.
_MARKDOWN_NOISE = re.compile(r"[*_`#]+")

#: Sentence end, used to truncate somewhere a listener expects a pause rather
#: than mid-clause.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def strip_for_speech(text: str) -> str:
    """Remove the parts of a written answer that only make sense on screen."""
    text = _SOURCES_BLOCK.sub("", text)
    text = _CITATION_MARKER.sub("", text)
    text = _URL.sub("", text)
    text = _MARKDOWN_NOISE.sub("", text)
    # Collapse the gaps left behind, but keep paragraph breaks out of the
    # middle of a sentence.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return text.strip()


def shorten_for_speech(text: str, limit: int = MAX_SPOKEN_CHARS) -> str:
    """Cut a long answer at a sentence boundary near ``limit``.

    Truncating mid-word is worse than speaking a little too much, so the cut
    lands on the last complete sentence that fits; if the very first sentence
    is already over the limit, it is spoken whole rather than clipped.
    """
    if len(text) <= limit:
        return text

    sentences = _SENTENCE_END.split(text)
    kept: list[str] = []
    total = 0

    for sentence in sentences:
        if kept and total + len(sentence) > limit:
            break
        kept.append(sentence)
        total += len(sentence) + 1

    spoken = " ".join(kept).strip()

    # The full text is on screen, so say so rather than trailing off as if the
    # answer had simply ended.
    return f"{spoken} The rest is on screen."


def spoken_form(result: object, displayed: str) -> str:
    """Return what the voice should say for a response shown as ``displayed``.

    A skill that knows how it wants to be read aloud can say so by exposing a
    ``spoken`` attribute; that is always preferred, because the skill has
    context this function does not. Everything else is derived from the
    displayed text, so a skill written without any of this in mind still does
    not read URLs out loud.
    """
    explicit = getattr(result, "spoken", None)

    # Accepted as either an attribute or a method: DeepResearchSkill's result
    # computes its spoken form (it appends the source count), while a simpler
    # skill would just set a string. Requiring one shape would make the other
    # silently fall through to the generic cleaner.
    if callable(explicit):
        try:
            explicit = explicit()
        except Exception:
            # A skill that cannot describe itself out loud is not a reason to
            # lose the answer; fall back to cleaning the displayed text.
            explicit = None

    if isinstance(explicit, str) and explicit.strip():
        # Still length-budgeted. A skill's spoken() knows how to drop citation
        # scaffolding but not how long is too long -- a live research answer
        # came back as a well-formed 600-character paragraph, which is a solid
        # minute of uninterruptible speech.
        return shorten_for_speech(explicit.strip())

    cleaned = strip_for_speech(displayed)

    if not cleaned:
        # An answer that was nothing but links still needs *something* said,
        # or the assistant appears to have ignored the request.
        return "I've put what I found on screen."

    return shorten_for_speech(cleaned)
