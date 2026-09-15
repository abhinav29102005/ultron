"""
Tests for intelligence/tool_dispatcher.py – running a tool call.

The dispatcher is the join between the new agent loop and everything FRIDAY
already does. A tool call becomes an ordinary Task with the tool's intent, and
that Task goes through the existing router and executor untouched. That is the
whole point of the design: no skill had to be rewritten to become callable.

The one piece of real work here is argument naming. Tool schemas are written
for the model to read ("path", "query"), while some skills predate them and
read something else ("folder_name", "target"). Rather than rename either side,
the dispatcher forwards both.
"""

from __future__ import annotations

import pytest

from intelligence.tool_dispatcher import ToolDispatcher
from llm.tools import ToolCall


class FakeExecutor:
    def __init__(self, result="ok", success=True):
        self.tasks = []
        self._result = result
        self._success = success

    async def execute(self, task):
        self.tasks.append(task)
        task.result = self._result
        return self._success, self._result


class FakeRouter:
    """Stands in for TaskRouter: records, and populates skill_name."""

    def __init__(self):
        self.routed = []

    async def route(self, tasks):
        self.routed.extend(tasks)
        for task in tasks:
            task.skill_name = f"skill_for_{task.intent}"
        return tasks


class FakeContainer:
    def __init__(self):
        self.router = FakeRouter()
        self.executor = FakeExecutor()
        self.llm = object()


@pytest.fixture
def container():
    return FakeContainer()


class TestKnownTools:
    def test_registry_tools_are_known(self, container):
        d = ToolDispatcher(container)
        assert d.is_known("read_file") is True
        assert d.is_known("research") is True

    def test_an_invented_name_is_not_known(self, container):
        assert ToolDispatcher(container).is_known("hack_the_mainframe") is False

    def test_confirmation_comes_from_the_registry(self, container):
        d = ToolDispatcher(container)
        assert d.needs_confirmation("write_file") is True
        assert d.needs_confirmation("read_file") is False

    def test_an_unknown_tool_never_needs_confirmation(self, container):
        """It is refused before it gets that far; this must not raise."""
        assert ToolDispatcher(container).needs_confirmation("nope") is False


class TestDispatch:
    @pytest.mark.asyncio
    async def test_the_tools_intent_becomes_the_tasks_intent(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="read_file", arguments={"path": "a.py"})
        )
        assert container.router.routed[0].intent == "read_file"

    @pytest.mark.asyncio
    async def test_arguments_become_task_parameters(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="read_file", arguments={"path": "a.py"})
        )
        assert container.executor.tasks[0].parameters["path"] == "a.py"

    @pytest.mark.asyncio
    async def test_the_result_is_returned_as_text(self, container):
        container.executor = FakeExecutor(result="file contents here")
        out = await ToolDispatcher(container).run(
            ToolCall(id="1", name="read_file", arguments={"path": "a.py"})
        )
        assert out == "file contents here"

    @pytest.mark.asyncio
    async def test_a_failing_skill_comes_back_as_text_not_an_exception(self, container):
        """The agent loop shows this to the model, which can then try
        something else. An exception would end the turn."""
        container.executor = FakeExecutor(result="no such file", success=False)

        out = await ToolDispatcher(container).run(
            ToolCall(id="1", name="read_file", arguments={"path": "/nope"})
        )

        assert "no such file" in out

    @pytest.mark.asyncio
    async def test_an_unknown_tool_is_refused(self, container):
        out = await ToolDispatcher(container).run(
            ToolCall(id="1", name="not_a_tool", arguments={})
        )
        assert "unknown" in out.lower()
        assert container.executor.tasks == []

    @pytest.mark.asyncio
    async def test_the_task_carries_a_raw_utterance_for_skills_that_want_one(
        self, container
    ):
        """ChatSkill and the research skill read raw_utterance; a task built
        from a tool call has no utterance unless one is threaded through."""
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="research", arguments={"query": "python 3.13 news"}),
            utterance="what's new in python",
        )
        task = container.executor.tasks[0]
        assert task.metadata["raw_utterance"] == "what's new in python"


class TestArgumentAliases:
    """Tool argument names are written for the model; some skills predate them."""

    @pytest.mark.asyncio
    async def test_open_folder_path_reaches_folder_skill_as_folder_name(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="open_folder", arguments={"path": "Downloads"})
        )
        params = container.executor.tasks[0].parameters
        assert params["folder_name"] == "Downloads"
        assert params["path"] == "Downloads", "the original name is kept too"

    @pytest.mark.asyncio
    async def test_recall_memory_query_reaches_memory_skill_as_target(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="recall_memory", arguments={"query": "my sister"})
        )
        assert container.executor.tasks[0].parameters["target"] == "my sister"

    @pytest.mark.asyncio
    async def test_find_file_query_reaches_file_skill_as_target(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="find_file", arguments={"query": "budget.xlsx"})
        )
        assert container.executor.tasks[0].parameters["target"] == "budget.xlsx"

    @pytest.mark.asyncio
    async def test_an_alias_does_not_overwrite_a_value_the_model_supplied(
        self, container
    ):
        await ToolDispatcher(container).run(
            ToolCall(
                id="1",
                name="open_folder",
                arguments={"path": "Downloads", "folder_name": "Documents"},
            )
        )
        assert container.executor.tasks[0].parameters["folder_name"] == "Documents"


class TestEveryToolIsDispatchable:
    @pytest.mark.asyncio
    async def test_every_registered_tool_builds_and_routes_a_task(self, container):
        """A tool the model can see but the dispatcher cannot run is a trap:
        the model calls it and nothing happens."""
        from intelligence.tool_registry import ALL_TOOLS

        dispatcher = ToolDispatcher(container)
        for tool in ALL_TOOLS:
            await dispatcher.run(ToolCall(id="x", name=tool.name, arguments={}))

        assert len(container.executor.tasks) == len(ALL_TOOLS)


class TestFixedParameters:
    """Several tools share one intent and differ only by action.

    NotesSkill handles add/list/search behind the single ``notes`` intent, so
    add_note and list_notes both route there. Without the action pinned to the
    tool, the skill falls back to its default -- and "what notes do I have"
    answered "what would you like me to note down?", which is exactly what
    happened live.
    """

    @pytest.mark.asyncio
    async def test_listing_notes_asks_the_skill_to_list(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="list_notes", arguments={})
        )
        assert container.executor.tasks[0].parameters["action"] == "list"

    @pytest.mark.asyncio
    async def test_adding_a_note_asks_the_skill_to_add(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="add_note", arguments={"text": "buy milk"})
        )
        params = container.executor.tasks[0].parameters
        assert params["action"] == "add"
        assert params["text"] == "buy milk"

    @pytest.mark.asyncio
    async def test_listing_reminders_asks_the_skill_to_list(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="list_reminders", arguments={})
        )
        assert container.executor.tasks[0].parameters["action"] == "list"

    @pytest.mark.asyncio
    async def test_cancelling_a_reminder_asks_the_skill_to_cancel(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="cancel_reminder", arguments={"query": "oven"})
        )
        assert container.executor.tasks[0].parameters["action"] == "cancel"

    @pytest.mark.asyncio
    async def test_reading_the_clipboard_asks_the_skill_to_read(self, container):
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="clipboard", arguments={"action": "read"})
        )
        assert container.executor.tasks[0].parameters["action"] == "read"

    @pytest.mark.asyncio
    async def test_a_model_supplied_action_is_not_overridden(self, container):
        """A fixed default fills a gap; it does not veto the model."""
        await ToolDispatcher(container).run(
            ToolCall(id="1", name="add_note", arguments={"action": "search", "text": "milk"})
        )
        assert container.executor.tasks[0].parameters["action"] == "search"
