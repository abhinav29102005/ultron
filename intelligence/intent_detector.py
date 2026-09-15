"""
intelligence/intent_detector.py – Intent Detection
====================================================
Uses the configured LLM to classify user utterances
and extract structured entities. Supports compound
requests that map to multiple intents.

Team: Planner Team
Phase: 2 (Intent Detection)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from intelligence.parser import STTParser

if TYPE_CHECKING:
    from llm.base import BaseLLM


# ── The web-lookup boundary ───────────────────────────────────────────────
#
# "Look it up on the web" must not mean "open Chrome for everything". A tab
# that pops up for "what's 2+2" or "good night" is worse than no tab at all,
# so the boundary is drawn explicitly here rather than left to the model's
# judgement, and the LLM's answer is corrected against it.
#
# The rule, in one sentence: a question goes to the web when answering it
# needs information the assistant does not and cannot hold — something
# current, external, or specific to the real world — and never when the
# assistant, the operating system, or plain arithmetic can answer it.
#
# WEB_LOOKUP_BLOCKERS is the ceiling: if one matches, no tab opens, whatever
# the model said. WEB_LOOKUP_TRIGGERS is the floor: if one matches and no
# blocker does, a tab opens even if the model wanted to answer from memory.
# Between the two, the model decides.

#: Utterances another part of Friday already answers. Never a web lookup.
WEB_LOOKUP_BLOCKERS = (
    # Arithmetic — MathSkill's job. "what is 2+2", "calculate 15 times 4".
    r"^\s*(?:what(?:'?s| is)|calculate|compute|how much is)?\s*"
    r"\d+(?:\.\d+)?\s*(?:[\+\-\*/x%]|plus|minus|times|multiplied by|divided by|over)\s*\d",
    r"\b(?:calculate|compute)\b",
    r"\b(?:square root|to the power of|percent of)\b",

    # The clock and the calendar — ClockSkill's job.
    r"\b(?:what(?:'?s| is)\s+the\s+time|time is it|current time|"
    r"what(?:'?s| is)\s+(?:today'?s\s+)?date|date is it|what day is it)\b",

    # The weather — WeatherSkill's job.
    r"\b(?:weather|temperature|forecast|humidity)\b",

    # Questions about Friday itself, and for its help.
    r"\b(?:what can you do|who are you|what(?:'?s| is) your name|"
    r"how do you work|are you (?:there|awake|listening)|help me with|"
    r"what are your (?:commands|skills))\b",
    r"^\s*help\s*$",

    # Memory.
    r"\b(?:remember|forget|know about me|remember about me)\b",

    # Machine commands, not questions. "open chrome", "play despacito",
    # "turn up the volume", "take a screenshot".
    r"^\s*(?:hey\s+\w+[,\s]+)?(?:please\s+)?"
    r"(?:open|close|launch|start|quit|exit|play|pause|resume|stop|skip|next|"
    r"previous|turn (?:up|down|on|off)|set|mute|unmute|increase|decrease|dim|"
    r"take|capture|create|delete|rename|move|shut\s?down|restart|lock)\b",
    r"\b(?:screenshot|volume|brightness|microphone)\b",
    # Transport controls. "next" and "when's the next ..." are otherwise a
    # collision waiting to happen.
    r"\b(?:next|previous|last)\s+(?:song|track|tune)\b",

    # Small talk, greetings and goodbyes.
    r"^\s*(?:hi|hello|hey|yo|sup|thanks|thank you|ok(?:ay)?|cool|nice|"
    r"good (?:morning|afternoon|evening|night)|"
    r"bye|bye bye|goodbye|good bye|see (?:you|ya)|night night|"
    r"how are you|what'?s up)\b",
)

#: Utterances that always need live or external information.
WEB_LOOKUP_TRIGGERS = (
    # The user asked for a search in so many words.
    r"\b(?:search (?:the web|online|for|up)|look (?:it |that |this )?up|"
    r"look up|google|web ?search|browse for|find (?:me )?(?:some )?"
    r"(?:info|information|details) (?:on|about))\b",
    r"\bon the (?:web|internet)\b",

    # Recency and live data. The model's weights cannot answer these.
    r"\b(?:latest|current|currently|right now|today'?s|this (?:week|month|year)|"
    r"recent|recently|so far this|up to date|as of now|breaking)\b",
    r"\b(?:news|headlines|stock (?:price|market)|share price|exchange rate|"
    r"score|scores|fixtures|standings|release date|box office)\b",

    # Real-world entities and events the assistant should look up rather than
    # assert from memory.
    r"\b(?:who (?:is|are|was|were)|who won|who' ?s winning|"
    r"what happened (?:to|with|in|at)|"
    r"how (?:many|much) .+ (?:are there|is there|does .+ cost)|"
    r"tell me about)\b",
    r"\bprice of\b",
    # "When is/was X" is nearly always a date the assistant should check
    # rather than recall. The transport-control blocker above keeps
    # "next song" out of this.
    r"\bwhen (?:is|'?s|are|was|were|will|did|does)\b",
    r"\bthe next\b",
)

_BLOCKER_RE = re.compile("|".join(WEB_LOOKUP_BLOCKERS), re.IGNORECASE)
_TRIGGER_RE = re.compile("|".join(WEB_LOOKUP_TRIGGERS), re.IGNORECASE)


def is_web_lookup_blocked(text: str) -> bool:
    """True when this utterance must never open a browser tab."""
    return bool(_BLOCKER_RE.search(text or ""))


def needs_web_lookup(text: str) -> bool:
    """
    True when answering this utterance requires the live web.

    The blockers win over the triggers, so "what's the weather today" stays
    with WeatherSkill even though "today" is a recency marker.
    """
    text = text or ""
    if is_web_lookup_blocked(text):
        return False
    return bool(_TRIGGER_RE.search(text))


@dataclass
class DetectedIntent:
    """
    Parsed intent classification result for a single intent.
    Contains fields only.
    """

    intent: str
    confidence: float
    entities: dict[str, Any]
    raw_utterance: str


# Screen and file phrasings, shared by the LLM correction pass and the
# rule-based fallback. Defined once so the two paths cannot drift apart and
# classify the same sentence differently depending on whether Ollama is up.
SCREEN_READ_RE = re.compile(
    r"\b(read (this|that|it|the screen)|what does (this|that|it) say|"
    r"read (this|that) (out|aloud|back)|read it out)\b"
)

SCREEN_QUERY_RE = re.compile(
    r"\b(on|at) (my|the) screen\b|\bwhat am i looking at\b|"
    r"\blook at (my|the) screen\b|\bsee (my|the) screen\b|"
    r"\bwhat('s| is) (this|that)\b|"
    r"\bwhat does (this|that) (error|message|warning)\b|"
    r"\bhelp me (with|fix) (this|that)\b|"
    r"\b(explain|what does) (this|that) mean\b"
)

SCREENSHOT_RE = re.compile(r"\b(screenshot|screen capture)\b")


# ── "open <a website>" ────────────────────────────────────────────────────
#
# The generic open_application rule below matches "open <any word>", so before
# this every site the user named was handed to the Start menu, which launched
# the nearest installed thing — "open youtube in chrome" opened the YouTube
# Music desktop app. The rule-based path has to know which names are sites for
# the same reason the prompt does, and both read the one registry in
# skills.system_skills so they cannot disagree.

#: The verb, then up to the first three words of what follows. The leading
#: article and possessive are dropped because "open the youtube" is common
#: dictation noise.
_OPEN_SITE_RE = re.compile(
    r"\b(?:open|go to|goto|visit|pull up|bring up|take me to|show me)\s+"
    r"(?:up\s+)?(?:the\s+|my\s+)?"
    r"([a-z0-9][\w.\-]*(?:\s+[a-z0-9][\w.\-]*){0,2})",
    re.IGNORECASE,
)

#: What to search for once the site is open. "and look up MKBHD", "and search
#: for mechanical keyboards". Deliberately excludes "play", which belongs to
#: play_music.
_SITE_QUERY_RE = re.compile(
    r"\b(?:and\s+)?(?:look\s+up|look\s+for|search\s+for|search|find)\s+(.+)$",
    re.IGNORECASE,
)


def _opened_phrases(text: str) -> list[str]:
    """Longest-first name candidates following an "open" verb.

    Longest first because the short form is usually a different thing:
    "google maps" is a site but "google chrome" is an app, and only the
    three-word form of "visual studio code" is a registered alias.
    """
    match = _OPEN_SITE_RE.search(text or "")
    if not match:
        return []

    words = match.group(1).lower().split()
    return [" ".join(words[:count]) for count in range(len(words), 0, -1)]


def names_a_website(text: str) -> tuple[str, str] | None:
    """Return ``(site, query)`` when the utterance opens a known website.

    ``query`` is "" when the user only asked for the site. Returns None when
    no known site is named, so the caller falls through to the application
    rules unchanged.
    """
    # Imported here, not at module scope: intelligence/__init__ imports this
    # module, and skills.system_skills pulls in sympy, so an eager import
    # would put a heavy dependency on the import path of every consumer of
    # `intelligence` for the sake of one lookup table.
    from skills.system_skills import ApplicationSkill, resolve_website

    for candidate in _opened_phrases(text):
        if candidate in ApplicationSkill.APP_ALIASES:
            # Installed software wins over the site of the same name, which is
            # what keeps "open claude" and "open whatsapp" opening the app.
            return None
        if candidate in ApplicationSkill.WEBSITE_FIRST_NAMES or (
            "." in candidate and resolve_website(candidate) is not None
        ):
            query = _SITE_QUERY_RE.search(text or "")
            return candidate, (query.group(1).strip(" .?!") if query else "")

    return None


def names_an_application(text: str) -> str | None:
    """Return the registered application alias the utterance opens, or None.

    The entity extractor captures a single word, so "open google chrome" gives
    it "google" — which is now a website-first name and would open google.com.
    Matching the two-word alias first keeps the browser launching.
    """
    from skills.system_skills import ApplicationSkill

    for candidate in _opened_phrases(text):
        if candidate in ApplicationSkill.APP_ALIASES:
            return candidate

    return None


def refers_to_the_screen(text: str) -> str | None:
    """The screen intent this utterance implies, or None.

    "What does this error mean" has no searchable subject — "this" is on the
    user's screen, not on the web — so a web lookup for it returns nothing
    useful. A local 3B model routes it to web_lookup about half the time,
    which is why this correction exists rather than more prompt wording.
    """
    text = (text or "").lower()
    if SCREENSHOT_RE.search(text):
        return None
    if SCREEN_READ_RE.search(text):
        return "screen_read"
    if SCREEN_QUERY_RE.search(text):
        return "screen_query"
    return None


# ── Screen follow-ups ─────────────────────────────────────────────────────
#
# The patterns above all name the screen one way or another. The second thing
# a user says never does: having just been told what is on screen, they ask
# "what about the second one?" or "and the button next to it?" — an utterance
# with no subject of its own, which on its own words is indistinguishable from
# small talk and lands in general_chat, where a model that has never seen a
# screen answers it anyway.
#
# So this cannot be decided from the words alone. It takes the words *and*
# the fact that the previous turn was about the screen; IntentDetector holds
# the latter and passes it in.

#: Screen intents, for recognising that the previous turn was one.
SCREEN_INTENTS = frozenset({"screen_query", "screen_read"})

#: Utterances that only make sense as a continuation. Each is either bare
#: ("and?") or purely deictic ("the second one") — never self-contained.
SCREEN_FOLLOW_UPS = (
    # Bare continuations.
    r"^\s*(?:and|and then|then|so|go on|carry on|keep going|what else|"
    r"anything else|the rest)\s*[?.!]*\s*$",

    # "what about the error", "and the button next to it".
    r"^\s*(?:ok(?:ay)?[,\s]+|so\s+|and\s+|but\s+)*(?:what|how)\s+about\b",
    r"^\s*and\s+(?:the|that|this|those|these|it)\b",

    # An ordinal or a position standing in for something on the screen.
    r"\b(?:first|second|third|fourth|fifth|sixth|last|other|top|bottom|left|"
    r"right|middle|red|green|blue|highlighted)\s+"
    r"(?:one|line|row|item|button|option|tab|column|entry|result|error|"
    r"message|paragraph|box|field|link)\b",
    r"^\s*(?:the\s+)?ones?\s+"
    r"(?:above|below|under|underneath|next to|beside|after|before|"
    r"on the (?:left|right))\b",

    # A read or explain request whose only object is a pronoun.
    r"^\s*(?:can you\s+|could you\s+|please\s+)*"
    r"(?:read|say|repeat|explain|describe|translate|summarise|summarize)\s+"
    r"(?:me\s+)?(?:that|this|it|them|those|the rest)\b",
)

_SCREEN_FOLLOW_UP_RE = re.compile("|".join(SCREEN_FOLLOW_UPS), re.IGNORECASE)


def continues_a_screen_turn(text: str, *, after_screen_turn: bool) -> bool:
    """True when this utterance elaborates on the screen just discussed.

    ``after_screen_turn`` is not optional context, it is half the signal.
    "What about that one?" is a screen question after FRIDAY has just read the
    screen and an ordinary sentence at any other moment, and letting every
    "what about that" reach the vision model would hijack the assistant.

    The web-lookup blockers double as the veto here: a device command or a
    greeting is not a follow-up however deictic it sounds, and "play the next
    one" must stay with the music.
    """
    if not after_screen_turn:
        return False
    text = (text or "").lower()
    if is_web_lookup_blocked(text):
        return False
    return bool(_SCREEN_FOLLOW_UP_RE.search(text))


class IntentDetector:
    """
    Extracts one or more intents and entities from text using an LLM.
    """

    VALID_INTENTS = {
        "weather",
        "news",
        "time",
        "date",
        "calculator",
        "open_application",
        "close_application",
        "open_website",
        "search_web",
        "web_lookup",
        "play_music",
        "media_control",
        "system_control",
        "file_operation",
        "brightness_control",
        "mic_control",
        "screenshot",
        "clipboard",
        "notes",
        "reminder",
        "help",
        "greeting",
        "farewell",
        "general_chat",
        "memory_recall",
        "memory_forget",
        "screen_query",
        "screen_read",
        "file_search",
    }

    def __init__(
        self,
        llm: BaseLLM,
        confidence_threshold: float = 0.75,
    ) -> None:
        """
        Initialise IntentDetector.
        """
        self.llm = llm
        self.confidence_threshold = confidence_threshold
        #: The intent the previous utterance resolved to, or None on the first
        #: turn. A deictic follow-up ("and the second one?") can only be read
        #: against what came before it, and the detector is the one component
        #: that already sees every utterance in order — so it remembers its own
        #: last answer rather than reaching for conversation state it does not
        #: own.
        self.last_intent: str | None = None

    async def detect(self, utterance: str) -> list[DetectedIntent]:
        """
        Detect one or more intents and their entities using the
        configured LLM. Returns a list to support compound requests
        like "Open Chrome and search for AI news".
        """

        # Keep parser for normalization/entity extraction for now.
        parsed_data = STTParser.parse(utterance)

        cleaned_text = parsed_data["normalized_text"]

        messages = [
            self.llm.build_system_message(self._system_prompt()),
            self.llm.build_user_message(cleaned_text),
        ]

        try:
            response = await self.llm.complete(messages, json_mode=True)

            raw_intents = self._parse_llm_response(response.content)

            detected: list[DetectedIntent] = []

            for item in raw_intents:
                intent = item.get("intent")
                confidence = float(item.get("confidence", 0.0))
                entities = item.get("entities", {})

                if intent not in self.VALID_INTENTS:
                    continue

                if not isinstance(entities, dict):
                    entities = {}

                detected.append(
                    DetectedIntent(
                        intent=intent,
                        confidence=confidence,
                        entities=entities,
                        raw_utterance=utterance,
                    )
                )

            if not detected:
                return self._remember(self._fallback(utterance, parsed_data))

            return self._remember(
                self._coalesce_site_search(
                    self._apply_web_lookup_boundary(detected, cleaned_text)
                )
            )

        except Exception as exc:
            # Keep Friday usable if the local LLM fails.
            print(f"LLM intent detection failed: {exc}")
            return self._remember(self._fallback(utterance, parsed_data))

    def _remember(self, detected: list[DetectedIntent]) -> list[DetectedIntent]:
        """Record what this turn resolved to, then hand the result straight on.

        The *last* intent of a compound request is the one a follow-up
        continues: "look at my screen and turn the volume up" ends on the
        volume, so "and the other one?" after it is not a screen question.
        """
        if detected:
            self.last_intent = detected[-1].intent
        return detected

    def _coalesce_site_search(
        self, detected: list[DetectedIntent]
    ) -> list[DetectedIntent]:
        """Fold "open <site>" + "search for X" into one in-site search.

        "Open youtube and look up MKBHD" is a single action: land on YouTube's
        results page for MKBHD. qwen2.5:3b reliably splits it into an
        ``open_website`` and a ``search_web``, which executes as two unrelated
        things -- a blank youtube.com tab, plus a web research run on
        "MKBHD" -- and that split is exactly what the user complained about.

        The prompt already asks the model not to do this and it does it
        anyway; a 3B model cannot be reliably instructed out of a decomposition
        this natural. So the repair is deterministic and happens here, where
        both intents are visible at once.

        Only sites with a real in-site search are merged. For the rest,
        ``build_website_url`` would fall back to a Google ``site:`` query,
        which is a worse answer than simply doing the two things the user
        literally said.
        """
        if len(detected) < 2:
            return detected

        # Lazy, for the same reason as names_a_website: system_skills pulls in
        # sympy, and this module is imported by intelligence/__init__.
        from skills.system_skills import resolve_website

        merged: list[DetectedIntent] = []
        index = 0

        while index < len(detected):
            current = detected[index]
            following = detected[index + 1] if index + 1 < len(detected) else None

            if (
                following is not None
                and current.intent == "open_website"
                and following.intent in ("search_web", "web_lookup")
                and not str(current.entities.get("query") or "").strip()
            ):
                query = str(following.entities.get("query") or "").strip()
                site = resolve_website(str(current.entities.get("website") or ""))

                if query and site is not None and site.search:
                    merged.append(
                        DetectedIntent(
                            intent="open_website",
                            confidence=min(current.confidence, following.confidence),
                            entities={**current.entities, "query": query},
                            raw_utterance=current.raw_utterance,
                        )
                    )
                    index += 2
                    continue

            merged.append(current)
            index += 1

        return merged

    def _is_screen_follow_up(self, text: str) -> bool:
        """True when this utterance elaborates on the screen turn before it."""
        return continues_a_screen_turn(
            text, after_screen_turn=self.last_intent in SCREEN_INTENTS
        )

    def _system_prompt(self) -> str:
        """
        Prompt Qwen to perform structured intent detection.
        Supports returning multiple intents for compound requests.
        """
        return """
You are the intent detection engine for the FRIDAY desktop assistant.

The user's request may contain ONE action or MULTIPLE actions
chained together (e.g. "Open Chrome and search for AI news").

Classify the request into an ORDERED LIST of intents, one entry
per distinct action, in the order they should be performed.

Valid intents:

weather
news
time
date
calculator
open_application
close_application
open_website
search_web
web_lookup
play_music
media_control
system_control
file_operation
brightness_control
mic_control
screenshot
clipboard
notes
reminder
help
greeting
farewell
general_chat
memory_recall
memory_forget
screen_query
screen_read
file_search

Return ONLY valid JSON.
Do not use markdown.
Do not include explanations.

Required JSON format:

{
  "intents": [
    {
      "intent": "one_valid_intent",
      "confidence": 0.0,
      "entities": {}
    }
  ]
}

For "system_control" (volume commands), entities must be:
  "action": one of "up", "down", "mute", "unmute", "max", "min", "set"
  "level": an integer 0-100, ONLY when action is "set"

For "calculator", entities must be:
  "expression": the arithmetic to evaluate, written using only digits and
  the operators + - * / ( ) — never words. e.g. "15*4", "(2+3)/4", "144/12"

For "memory_forget", entities must be:
  "target": what the user wants forgotten, e.g. "my job", "favourite editor"

"memory_recall" takes no entities. Use it when the user asks what you know
or remember about them.

For "file_operation" (folder commands), entities must be:
  "action": one of "open", "create", "list", "delete", "modify"
  "folder_name": the folder's current name/location, e.g. "Downloads", "Projects"
  For "modify" ONLY, also include when relevant:
    "new_name": the new name to rename the folder to
    "destination": the target parent location to move the folder into, e.g. "Desktop", "Documents"
  A "modify" request may include new_name only, destination only, or both.

For "brightness_control" (screen brightness), entities must be:
  "action": one of "up", "down", "set"
  "level": an integer 0-100, ONLY when action is "set"

For "mic_control" (microphone), entities must be:
  "action": one of "mute", "unmute", "toggle"

Use "screen_query" when the user asks about what is currently on their screen,
or asks for help with whatever they are looking at. e.g. "what's on my screen",
"what does this error mean", "help me with this", "what am I looking at".
Entities must be:
  "question": what they want to know about the screen, in their own words

Use "screen_read" only when they want text on screen read back verbatim.
e.g. "read this", "what does that say". It takes no entities.

Do NOT use "screenshot" for either of those — that intent only saves a PNG to
disk and shows the user nothing.

Use "file_search" when the user wants to find or open a FILE or an
application by name rather than a known folder. e.g. "find my resume",
"open budget spreadsheet", "where is my thesis". Entities must be:
  "action": one of "open", "find", "create"
  "target": the file or folder name they said, e.g. "resume", "budget"
Requests naming a standard folder ("open Downloads") are "file_operation".
Requests naming an application ("open Chrome") are "open_application".

For "open_application", entities must be:
  "application": the app name exactly as the user said it, e.g. "Chrome"
Use it ONLY for software installed on the computer: Chrome, Edge, Firefox,
VS Code, Spotify, Discord, Notepad, Calculator, Word, Excel, Zoom.

For "open_website", entities must be:
  "website": the site name or domain, e.g. "youtube", "gmail", "bbc.co.uk"
  "query": what to search for ON that site — omit it entirely if the user
  did not ask to search for anything
A website is "open_website" even when the user says "open": YouTube, Gmail,
Google, Maps, Drive, Reddit, X/Twitter, Instagram, Facebook, LinkedIn,
Wikipedia, Amazon, Netflix, Stack Overflow and GitHub are websites, not
installed programs.

A browser named in the request — "in chrome", "on chrome", "using edge" — is
HOW to open the site. It is never a second "open_application" intent.

"Open a site and look something up on it" is ONE "open_website" intent
carrying both "website" and "query". Do not also emit "search_web" or
"web_lookup" for the same request: that would open a second, useless tab.

For "play_music" (playing a song or artist in Spotify), entities must be:
  "query": the song, artist or album the user named, e.g. "Blinding Lights",
  "Bohemian Rhapsody by Queen". Omit "query" entirely when the user just said
  "play some music" without naming anything.

For "media_control" (transport controls for music already playing), entities:
  "action": one of "pause", "resume", "next", "previous", "stop"

Use "web_lookup" when answering NEEDS live or external information: the user
asked you to search or look something up, asked about news, prices, scores,
recent events, or asked about a real person, place, company or event whose
facts you should not assert from memory.

Do NOT use "web_lookup" for anything Friday already answers itself:
arithmetic (use calculator), the time or date (use time/date), the weather
(use weather), questions about Friday itself (use help), greetings,
goodbyes, or ordinary small talk (use greeting/farewell/general_chat).

For "web_lookup", entities must be:
  "query": the thing to look up, with the "search for"/"look up" framing
  stripped off, e.g. "who won the 2024 election"

Use "farewell" when the user is ending the conversation or saying goodbye:
"bye", "bye bye", "goodbye", "good night", "see you", "see ya",
"talk to you later", "catch you later". Note that "good morning",
"good afternoon" and "good evening" are greetings, not farewells.

Examples:
User: "Delete the Projects folder"
{
  "intents": [
    {
      "intent": "file_operation",
      "confidence": 0.97,
      "entities": {"action": "delete", "folder_name": "Projects"}
    }
  ]
}

User: "Open Chrome"
{
  "intents": [
    {
      "intent": "open_application",
      "confidence": 0.98,
      "entities": {"application": "Chrome"}
    }
  ]
}

User: "Open Spotify"
{
  "intents": [
    {
      "intent": "open_application",
      "confidence": 0.98,
      "entities": {"application": "Spotify"}
    }
  ]
}

User: "Open YouTube"
{
  "intents": [
    {
      "intent": "open_website",
      "confidence": 0.97,
      "entities": {"website": "youtube"}
    }
  ]
}

User: "Open youtube in chrome and look up MKBHD"
{
  "intents": [
    {
      "intent": "open_website",
      "confidence": 0.97,
      "entities": {"website": "youtube", "query": "MKBHD"}
    }
  ]
}

User: "Open reddit and search for mechanical keyboards"
{
  "intents": [
    {
      "intent": "open_website",
      "confidence": 0.96,
      "entities": {"website": "reddit", "query": "mechanical keyboards"}
    }
  ]
}

User: "What's 15 times 4?"
{
  "intents": [
    {
      "intent": "calculator",
      "confidence": 0.98,
      "entities": {"expression": "15*4"}
    }
  ]
}

User: "Calculate 144 divided by 12 plus 7"
{
  "intents": [
    {
      "intent": "calculator",
      "confidence": 0.97,
      "entities": {"expression": "144/12+7"}
    }
  ]
}

User: "Search for AI news"
{
  "intents": [
    {
      "intent": "search_web",
      "confidence": 0.98,
      "entities": {"query": "AI news"}
    }
  ]
}

User: "Open Chrome and search for AI news"
{
  "intents": [
    {
      "intent": "open_application",
      "confidence": 0.98,
      "entities": {"application": "Chrome"}
    },
    {
      "intent": "search_web",
      "confidence": 0.98,
      "entities": {"query": "AI news"}
    }
  ]
}

User: "What's the weather today?"
{
  "intents": [
    {
      "intent": "weather",
      "confidence": 0.98,
      "entities": {}
    }
  ]
}

User: "Take a screenshot"
{
  "intents": [
    {
      "intent": "screenshot",
      "confidence": 0.99,
      "entities": {}
    }
  ]
}

User: "Turn up the volume"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.97,
      "entities": {"action": "up"}
    }
  ]
}

User: "Turn down the volume"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.97,
      "entities": {"action": "down"}
    }
  ]
}

User: "Mute the volume"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.98,
      "entities": {"action": "mute"}
    }
  ]
}

User: "Unmute"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.98,
      "entities": {"action": "unmute"}
    }
  ]
}

User: "Set volume to 50%"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.98,
      "entities": {"action": "set", "level": 50}
    }
  ]
}

User: "Max out the volume"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.97,
      "entities": {"action": "max"}
    }
  ]
}

User: "Set volume to minimum"
{
  "intents": [
    {
      "intent": "system_control",
      "confidence": 0.97,
      "entities": {"action": "min"}
    }
  ]
}

User: "What do you know about me?"
{
  "intents": [
    {
      "intent": "memory_recall",
      "confidence": 0.98,
      "entities": {}
    }
  ]
}

User: "Forget where I live"
{
  "intents": [
    {
      "intent": "memory_forget",
      "confidence": 0.97,
      "entities": {"target": "where I live"}
    }
  ]
}

User: "Open my Downloads folder"
{
  "intents": [
    {
      "intent": "file_operation",
      "confidence": 0.98,
      "entities": {"action": "open", "folder_name": "Downloads"}
    }
  ]
}

User: "Create a new folder called Projects"
{
  "intents": [
    {
      "intent": "file_operation",
      "confidence": 0.98,
      "entities": {"action": "create", "folder_name": "Projects"}
    }
  ]
}

User: "List what's in my Documents folder"
{
  "intents": [
    {
      "intent": "file_operation",
      "confidence": 0.98,
      "entities": {"action": "list", "folder_name": "Documents"}
    }
  ]
}

User: "Increase brightness"
{
  "intents": [
    {
      "intent": "brightness_control",
      "confidence": 0.97,
      "entities": {"action": "up"}
    }
  ]
}

User: "Set brightness to 40 percent"
{
  "intents": [
    {
      "intent": "brightness_control",
      "confidence": 0.97,
      "entities": {"action": "set", "level": 40}
    }
  ]
}

User: "Dim the screen"
{
  "intents": [
    {
      "intent": "brightness_control",
      "confidence": 0.95,
      "entities": {"action": "down"}
    }
  ]
}

User: "Mute my microphone"
{
  "intents": [
    {
      "intent": "mic_control",
      "confidence": 0.98,
      "entities": {"action": "mute"}
    }
  ]
}

User: "Unmute mic"
{
  "intents": [
    {
      "intent": "mic_control",
      "confidence": 0.97,
      "entities": {"action": "unmute"}
    }
  ]
}

User: "Play Blinding Lights"
{
  "intents": [
    {
      "intent": "play_music",
      "confidence": 0.98,
      "entities": {"query": "Blinding Lights"}
    }
  ]
}

User: "Play some music"
{
  "intents": [
    {
      "intent": "play_music",
      "confidence": 0.95,
      "entities": {}
    }
  ]
}

User: "Pause the music"
{
  "intents": [
    {
      "intent": "media_control",
      "confidence": 0.98,
      "entities": {"action": "pause"}
    }
  ]
}

User: "Skip to the next song"
{
  "intents": [
    {
      "intent": "media_control",
      "confidence": 0.97,
      "entities": {"action": "next"}
    }
  ]
}

User: "Who won the election?"
{
  "intents": [
    {
      "intent": "web_lookup",
      "confidence": 0.96,
      "entities": {"query": "who won the election"}
    }
  ]
}

User: "Look up the latest news on the mars rover"
{
  "intents": [
    {
      "intent": "web_lookup",
      "confidence": 0.97,
      "entities": {"query": "latest news on the mars rover"}
    }
  ]
}

User: "What's 2 + 2?"
{
  "intents": [
    {
      "intent": "calculator",
      "confidence": 0.99,
      "entities": {"expression": "2+2"}
    }
  ]
}

User: "Good night"
{
  "intents": [
    {
      "intent": "farewell",
      "confidence": 0.97,
      "entities": {}
    }
  ]
}

User: "Bye bye Friday"
{
  "intents": [
    {
      "intent": "farewell",
      "confidence": 0.98,
      "entities": {}
    }
  ]
}

If the request does not clearly match an action,
use "general_chat" as a single intent.

Return JSON only.
"""

    #: Framing that is part of the request, not part of the thing to look up.
    _QUERY_FRAMING = re.compile(
        r"^(?:hey\s+\w+[,\s]+)?(?:can you\s+|could you\s+|please\s+)?"
        r"(?:go\s+)?(?:and\s+)?"
        r"(?:search(?:\s+the\s+web)?(?:\s+for)?|look\s+up|look\s+for|google|"
        r"web\s?search|find\s+out\s+about|find\s+information\s+(?:on|about)|"
        r"tell\s+me\s+about)\s+",
        re.IGNORECASE,
    )

    def _apply_web_lookup_boundary(
        self,
        detected: list[DetectedIntent],
        cleaned_text: str,
    ) -> list[DetectedIntent]:
        """
        Reconcile the model's classification with the explicit boundary.

        A local model is inconsistent about when a question needs the live web:
        left alone it will answer "who won the election" from stale weights and
        then open a tab for "what's 2+2". Two corrections fix both directions:

        * **Demote** a web_lookup the blockers forbid, so no tab opens for
          arithmetic, the clock, the weather, device commands or small talk.
        * **Promote** a general_chat the triggers demand, so the questions the
          user complained about stop being answered from memory.

        Only single-intent results are touched. In a compound request the parts
        constrain each other ("open Chrome AND search for X"), and second
        guessing one leg of it does more harm than good.
        """
        if len(detected) != 1:
            return detected

        item = detected[0]

        # A question about the screen must never become a web search. The
        # local model sends "what does this error mean" to web_lookup roughly
        # half the time, which googles the literal words "this error".
        screen_intent = refers_to_the_screen(cleaned_text)

        # A follow-up names no screen and so matches none of those patterns.
        # It is only recognisable against the turn before it, which the model
        # is never shown, so it always arrives here as general_chat or a web
        # lookup for the literal words "the second one".
        follow_up = screen_intent is None and self._is_screen_follow_up(cleaned_text)
        if follow_up:
            screen_intent = "screen_query"

        if screen_intent is not None and item.intent in {
            "web_lookup",
            "search_web",
            "general_chat",
            "help",
        }:
            item.intent = screen_intent
            item.entities.pop("query", None)
            if screen_intent == "screen_query" and not item.entities.get("question"):
                item.entities["question"] = cleaned_text
            if follow_up:
                item.entities["follow_up"] = True
            return detected

        if item.intent == "web_lookup" and is_web_lookup_blocked(cleaned_text):
            item.intent = "general_chat"
            return detected

        if item.intent == "general_chat" and needs_web_lookup(cleaned_text):
            item.intent = "web_lookup"
            if not item.entities.get("query"):
                item.entities["query"] = self._strip_query_framing(cleaned_text)

        if item.intent == "web_lookup" and not item.entities.get("query"):
            item.entities["query"] = self._strip_query_framing(cleaned_text)

        return detected

    def _strip_query_framing(self, text: str) -> str:
        """Turn "look up the latest mars news" into "the latest mars news"."""
        stripped = self._QUERY_FRAMING.sub("", (text or "").strip()).strip()
        return stripped or (text or "").strip()

    def _parse_llm_response(self, content: str) -> list[dict[str, Any]]:
        """
        Parse the JSON returned by the LLM into a list of raw
        intent dicts.
        """

        content = content.strip()

        # Remove markdown code fences if the model accidentally adds them.
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        result = json.loads(content)

        if not isinstance(result, dict) or "intents" not in result:
            raise ValueError("LLM response missing 'intents' array.")

        intents = result["intents"]

        if not isinstance(intents, list) or not intents:
            raise ValueError("'intents' must be a non-empty JSON array.")

        return intents

    def _fallback(
        self,
        utterance: str,
        parsed_data: dict[str, Any],
    ) -> list[DetectedIntent]:
        """
        Fallback to the old rule-based detector if the LLM fails.
        Always returns a single-item list.
        """

        cleaned_text = parsed_data["normalized_text"]
        entities = dict(parsed_data["entities"])

        intent = self._rule_based_match(cleaned_text)

        # Only the two "I could not place this" outcomes are overridden, so a
        # follow-up never steals an utterance the rules did recognise.
        if intent in {"general_chat", "web_lookup"} and self._is_screen_follow_up(
            cleaned_text
        ):
            intent = "screen_query"
            entities.pop("query", None)
            entities["follow_up"] = True

        confidence = 1.0 if intent != "general_chat" else 0.5

        # The regex entity extractor predates these intents, so fill in the
        # parameters they need from the utterance itself.
        if intent == "web_lookup" and not entities.get("query"):
            entities["query"] = self._strip_query_framing(
                entities.pop("search_query", "") or cleaned_text
            )

        elif intent == "play_music" and not entities.get("query"):
            match = re.match(r"^\s*(?:play|put on)\s+(.*)$", cleaned_text)
            song = (match.group(1).strip() if match else "")
            song = re.sub(r"\b(?:on|in|through)\s+spotify\b", "", song).strip()
            song = re.sub(r"^(?:some|the|a)\s+", "", song).strip()
            if song and song not in {"music", "a song", "song", "something"}:
                entities["query"] = song

        elif intent == "media_control" and not entities.get("action"):
            entities["action"] = self._media_action(cleaned_text)

        elif intent == "screen_query" and not entities.get("question"):
            # The skill answers about the screen, so the user's own words are
            # the question; there is nothing else to extract.
            entities["question"] = cleaned_text

        elif intent == "open_application":
            # "open google chrome" reaches the skill as "google" otherwise,
            # which the website-first guard would open as google.com.
            app = names_an_application(cleaned_text)
            if app:
                entities["application"] = app

        elif intent == "open_website":
            # The regex entity extractor only recognises a site by its TLD, so
            # for "open youtube ..." it guessed `application` instead. Left in
            # place that key routes nothing but still tells ApplicationSkill to
            # go hunting through the Start menu if anything ever reads it.
            entities.pop("application", None)
            named = names_a_website(cleaned_text)
            if named is not None:
                site, query = named
                entities.setdefault("website", site)
                if query:
                    entities["query"] = query
                # names_a_website has already read the whole utterance for a
                # search verb. The extractor's "search_query" is dropped rather
                # than trusted because its pattern fires on the word "google":
                # for "open google maps" it reports a search for "maps".
                entities.pop("search_query", None)
            else:
                # Reached via the domain rule, which extracts no query.
                query = entities.pop("search_query", "")
                if query and not entities.get("query"):
                    entities["query"] = query

        elif intent == "file_search":
            entities.setdefault("action", self._file_action(cleaned_text))
            if not entities.get("target"):
                target = self._file_target(cleaned_text)
                if target:
                    entities["target"] = target

        return [
            DetectedIntent(
                intent=intent,
                confidence=confidence,
                entities=entities,
                raw_utterance=utterance,
            )
        ]

    @staticmethod
    def _file_action(text: str) -> str:
        """Map a file phrase onto a FileSkill action."""
        if re.search(r"\b(?:find|locate|where is|search for|look for)\b", text):
            return "find"
        if re.search(r"\b(?:create|make|new)\b", text):
            return "create"
        return "open"

    @staticmethod
    def _file_target(text: str) -> str:
        """Pull the file's name out of the utterance.

        Everything before the verb and after the noise words is dropped, so
        "open my budget spreadsheet" yields "budget spreadsheet" rather than
        the whole sentence — which would match nothing.
        """
        stripped = re.sub(
            r"^\s*(?:can you|could you|please|hey friday|friday)\s+", "", text
        )
        match = re.search(
            r"\b(?:open|find|locate|search for|look for|where is)\s+"
            r"(?:the\s+|my\s+|a\s+)*(?:file\s+(?:called\s+|named\s+)?)?(.+)$",
            stripped,
        )
        if not match:
            return ""

        target = match.group(1).strip(" .?!")
        # Trailing category words are how the user described it, not part of
        # the name: "budget spreadsheet" still finds budget.xlsx by substring,
        # but "resume file" should not look for a file called "resume file".
        target = re.sub(r"\s+(?:file|document|folder)$", "", target).strip()
        return target

    @staticmethod
    def _media_action(text: str) -> str:
        """Map a transport phrase onto a MediaSkill action."""
        if re.search(r"\b(?:next|skip|forward)\b", text):
            return "next"
        if re.search(r"\b(?:previous|prev|back|go back|last song)\b", text):
            return "previous"
        if re.search(r"\b(?:resume|unpause|continue|keep playing)\b", text):
            return "resume"
        if re.search(r"\bstop\b", text):
            return "stop"
        return "pause"

    def _rule_based_match(self, text: str) -> str:
        """
        Legacy rule-based fallback.
        """

        # Farewells are checked before greetings so that "good night" is not
        # swallowed by the greeting rule, and before the close/quit rule so
        # that "see you later" is not read as closing an application.
        if re.search(
            r"^\s*(?:ok(?:ay)?[,\s]+)?(?:bye bye|bye|goodbye|good bye|"
            r"good night|night night|see you|see ya|"
            r"(?:talk|speak|catch) (?:to |with )?you later|catch you later|"
            r"farewell|adios|later)\b",
            text,
        ):
            return "farewell"

        if re.search(
            r"\b(forget|stop remembering|erase what you know)\b",
            text,
        ):
            return "memory_forget"

        # Screen and file rules come before the generic open/web rules. Left
        # further down, "open my budget spreadsheet" is swallowed by the
        # open_application rule below (which then launches whatever Start menu
        # entry best matches the word "my"), and "what's on my screen" is
        # swallowed by the web-lookup boundary.
        screen_intent = refers_to_the_screen(text)
        if screen_intent is not None:
            return screen_intent

        # A file request must not fall through to open_application: that rule
        # matches "open <any word>" and would launch a Start menu entry.
        if re.search(
            r"\b(find|locate|where is|search for)\b.*\b(file|document|"
            r"folder|resume|spreadsheet|pdf|doc|photo|picture|note)\b",
            text,
        ) or re.search(
            r"\b(open|find|locate)\s+(my|the)\s+\w+\s+"
            r"(file|document|spreadsheet|presentation|pdf|photo|picture)\b",
            text,
        ) or re.search(
            r"\b(open|find)\s+the\s+file\b",
            text,
        ) or re.search(
            # "where is my thesis" names no category, but asking where one's
            # own something is, is a file question far more often than not.
            r"\bwhere('s| is)\s+my\s+\w+",
            text,
        ):
            return "file_search"

        # Transport controls come before the generic open/close rules because
        # "stop the music" would otherwise read as closing an application.
        if re.search(
            r"\b(pause|resume|unpause|skip|next|previous|stop)\b",
            text,
        ) and re.search(r"\b(song|music|track|playback|spotify|tune)\b", text):
            return "media_control"

        if re.search(r"^\s*(?:pause|resume|unpause)\s*$", text):
            return "media_control"

        if re.search(
            r"^\s*(?:play|put on)\b",
            text,
        ) and not re.search(r"\b(video|youtube|movie|film|episode)\b", text):
            return "play_music"

        if re.search(
            r"\b(know about me|remember about me|what do you remember|"
            r"what you know about me)\b",
            text,
        ):
            return "memory_recall"

        if re.search(
            r"\b(weather|temperature|forecast|rain|sunny)\b",
            text,
        ):
            return "weather"

        if re.search(r"\b(news|headlines)\b", text):
            return "news"

        if re.search(r"\b(time is it|current time)\b", text):
            return "time"

        if re.search(
            r"\b(date is it|today's date|what day is it)\b",
            text,
        ):
            return "date"

        if re.search(
            r"\b(calculate|math|\d+\s*\+\s*\d+|\d+\s*-\s*\d+)\b",
            text,
        ):
            return "calculator"

        if re.search(
            r"\b(close|exit|quit)\s+(app|application|program|\w+)\b",
            text,
        ):
            return "close_application"

        # Before the generic open_application rule, which matches "open <any
        # word>" and would send "open youtube" to the Start menu.
        if names_a_website(text) is not None:
            return "open_website"

        if re.search(
            r"\b(go to|open|visit)\s+"
            r"(\w+\.(com|org|net|io|co)|website)\b",
            text,
        ):
            return "open_website"

        if re.search(
            r"\b(open|launch|start)\s+"
            r"(app|application|program|\w+)\b",
            text,
        ):
            return "open_application"

        # The explicit boundary decides this one, so that the fallback path
        # opens Chrome for exactly the same utterances the LLM path does.
        if needs_web_lookup(text) and not re.search(r"\b(file|folder)\b", text):
            return "web_lookup"

        if re.search(
            r"\b(volume|mute|unmute|brightness|shutdown|restart|sleep|lock)\b",
            text,
        ):
            return "system_control"

        if re.search(
            r"\b(create|delete|move|copy|rename)\b",
            text,
        ) and re.search(r"\b(file|folder|directory)\b", text):
            return "file_operation"

        if re.search(
            r"\b(screenshot|take a picture of the screen|screen capture)\b",
            text,
        ):
            return "screenshot"

        if re.search(
            r"\b(clipboard|copy to clipboard|paste)\b",
            text,
        ):
            return "clipboard"

        if re.search(
            r"\b(note|take a note|write down|jot down)\b",
            text,
        ):
            return "notes"

        if re.search(
            r"\b(remind|reminder|set a timer|alarm)\b",
            text,
        ):
            return "reminder"

        if re.search(
            r"\b(help|what can you do|commands)\b",
            text,
        ):
            return "help"

        if re.search(
            r"\b(hello|hi|hey|greetings)\b",
            text,
        ):
            return "greeting"

        return "general_chat"

    def is_actionable(self, intent: DetectedIntent) -> bool:
        """
        Check whether a single detected intent meets the confidence
        threshold. Call per-item on the list returned by detect().
        """
        return intent.confidence >= self.confidence_threshold