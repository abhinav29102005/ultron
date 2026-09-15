"""
Tests for the tool-calling layer (llm/tools.py, intelligence/tool_registry.py).

Why this exists: FRIDAY classified every utterance into one of 29 fixed
intents with a single 3B-model call. Anything outside those buckets -- "fix
the bug in my code", "open youtube and search MKBHD" -- was forced into the
nearest wrong one, which is how a request to fix code became a web search for
"error".

Tool calling replaces that. The model is handed typed tools and picks them,
possibly several in sequence, instead of labelling a sentence.

Nothing here touches a network or a real model.
"""

from __future__ import annotations

import pytest

from llm.tools import ToolCall, ToolDef


class TestToolSchema:
    """A ToolDef has to serialise to the schema both providers expect.

    OpenAI (and therefore NVIDIA NIM, which is OpenAI-compatible) and Ollama
    both take the same ``{"type": "function", "function": {...}}`` shape, so
    there is one serialiser rather than one per provider.
    """

    def _tool(self, **overrides):
        base = dict(
            name="set_volume",
            description="Set the system volume to a percentage.",
            intent="system_control",
            properties={"level": {"type": "integer", "description": "0-100"}},
            required=("level",),
        )
        base.update(overrides)
        return ToolDef(**base)

    def test_schema_is_a_function_envelope(self):
        schema = self._tool().to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "set_volume"
        assert schema["function"]["description"].startswith("Set the system volume")

    def test_parameters_are_a_json_schema_object(self):
        params = self._tool().to_schema()["function"]["parameters"]
        assert params["type"] == "object"
        assert params["properties"]["level"]["type"] == "integer"
        assert params["required"] == ["level"]

    def test_a_tool_with_no_arguments_still_has_an_object_schema(self):
        """Providers reject a function whose parameters are absent or a bare type."""
        params = self._tool(properties={}, required=()).to_schema()["function"]["parameters"]
        assert params == {"type": "object", "properties": {}, "required": []}

    def test_confirmation_defaults_to_off(self):
        assert self._tool().confirm is False


class TestToolCallParsing:
    """Providers hand back arguments as a JSON *string*; Ollama as a dict."""

    def test_arguments_arrive_as_a_dict(self):
        call = ToolCall(id="1", name="set_volume", arguments={"level": 40})
        assert call.arguments["level"] == 40

    def test_a_json_string_is_decoded(self):
        call = ToolCall.from_raw(id="1", name="set_volume", arguments='{"level": 40}')
        assert call.arguments == {"level": 40}

    def test_malformed_arguments_become_empty_rather_than_raising(self):
        """A model that emits broken JSON must not crash the turn."""
        call = ToolCall.from_raw(id="1", name="set_volume", arguments="{level: 40")
        assert call.arguments == {}

    def test_a_dict_passes_through_unchanged(self):
        call = ToolCall.from_raw(id="1", name="set_volume", arguments={"level": 40})
        assert call.arguments == {"level": 40}


class TestRegistry:
    """The registry is the bridge from a tool name back to the existing skills."""

    def test_every_tool_maps_to_a_routable_intent(self):
        """A tool whose intent is not in the routing table would silently
        execute as DefaultSkill -- the model would call it and nothing would
        happen."""
        from intelligence.router import TaskRouter
        from intelligence.tool_registry import ALL_TOOLS

        unroutable = [t.name for t in ALL_TOOLS if t.intent not in TaskRouter.ROUTING_TABLE]
        assert unroutable == []

    def test_tool_names_are_unique(self):
        from intelligence.tool_registry import ALL_TOOLS

        names = [t.name for t in ALL_TOOLS]
        assert len(names) == len(set(names))

    def test_the_core_capabilities_are_all_exposed(self):
        """If a capability has no tool the model cannot reach it at all."""
        from intelligence.tool_registry import ALL_TOOLS

        names = {t.name for t in ALL_TOOLS}
        for expected in (
            "open_application",
            "set_volume",
            "describe_screen",
            "read_screen_text",
            "research",
            "read_file",
            "write_file",
            "get_time",
            # W5: the three DefaultSkill stubs, now real.
            "add_note",
            "list_notes",
            "set_reminder",
            "list_reminders",
            # W3: browser and desktop control.
            "browser_open",
            "browser_click",
            "browser_type",
            "browser_read",
            "focus_window",
            "press_keys",
            # W6: the verified fix loop.
            "edit_file",
            "run_command",
            "copy_to_shadow",
        ):
            assert expected in names, f"no tool named {expected}"

    def test_destructive_tools_require_confirmation(self):
        """Writing a file or closing an app is not undoable by voice."""
        from intelligence.tool_registry import TOOLS_BY_NAME

        for name in (
            "write_file",
            "close_application",
            # W3: these act on the user's real machine and real logged-in
            # browser session. A misheard sentence must not click "Delete".
            "browser_click",
            "browser_type",
            "press_keys",
            # Changing a real file the user has open is not undoable by voice.
            "edit_file",
        ):
            assert TOOLS_BY_NAME[name].confirm is True, f"{name} must be confirmed"

    def test_read_only_tools_do_not_require_confirmation(self):
        from intelligence.tool_registry import TOOLS_BY_NAME

        # run_command and copy_to_shadow are the *read* half of the fix
        # loop: they run code that already exists and copy it aside. Making
        # them confirmed would mean a spoken yes for every iteration.
        for name in (
            "get_time",
            "read_file",
            "describe_screen",
            "run_command",
            "copy_to_shadow",
        ):
            assert TOOLS_BY_NAME[name].confirm is False
