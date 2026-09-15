"""
llm/tools.py – Tool definitions for function calling
=====================================================
The vocabulary the agent loop speaks in.

ULTRON used to classify each utterance into one of 29 fixed intents with a
single model call. That works for "what's the time" and falls apart for
anything compound or unanticipated: the model had to pick one bucket, so
"fix the bug in my code" landed in ``search_web`` and ULTRON googled "error".

A tool call is the same information with the shape inverted. Instead of
asking the model to *name* what the user wants, we hand it typed capabilities
and let it *use* them -- one, several, or none, in whatever order the request
actually needs.

Both providers take the same wire format. NVIDIA NIM is OpenAI-compatible, and
Ollama's ``chat(tools=...)`` accepts the OpenAI function envelope verbatim, so
there is a single serialiser here rather than one per provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolDef:
    """One capability the model may invoke.

    ``intent`` is the bridge back to the existing pipeline: executing a tool
    builds a :class:`~intelligence.task.Task` with this intent and runs it
    through the ordinary router and executor. Every skill ULTRON already has
    keeps working unchanged -- the agent loop replaces how a skill is *chosen*,
    not what skills do.
    """

    name: str
    description: str
    #: The routing-table intent this tool dispatches to.
    intent: str
    #: JSON Schema properties, by argument name.
    properties: dict[str, Any] = field(default_factory=dict)
    #: Argument names the model must supply.
    required: tuple[str, ...] = ()
    #: True when the action is not undoable by voice and the user has to be
    #: asked first. Writing a file and closing an app qualify; reading the
    #: clock does not.
    confirm: bool = False
    #: Parameters set on every call of this tool, whatever the model sends.
    #:
    #: Several tools share one intent and differ only by what they ask the
    #: skill to do: add_note and list_notes both route to ``notes``, and
    #: NotesSkill reads an ``action`` to tell them apart. The model is not
    #: asked to supply that -- the tool it chose already says which it meant.
    #: A value the model *does* send wins, so this fills a gap rather than
    #: vetoing a deliberate choice.
    fixed: dict[str, Any] = field(default_factory=dict)
    #: Extra parameter names to copy an argument into, ``{argument: alias}``.
    #:
    #: Tool arguments are named for the model to read ("path", "query") while
    #: some skills predate the tools and read something else ("folder_name",
    #: "target"). Renaming either side would break the other, so the argument
    #: is simply forwarded under both names.
    aliases: dict[str, str] = field(default_factory=dict)

    def to_schema(self) -> dict[str, Any]:
        """The OpenAI/Ollama function envelope for this tool.

        ``parameters`` is always a complete JSON Schema object even when the
        tool takes no arguments -- providers reject a function whose parameter
        block is missing or is a bare type name.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": dict(self.properties),
                    "required": list(self.required),
                },
            },
        }


@dataclass(frozen=True)
class ToolCall:
    """One invocation the model asked for."""

    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_raw(cls, id: str, name: str, arguments: Any) -> ToolCall:
        """Build from whatever the provider handed back.

        OpenAI-compatible endpoints return the arguments as a JSON *string*;
        Ollama returns a dict already. A model can also emit malformed JSON,
        and when it does the turn must continue -- the tool simply runs with no
        arguments and the skill reports what it needed, which the model can
        read and retry. Raising here would kill the whole conversation over a
        missing brace.
        """
        if isinstance(arguments, dict):
            decoded = arguments
        else:
            try:
                decoded = json.loads(arguments or "{}")
            except (TypeError, ValueError):
                decoded = {}

        if not isinstance(decoded, dict):
            decoded = {}

        return cls(id=id, name=name, arguments=decoded)


@dataclass
class ToolCallResponse:
    """What the model returned: either text, or tools it wants run.

    Both fields can be populated at once -- some models narrate ("Let me check
    that for you") in the same turn they call a tool.
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class ToolsUnsupportedError(RuntimeError):
    """Raised by a provider that cannot do function calling.

    The agent loop catches this and falls back to the classifier pipeline, so
    a model without tool support degrades to the old behaviour rather than
    failing the turn.
    """
