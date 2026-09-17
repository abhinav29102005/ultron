"""
intelligence/agent_loop.py – The tool-calling turn
===================================================
What replaces one-shot intent classification.

The old turn was: classify the utterance into one of 29 intents, look the
intent up in a table, run that one skill, speak the result. It worked for
"what's the time" and broke for everything else, because the model had to
choose exactly one bucket for a sentence that might mean several things or
none of them. "Fix the bug in my code" has no bucket, so it landed in
``search_web`` and ULTRON googled the word "error".

The new turn is: hand the model typed tools, let it call them -- none, one, or
several, over as many rounds as it needs -- and speak whatever it says once it
stops calling them.

Four things make this safe in front of a live microphone:

  * **it stops.** A step budget and a wall-clock budget, because a model that
    keeps calling tools holds the mic open and the user cannot interrupt a
    turn that never ends;
  * **it fails soft.** A bad tool name, bad arguments, or a skill that raises
    all come back to the model as text it can read and retry from. Nothing in
    a tool call is allowed to end the conversation;
  * **it asks first.** Tools marked ``confirm`` in the registry -- writing a
    file, closing an app -- do not run until the user says yes, and if there
    is no way to ask, they do not run at all;
  * **it degrades.** A provider that cannot call tools raises
    :class:`~llm.tools.ToolsUnsupportedError`, and the caller falls back to
    the classifier pipeline that is still there.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

from config.logging_config import get_logger
from llm.tools import ToolCall, ToolCallResponse, ToolsUnsupportedError

if TYPE_CHECKING:
    from llm.base import BaseLLM

logger = get_logger("agent")

#: Tool calls allowed in one turn.
#:
#: Twelve. Six covered "look, then act"; the verified fix loop is read the
#: error, copy to a shadow, then edit-run-check repeatedly, then apply. A
#: budget that cuts that off mid-way is worse than no loop at all.
DEFAULT_MAX_STEPS = 12

#: Wall-clock ceiling for the whole turn, in seconds.
#:
#: Generous because one legitimate tool (``research``) is itself a 45-second
#: budget. This is the backstop against a wedged turn, not a latency target.
DEFAULT_TIME_BUDGET = 120.0

#: What the user hears when the budget runs out mid-chain.
BUDGET_MESSAGE = (
    "I got partway through that but ran out of steps. Ask me again and I'll "
    "pick up from what I found."
)

#: What the user hears when the model stops without saying anything.
EMPTY_MESSAGE = "I've done that."

#: Consecutive identical calls tolerated before the loop stops running the
#: tool and tells the model instead.
#:
#: Two, so the first repeat still executes -- re-reading a file after an
#: edit is legitimate -- and the third is answered with a nudge.
REPEAT_LIMIT = 2


#: The agent's instructions.
#:
#: Written plainly on purpose. An earlier version used emphatic capitalised
#: words for emphasis -- "answered by LOOKING" -- and qwen2.5:3b replied with
#: the single word "LOOKING" on three runs out of three, calling no tools at
#: all. A small model quotes what stands out instead of following it. So:
#: no capitalised emphasis, no metaphors, and the fix procedure written as a
#: numbered recipe, because a numbered list is the one structure these models
#: reliably execute in order.
SYSTEM_PROMPT = """You are ULTRON, a voice assistant on the user's Windows laptop.

Use tools to do things. Do not describe what you would do, and do not answer from memory when a tool can check.

Questions about the user's screen, files, or code are answered with get_active_window, read_screen_text, and read_file. The web cannot answer them. The research tool is only for the outside world: news, prices, facts, documentation.

To fix a bug or an error:
1. Find the error text. Use read_screen_text if it is on screen, or clipboard if they copied it.
2. Find the file. get_active_window usually names it. Then read_file to see the code.
3. Call copy_to_shadow on that file. You will experiment on the copy it returns.
4. Call edit_file on the copy to make your fix.
5. Call run_command to run the copy and read the output.
6. If it is still wrong, go back to step 4 and try again. Stop after four attempts.
7. When it works, call edit_file on the real file with the same change.

Never put code in your reply. Code goes through edit_file. If you have not run the fix, say that you have not.

Your reply is read aloud. Use one to three short sentences. No markdown, no bullet points, no code, no long file paths. Say what you did, not which tools you used. If something failed, say so in one sentence."""


class Dispatcher(Protocol):
    """What the loop needs from whatever actually runs a tool."""

    async def run(self, call: ToolCall) -> str: ...
    def is_known(self, name: str) -> bool: ...
    def needs_confirmation(self, name: str) -> bool: ...


#: ``async def confirm(prompt) -> bool``. None means there is no way to ask.
Confirmer = Callable[[str], Awaitable[bool]]


@dataclass
class AgentResult:
    """The outcome of one turn."""

    text: str
    tools_used: list[str] = field(default_factory=list)
    steps: int = 0
    #: True when the turn was cut short by a budget rather than finishing.
    hit_budget: bool = False


class AgentLoop:
    """Run one user utterance to an answer, calling tools as needed."""

    def __init__(
        self,
        llm: BaseLLM,
        dispatcher: Dispatcher,
        *,
        tools: list[dict] | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        time_budget: float = DEFAULT_TIME_BUDGET,
        confirm: Confirmer | None = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.llm = llm
        self.dispatcher = dispatcher
        self.max_steps = max_steps
        self.time_budget = time_budget
        self.confirm = confirm
        self.system_prompt = system_prompt

        if tools is None:
            from intelligence.tool_registry import schemas

            tools = schemas()
        self.tools = tools

    def _prompt_with_background(self, history: list[dict[str, str]] | None) -> str:
        """Fold earlier turns into the system prompt, marked as already done.

        Not appended as chat messages, which is what this used to do. A past
        "open youtube" sitting in the user channel is indistinguishable from
        a request the model has yet to carry out, and it acts on it: asked
        "open google.com" with that one line of history, qwen3:4b-instruct
        opened YouTube and *not* Google in 3 runs out of 3. The user sees the
        wrong tab, or -- when the model instead copies the previous reply --
        a confident "Google.com is now open" and no tab at all.

        Measured, three runs each, "open google.com" after "open youtube":

            history as user messages   google 0/3, stale youtube 3
            labelled system context    google 3/3, stale youtube 0
            no history at all          google 3/3, stale youtube 0

        The middle one is chosen because it also keeps the context that lets
        a follow-up like "and the other one?" resolve at all.
        """
        lines = [
            (turn.get("content") or "").strip()
            for turn in (history or [])
            if (turn.get("content") or "").strip()
        ]
        if not lines:
            return self.system_prompt

        earlier = "\n".join(f"- {line}" for line in lines)
        return (
            f"{self.system_prompt}\n\n"
            "For context only, these are things the user said earlier in this "
            "conversation:\n"
            f"{earlier}\n"
            "They are a record of what was said, not a queue of work: never "
            "act on one of them on its own. Carry out the new request below, "
            "using the list only to resolve what a phrase like \"the other "
            "one\" refers to. If the new request repeats an earlier one, "
            "carry it out again -- the user is allowed to ask twice."
        )

    async def run(
        self,
        utterance: str,
        history: list[dict[str, str]] | None = None,
    ) -> AgentResult:
        """Answer ``utterance``, calling tools until the model stops asking.

        Raises :class:`ToolsUnsupportedError` when the provider cannot do
        function calling, so the caller can fall back.
        """
        deadline = time.monotonic() + self.time_budget

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._prompt_with_background(history)},
        ]
        messages.append({"role": "user", "content": utterance})

        tools_used: list[str] = []
        steps = 0
        #: The last call executed, to notice a model going round in circles.
        last_signature: tuple[str, str] | None = None
        repeats = 0

        # Fast-path for pure conversational greetings: omitting 46 tool definitions
        # cuts initial token overhead and drops TTFT to under 500ms.
        import re
        is_pure_smalltalk = bool(re.match(
            r"^\s*(?:hi|hello|hey|yo|sup|how are you|how'?s it going|what'?s up|"
            r"good (?:morning|afternoon|evening|night)|who are you)\s*[.?!]*$",
            utterance,
            re.IGNORECASE,
        ))

        while True:
            active_tools = [] if (is_pure_smalltalk and steps == 0) else self.tools
            response = await self.llm.complete_with_tools(messages, active_tools)

            if not isinstance(response, ToolCallResponse):
                # A provider that returned plain text where a structured
                # response was expected is still usable -- take the text.
                return AgentResult(text=str(response), tools_used=tools_used, steps=steps)

            if not response.wants_tools:
                text = (response.content or "").strip() or EMPTY_MESSAGE
                return AgentResult(text=text, tools_used=tools_used, steps=steps)

            # The assistant's tool-call turn has to be in the transcript before
            # its results are, or the provider rejects the tool messages as
            # replies to nothing.
            messages.append(self._assistant_turn(response))

            for call in response.tool_calls:
                if steps >= self.max_steps or time.monotonic() >= deadline:
                    logger.info(f"Agent budget reached after {steps} tool calls")
                    return AgentResult(
                        text=self._budget_text(response),
                        tools_used=tools_used,
                        steps=steps,
                        hit_budget=True,
                    )

                steps += 1

                # A model repeating one call verbatim is stuck: the result is
                # identical every time, so the transcript grows without telling
                # it anything new and nothing pushes it to change course. Seen
                # live as six consecutive list_directory calls that ate the
                # whole budget. Saying so is usually enough for it to recover
                # within the same turn.
                signature = (call.name, json.dumps(call.arguments, sort_keys=True))
                repeats = repeats + 1 if signature == last_signature else 0
                last_signature = signature

                if repeats >= REPEAT_LIMIT:
                    logger.info(f"Model repeated {call.name}; nudging instead of rerunning.")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": (
                                f"You have already called {call.name} with these "
                                f"exact arguments and got the same answer. Do not "
                                f"call it again. Use what you already have, try a "
                                f"different tool, or tell the user what is blocking you."
                            ),
                        }
                    )
                    continue

                output = await self._run_one(call)
                if output.ran:
                    tools_used.append(call.name)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": output.text,
                    }
                )

            # Direct return fast-path: for single query/action tools that produced a complete,
            # human-readable message, return immediately without burning 5-10s on a redundant LLM pass.
            DIRECT_RETURN_TOOLS = {
                "get_weather", "weather", "system_weather",
                "calculate",
                "take_screenshot", "set_volume", "set_brightness", "set_microphone",
                "play_music", "control_media", "open_application", "close_application",
                "open_website", "open_folder", "add_note", "list_notes",
                "set_reminder", "list_reminders", "cancel_reminder", "end_session"
            }
            if (
                len(response.tool_calls) == 1
                and response.tool_calls[0].name in DIRECT_RETURN_TOOLS
                and output.ran
                and not output.text.startswith("Error")
            ):
                return AgentResult(text=output.text, tools_used=tools_used, steps=steps)

    # ── one tool call ─────────────────────────────────────────────────────

    @dataclass
    class _Outcome:
        text: str
        ran: bool

    async def _run_one(self, call: ToolCall) -> _Outcome:
        """Execute one call, converting every failure into readable text.

        Nothing in here raises. A model that picked a bad tool or bad
        arguments gets told what went wrong and can try something else; an
        exception would instead end the turn and leave the user with
        "something went wrong".
        """
        if not self.dispatcher.is_known(call.name):
            logger.warning(f"Model called unknown tool: {call.name}")
            return self._Outcome(
                text=(
                    f"Error: unknown tool '{call.name}'. It does not exist. "
                    f"Use one of the tools you were given, or answer without one."
                ),
                ran=False,
            )

        if self.dispatcher.needs_confirmation(call.name):
            approved = await self._ask(call)
            if not approved:
                return self._Outcome(
                    text=(
                        f"The user did not approve {call.name}. Do not try it "
                        f"again; tell them it was not done."
                    ),
                    ran=False,
                )

        try:
            result = await self.dispatcher.run(call)
        except asyncio.CancelledError:
            # A barge-in. Must propagate: the user is talking over us.
            raise
        except Exception as exc:
            logger.warning(f"Tool {call.name} failed: {exc}")
            return self._Outcome(text=f"Error running {call.name}: {exc}", ran=False)

        return self._Outcome(text=str(result), ran=True)

    async def _ask(self, call: ToolCall) -> bool:
        """Get the user's consent for a destructive call.

        No confirmer means no channel to ask on, which fails closed. Silently
        proceeding would let a misheard sentence overwrite a file.
        """
        if self.confirm is None:
            logger.info(f"No confirmation channel; declining {call.name}")
            return False

        try:
            return bool(await self.confirm(self._confirmation_prompt(call)))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Confirmation failed for {call.name}: {exc}")
            return False

    @staticmethod
    def _confirmation_prompt(call: ToolCall) -> str:
        """A one-line description of what is about to happen, for speaking.

        Deliberately concrete: "write 40 lines to app.py" rather than "run
        write_file", because the user is being asked to consent to the effect,
        not to the mechanism.
        """
        if call.name == "write_file":
            path = call.arguments.get("path", "a file")
            lines = len(str(call.arguments.get("content", "")).splitlines())
            return f"Write {lines} lines to {path}?"
        if call.name == "close_application":
            return f"Close {call.arguments.get('application', 'that application')}?"

        arguments = ", ".join(f"{k}={v!r}" for k, v in call.arguments.items())
        return f"Run {call.name}({arguments})?"

    # ── transcript helpers ────────────────────────────────────────────────

    @staticmethod
    def _assistant_turn(response: ToolCallResponse) -> dict[str, Any]:
        """The assistant message carrying the tool calls, echoed back.

        ``arguments`` stays a **dict** here — the neutral Python form. The two
        providers genuinely disagree about this one field: Ollama's Message
        model validates it as a dict and rejects a string, while OpenAI's API
        specifies a JSON string. Serialising here would break Ollama, so the
        OpenAI-compatible provider converts on the way out instead and the
        loop stays provider-agnostic.

        This only bites on the second round trip, when the first round's calls
        are replayed — which is why it survived every unit test and turned up
        the first time the real loop ran two rounds.
        """
        return {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": dict(call.arguments),
                    },
                }
                for call in response.tool_calls
            ],
        }

    @staticmethod
    def _budget_text(response: ToolCallResponse) -> str:
        """What to say when the turn is cut short.

        If the model narrated before its last tool call, that narration is a
        better thing to say than a generic apology.
        """
        return (response.content or "").strip() or BUDGET_MESSAGE
