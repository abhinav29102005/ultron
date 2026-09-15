"""
utils/consent.py – Reading yes and no out of a spoken reply
============================================================
The agent asks before it overwrites a file or closes an app. The answer comes
back through speech-to-text like everything else: lowercase, unpunctuated,
often prefixed with a filler word.

The asymmetry here is deliberate and is the whole design. Misreading a refusal
as consent overwrites the user's work; misreading consent as a refusal means
being asked once more. So this fails closed: anything that is not clearly a
yes is not a yes, and silence is never permission.

The trap worth naming is that a keyword search gets "yeah don't do that"
exactly backwards -- it contains "yeah". Negation is therefore checked first
and wins outright, whatever else the sentence contains.
"""

from __future__ import annotations

import re

#: Refusals, and the negating words that turn any sentence into one.
#:
#: Checked before the affirmatives and allowed to veto them, because a
#: negation attaches to the whole reply: "yes but not that file" is a no.
_NEGATIVE_RE = re.compile(
    r"\b(?:no|nope|nah|don'?t|do not|never|stop|cancel|abort|wait|hold on|"
    r"not now|not yet|leave it|forget it|never mind|nevermind|skip it|"
    r"negative|no thanks|not that)\b",
    re.IGNORECASE,
)

#: Consent, and only consent. Every entry has to be unambiguous on its own:
#: a word that merely *often* means yes ("right", "fine", "mhm") is left out,
#: because the cost of getting this wrong is the user's file.
_AFFIRMATIVE_RE = re.compile(
    r"\b(?:yes|yeah|yep|yup|yes please|sure|ok|okay|alright|"
    r"go ahead|go for it|do it|please do|confirm|confirmed|approved|"
    r"sounds good|absolutely|definitely|certainly|affirmative|"
    r"that'?s right|correct|proceed|carry on)\b",
    re.IGNORECASE,
)


def is_affirmative(reply: str | None) -> bool:
    """True only when ``reply`` is unmistakably consent.

    Everything else -- a refusal, a question, a fresh request, silence -- is
    False. The caller treats False as "do not do it", never as "ask again",
    so an unclear answer costs the user nothing.
    """
    text = (reply or "").strip()
    if not text:
        return False

    # Negation first, and it wins: see the module docstring.
    if _NEGATIVE_RE.search(text):
        return False

    return bool(_AFFIRMATIVE_RE.search(text))
