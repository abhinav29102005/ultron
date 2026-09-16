"""
tests/test_memory.py – Context Memory Tests
=============================================
Contains unit tests for MemoryStore, FactExtractor, MemoryService and
MemorySkill. Every test writes into tmp_path so the real store is untouched.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from intelligence.task import Task, TaskStatus
from llm.mock import MockLLM
from memory.extractor import FactExtractor
from memory.models import MemoryFact, from_dict, to_dict
from memory.service import MemoryService
from memory.store import MemoryStore
from skills.memory_skills import MemorySkill


# ── Helpers ──

def make_task(intent: str, parameters: dict[str, Any] | None = None) -> Task:
    """Build a routed-looking Task for a skill under test."""
    return Task(
        task_id=str(uuid.uuid4()),
        skill_name="MemorySkill",
        intent=intent,
        parameters=parameters or {},
        status=TaskStatus.READY_FOR_EXECUTION,
        result=None,
        error=None,
        created_at=datetime.utcnow(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


class StubContainer:
    """Minimal stand-in exposing only the `memory` property skills read."""

    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory


def make_service(tmp_path: Path, llm: MockLLM | None = None, **kwargs: Any) -> MemoryService:
    """Build a MemoryService backed by a store inside tmp_path."""
    store = MemoryStore(path=tmp_path / "memory.json", max_facts=kwargs.pop("max_facts", 200))
    extractor = FactExtractor(llm=llm or MockLLM(default_response='{"facts": []}'))
    return MemoryService(store=store, extractor=extractor, **kwargs)


# ── MemoryFact Serialisation Tests ──

class TestMemoryFactSerialisation:
    """Tests for the MemoryFact JSON helpers."""

    def test_round_trip(self) -> None:
        now = datetime(2026, 8, 19, 12, 30, 45)
        fact = MemoryFact(
            key="name",
            value="Ola",
            source_utterance="my name is Ola",
            created_at=now,
            updated_at=now,
        )

        payload = to_dict(fact)
        assert payload["created_at"] == now.isoformat()

        # Must survive an actual JSON encode/decode, not just a dict copy.
        restored = from_dict(json.loads(json.dumps(payload)))
        assert restored == fact


# ── MemoryStore Tests ──

class TestMemoryStore:
    """Tests for the on-disk fact store."""

    def test_upsert_then_read_back(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json")
        store.upsert("name", "Ola", "my name is Ola")

        facts = store.all()
        assert len(facts) == 1
        assert facts[0].key == "name"
        assert facts[0].value == "Ola"
        assert facts[0].source_utterance == "my name is Ola"

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"

        first = MemoryStore(path=path)
        first.upsert("name", "Ola", "my name is Ola")
        first.upsert("favourite_editor", "VS Code", "I use VS Code")

        # A brand-new instance reads the file cold: this is the restart case.
        second = MemoryStore(path=path)
        recalled = {fact.key: fact.value for fact in second.all()}

        assert recalled == {"name": "Ola", "favourite_editor": "VS Code"}

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deeper" / "memory.json"
        store = MemoryStore(path=path)
        store.upsert("name", "Ola", "my name is Ola")

        assert path.exists()

    def test_upsert_overwrites_in_place(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json")

        original = store.upsert("name", "Ola", "my name is Ola")
        created_at = original.created_at
        updated_at = original.updated_at

        corrected = store.upsert("name", "Olamide", "actually my name is Olamide")

        facts = store.all()
        assert len(facts) == 1, "A correction must supersede, not duplicate."
        assert facts[0].value == "Olamide"
        assert facts[0].source_utterance == "actually my name is Olamide"
        assert corrected.created_at == created_at
        assert corrected.updated_at >= updated_at

    def test_all_is_newest_updated_first(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json")
        store.upsert("first", "one", "u1")
        store.upsert("second", "two", "u2")
        store.upsert("first", "one again", "u3")

        assert [fact.key for fact in store.all()] == ["first", "second"]

    def test_key_normalisation(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json")

        store.upsert("  Favourite Editor  ", "VS Code", "u1")
        store.upsert("favourite-editor", "Neovim", "u2")

        facts = store.all()
        assert len(facts) == 1
        assert facts[0].key == "favourite_editor"
        assert facts[0].value == "Neovim"

    def test_delete_hit_and_miss(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json")
        store.upsert("name", "Ola", "u1")

        assert store.delete("Name") is True
        assert store.delete("name") is False
        assert store.all() == []

    def test_delete_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.upsert("name", "Ola", "u1")
        store.delete("name")

        assert MemoryStore(path=path).all() == []

    def test_find_matches_key_and_value_case_insensitively(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json")
        store.upsert("favourite_editor", "VS Code", "u1")
        store.upsert("location", "Lagos", "u2")

        assert [fact.key for fact in store.find("EDITOR")] == ["favourite_editor"]
        assert [fact.key for fact in store.find("lagos")] == ["location"]
        assert store.find("nothing here") == []
        assert store.find("   ") == []

    def test_clear(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.upsert("name", "Ola", "u1")
        store.upsert("location", "Lagos", "u2")

        store.clear()

        assert store.all() == []
        assert MemoryStore(path=path).all() == []

    def test_corrupt_file_recovers_to_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        path.write_text("{not json at all", encoding="utf-8")

        store = MemoryStore(path=path)

        assert store.all() == []
        assert path.with_name(path.name + ".corrupt").exists()

    def test_corrupt_file_still_accepts_writes(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        path.write_text("[[[", encoding="utf-8")

        store = MemoryStore(path=path)
        store.upsert("name", "Ola", "u1")

        assert MemoryStore(path=path).all()[0].value == "Ola"

    def test_corrupt_sidecar_is_overwritten(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        corrupt_path = path.with_name(path.name + ".corrupt")
        corrupt_path.write_text("older corruption", encoding="utf-8")
        path.write_text("still not json", encoding="utf-8")

        assert MemoryStore(path=path).all() == []
        assert corrupt_path.read_text(encoding="utf-8") == "still not json"

    def test_wrong_shape_recovers_to_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        path.write_text(json.dumps({"facts": "not-a-list"}), encoding="utf-8")

        assert MemoryStore(path=path).all() == []

    def test_eviction_drops_least_recently_updated(self, tmp_path: Path) -> None:
        store = MemoryStore(path=tmp_path / "memory.json", max_facts=3)

        for index in range(5):
            store.upsert(f"key_{index}", f"value_{index}", f"utterance {index}")
            time.sleep(0.005)

        keys = [fact.key for fact in store.all()]
        assert len(keys) == 3
        assert keys == ["key_4", "key_3", "key_2"]

    def test_eviction_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path, max_facts=2)

        for index in range(4):
            store.upsert(f"key_{index}", f"value_{index}", "u")

        assert len(MemoryStore(path=path).all()) == 2

    def test_save_leaves_no_temp_files(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.upsert("name", "Ola", "u1")

        assert [entry.name for entry in tmp_path.iterdir()] == ["memory.json"]


# ── FactExtractor Tests ──

class TestFactExtractor:
    """Tests for LLM-backed fact extraction."""

    async def test_clean_json(self) -> None:
        llm = MockLLM(
            default_response=json.dumps(
                {"facts": [{"key": "name", "value": "Ola"}, {"key": "job", "value": "Engineer"}]}
            )
        )
        extractor = FactExtractor(llm=llm)

        assert await extractor.extract("my name is Ola") == [
            ("name", "Ola"),
            ("job", "Engineer"),
        ]

    async def test_fenced_json(self) -> None:
        llm = MockLLM(
            default_response='```json\n{"facts": [{"key": "name", "value": "Ola"}]}\n```'
        )
        extractor = FactExtractor(llm=llm)

        assert await extractor.extract("my name is Ola") == [("name", "Ola")]

    async def test_malformed_json_returns_empty(self) -> None:
        extractor = FactExtractor(llm=MockLLM(default_response="{ this is not json"))

        assert await extractor.extract("my name is Ola") == []

    async def test_wrong_shape_returns_empty(self) -> None:
        extractor = FactExtractor(llm=MockLLM(default_response='{"intents": []}'))

        assert await extractor.extract("my name is Ola") == []

    async def test_facts_not_a_list_returns_empty(self) -> None:
        extractor = FactExtractor(llm=MockLLM(default_response='{"facts": {"key": "name"}}'))

        assert await extractor.extract("my name is Ola") == []

    async def test_incomplete_entries_are_skipped(self) -> None:
        llm = MockLLM(
            default_response=json.dumps(
                {
                    "facts": [
                        {"key": "name", "value": "Ola"},
                        {"key": "", "value": "orphan"},
                        {"key": "job"},
                        "not-a-dict",
                    ]
                }
            )
        )
        extractor = FactExtractor(llm=llm)

        assert await extractor.extract("my name is Ola") == [("name", "Ola")]

    async def test_llm_failure_returns_empty(self) -> None:
        class BrokenLLM(MockLLM):
            async def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
                raise ConnectionError("Ollama is down")

        assert await FactExtractor(llm=BrokenLLM()).extract("my name is Ola") == []

    async def test_blank_utterance_skips_llm(self) -> None:
        llm = MockLLM(default_response='{"facts": []}')

        assert await FactExtractor(llm=llm).extract("   ") == []
        assert llm.call_count == 0


# ── MemoryService Tests ──

class TestMemoryService:
    """Tests for the capture / recall / forget facade."""

    async def test_capture_skips_llm_without_first_person_marker(self, tmp_path: Path) -> None:
        llm = MockLLM(default_response=json.dumps({"facts": [{"key": "x", "value": "y"}]}))
        service = make_service(tmp_path, llm)

        assert await service.capture("Open Chrome and search for AI news") == []
        assert llm.call_count == 0, "Command utterances must never reach the model."
        assert service.facts() == []

    async def test_capture_runs_for_first_person_utterance(self, tmp_path: Path) -> None:
        llm = MockLLM(
            default_response=json.dumps({"facts": [{"key": "name", "value": "Ola"}]})
        )
        service = make_service(tmp_path, llm)

        captured = await service.capture("my name is Ola")

        assert llm.call_count == 1
        assert [fact.key for fact in captured] == ["name"]
        assert service.facts()[0].value == "Ola"

    async def test_capture_is_disabled_by_flag(self, tmp_path: Path) -> None:
        llm = MockLLM(
            default_response=json.dumps({"facts": [{"key": "name", "value": "Ola"}]})
        )
        service = make_service(tmp_path, llm, enabled=False)

        assert await service.capture("my name is Ola") == []
        assert llm.call_count == 0

    async def test_capture_swallows_store_failures(self, tmp_path: Path) -> None:
        llm = MockLLM(
            default_response=json.dumps({"facts": [{"key": "name", "value": "Ola"}]})
        )
        service = make_service(tmp_path, llm)

        def explode(*args: Any, **kwargs: Any) -> None:
            raise OSError("disk on fire")

        service.store.upsert = explode  # type: ignore[method-assign]

        assert await service.capture("my name is Ola") == []

    async def test_capture_ignores_blank_utterance(self, tmp_path: Path) -> None:
        llm = MockLLM(default_response='{"facts": []}')
        service = make_service(tmp_path, llm)

        assert await service.capture("") == []
        assert llm.call_count == 0

    def test_render_block_empty(self, tmp_path: Path) -> None:
        assert make_service(tmp_path).render_block() == ""

    def test_render_block_populated(self, tmp_path: Path) -> None:
        service = make_service(tmp_path)
        service.store.upsert("name", "Ola", "my name is Ola")
        service.store.upsert("favourite_editor", "VS Code", "I use VS Code")

        assert service.render_block() == (
            "What you know about the user:\n"
            "- favourite_editor: VS Code\n"
            "- name: Ola"
        )

    def test_forget_removes_matches(self, tmp_path: Path) -> None:
        service = make_service(tmp_path)
        service.store.upsert("name", "Ola", "u1")
        service.store.upsert("location", "Lagos", "u2")

        removed = service.forget("location")

        assert [fact.key for fact in removed] == ["location"]
        assert [fact.key for fact in service.facts()] == ["name"]

    def test_forget_no_match(self, tmp_path: Path) -> None:
        service = make_service(tmp_path)
        service.store.upsert("name", "Ola", "u1")

        assert service.forget("my car") == []
        assert len(service.facts()) == 1


# ── MemorySkill Tests ──

class TestMemorySkill:
    """Tests for the recall and forget skill."""

    async def test_recall_when_empty(self, tmp_path: Path) -> None:
        skill = MemorySkill(StubContainer(make_service(tmp_path)))  # type: ignore[arg-type]

        result = await skill.execute(make_task("memory_recall"))

        assert result == "I don't know anything about you yet."

    async def test_recall_lists_facts_without_calling_the_llm(self, tmp_path: Path) -> None:
        llm = MockLLM(default_response='{"facts": []}')
        service = make_service(tmp_path, llm)
        service.store.upsert("name", "Ola", "u1")
        service.store.upsert("favourite_editor", "VS Code", "u2")

        skill = MemorySkill(StubContainer(service))  # type: ignore[arg-type]
        result = await skill.execute(make_task("memory_recall"))

        assert "Ola" in result
        assert "VS Code" in result
        assert "favourite editor" in result
        assert llm.call_count == 0, "Recall must be deterministic."

    async def test_forget_removes_and_confirms(self, tmp_path: Path) -> None:
        service = make_service(tmp_path)
        service.store.upsert("name", "Ola", "u1")
        service.store.upsert("location", "Lagos", "u2")

        skill = MemorySkill(StubContainer(service))  # type: ignore[arg-type]
        result = await skill.execute(
            make_task("memory_forget", {"target": "location"})
        )

        assert "location" in result
        assert [fact.key for fact in service.facts()] == ["name"]

    async def test_forget_no_match(self, tmp_path: Path) -> None:
        service = make_service(tmp_path)
        service.store.upsert("name", "Ola", "u1")

        skill = MemorySkill(StubContainer(service))  # type: ignore[arg-type]
        result = await skill.execute(make_task("memory_forget", {"target": "my car"}))

        assert "my car" in result
        assert len(service.facts()) == 1

    async def test_forget_without_target(self, tmp_path: Path) -> None:
        skill = MemorySkill(StubContainer(make_service(tmp_path)))  # type: ignore[arg-type]

        result = await skill.execute(make_task("memory_forget", {}))

        assert "forget" in result.lower()

    async def test_unknown_intent_raises(self, tmp_path: Path) -> None:
        skill = MemorySkill(StubContainer(make_service(tmp_path)))  # type: ignore[arg-type]

        with pytest.raises(ValueError):
            await skill.execute(make_task("weather"))

    async def test_forget_persists_across_instances(self, tmp_path: Path) -> None:
        service = make_service(tmp_path)
        service.store.upsert("name", "Ola", "u1")
        service.store.upsert("location", "Lagos", "u2")

        skill = MemorySkill(StubContainer(service))  # type: ignore[arg-type]
        await skill.execute(make_task("memory_forget", {"target": "Lagos"}))

        reopened = MemoryStore(path=tmp_path / "memory.json")
        assert [fact.key for fact in reopened.all()] == ["name"]


# ── ChatSkill Injection Tests ──

class TestChatSkillMemoryInjection:
    """Tests that remembered facts reach the conversational system prompt."""

    def _container(self, tmp_path: Path, llm: MockLLM) -> Any:
        from core.state import AssistantRuntimeState

        class ChatContainer:
            def __init__(self, memory: MemoryService) -> None:
                self.llm = llm
                self.memory = memory
                self.state = AssistantRuntimeState()

        return ChatContainer(make_service(tmp_path, llm))

    async def test_memory_block_is_appended(self, tmp_path: Path) -> None:
        from skills.system_skills import ChatSkill

        llm = MockLLM(default_response="Hello Ola.")
        container = self._container(tmp_path, llm)
        container.memory.store.upsert("name", "Ola", "my name is Ola")

        skill = ChatSkill(container)
        task = make_task("general_chat")
        task.metadata["raw_utterance"] = "who am I?"

        await skill.execute(task)

        system_prompt = llm.last_messages[0]["content"]
        assert ChatSkill.SYSTEM_PROMPT in system_prompt
        assert "What you know about the user:\n- name: Ola" in system_prompt

    async def test_no_block_when_store_is_empty(self, tmp_path: Path) -> None:
        from skills.system_skills import ChatSkill

        llm = MockLLM(default_response="Hello.")
        container = self._container(tmp_path, llm)

        skill = ChatSkill(container)
        task = make_task("general_chat")
        task.metadata["raw_utterance"] = "hello"

        await skill.execute(task)

        assert llm.last_messages[0]["content"] == ChatSkill.SYSTEM_PROMPT

    async def test_broken_store_degrades_to_plain_chat(self, tmp_path: Path) -> None:
        from skills.system_skills import ChatSkill

        llm = MockLLM(default_response="Hello.")
        container = self._container(tmp_path, llm)

        def explode() -> str:
            raise OSError("store unreadable")

        container.memory.render_block = explode  # type: ignore[method-assign]

        skill = ChatSkill(container)
        task = make_task("general_chat")
        task.metadata["raw_utterance"] = "hello"

        assert await skill.execute(task) == "Hello."


# ── Validator / Router Wiring Tests ──

class TestMemoryWiring:
    """Tests that the memory intents are routed and validated correctly."""

    def test_router_maps_memory_intents(self) -> None:
        from intelligence.router import TaskRouter

        assert TaskRouter.ROUTING_TABLE["memory_recall"] is MemorySkill
        assert TaskRouter.ROUTING_TABLE["memory_forget"] is MemorySkill

    def test_validator_requires_forget_target(self) -> None:
        from core.validator import TaskValidator

        validator = TaskValidator()

        assert validator.validate(make_task("memory_recall")).valid is True
        assert validator.validate(make_task("memory_forget", {"target": "my job"})).valid is True

        result = validator.validate(make_task("memory_forget", {"target": "   "}))
        assert result.valid is False
        assert result.missing_parameters == ["target"]

    def test_intent_detector_knows_memory_intents(self) -> None:
        from intelligence.intent_detector import IntentDetector

        assert "memory_recall" in IntentDetector.VALID_INTENTS
        assert "memory_forget" in IntentDetector.VALID_INTENTS

        detector = IntentDetector(llm=MockLLM())
        assert detector._rule_based_match("forget where i live") == "memory_forget"
        assert detector._rule_based_match("what do you know about me") == "memory_recall"
