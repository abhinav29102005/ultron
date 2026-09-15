"""
tests/test_core.py – Core Module Tests for Phase 0
===================================================
Contains unit tests for Settings, EventBus, AssistantState, and ServiceContainer.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import pytest
from pydantic import SecretStr

from core.state import AssistantState, AssistantRuntimeState, ConversationTurn
from core.event_bus import EventBus, BaseEvent, UserInputEvent, StateChangedEvent
from core.container import ServiceContainer
from config.settings import Settings
from utils.exceptions import EventBusError, ServiceNotFoundError, ValidationError


# ── Settings Tests ──

class TestSettings:
    """Tests for the Settings configuration module."""

    def test_default_settings(self) -> None:
        settings = Settings(
            app_name="ULTRON",
            app_version="0.1.0",
            app_env="development",
            debug=False,
            log_level="INFO",
            log_dir=Path("logs"),
            nvidia_api_key=SecretStr(""),
            nvidia_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_model="meta/llama-3.1-8b-instruct",
            llm_temperature=0.7,
            llm_max_tokens=1024,
            llm_timeout_seconds=30,
            stt_engine="whisper",
            tts_engine="pyttsx3",
            tts_voice_rate=175,
            tts_voice_volume=1.0,
            audio_sample_rate=16000,
            audio_channels=1,
            audio_chunk_size=1024,
            wakeword_engine="porcupine",
            wakeword_keyword="ULTRON",
            picovoice_access_key=SecretStr(""),
            wakeword_sensitivity=0.5,
            intent_confidence_threshold=0.75,
            max_plan_steps=10,
            secret_key=SecretStr("dev_secret_key")
        )
        assert settings.app_name == "ULTRON"
        assert settings.log_level == "INFO"
        assert settings.secret_key.get_secret_value() == "dev_secret_key"

    def test_invalid_log_level_raises(self) -> None:
        with pytest.raises(Exception):
            # log_level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL
            Settings(
                app_name="ULTRON",
                app_version="0.1.0",
                app_env="development",
                debug=False,
                log_level="INVALID_LEVEL",
                log_dir=Path("logs"),
                nvidia_api_key=SecretStr(""),
                nvidia_base_url="https://integrate.api.nvidia.com/v1",
                nvidia_model="meta/llama-3.1-8b-instruct",
                llm_temperature=0.7,
                llm_max_tokens=1024,
                llm_timeout_seconds=30,
                stt_engine="whisper",
                tts_engine="pyttsx3",
                tts_voice_rate=175,
                tts_voice_volume=1.0,
                audio_sample_rate=16000,
                audio_channels=1,
                audio_chunk_size=1024,
                wakeword_engine="porcupine",
                wakeword_keyword="ULTRON",
                picovoice_access_key=SecretStr(""),
                wakeword_sensitivity=0.5,
                intent_confidence_threshold=0.75,
                max_plan_steps=10,
                secret_key=SecretStr("dev_secret_key")
            )


# ── EventBus Tests ──

@pytest.mark.asyncio
class TestEventBus:
    """Tests for the asynchronous EventBus pub-sub implementation."""

    async def test_subscribe_and_publish(self) -> None:
        bus = EventBus()
        called_with: list[UserInputEvent] = []

        async def handler(event: UserInputEvent) -> None:
            called_with.append(event)

        bus.subscribe(UserInputEvent, handler)
        event = UserInputEvent(text="Hello", source="test")
        await bus.publish(event)

        assert len(called_with) == 1
        assert called_with[0].text == "Hello"
        assert called_with[0].source == "test"

    async def test_unsubscribe(self) -> None:
        bus = EventBus()
        called_count = 0

        async def handler(event: UserInputEvent) -> None:
            nonlocal called_count
            called_count += 1

        bus.subscribe(UserInputEvent, handler)
        await bus.publish(UserInputEvent(text="First", source="test"))
        assert called_count == 1

        bus.unsubscribe(UserInputEvent, handler)
        await bus.publish(UserInputEvent(text="Second", source="test"))
        assert called_count == 1  # Should not increase

    async def test_non_async_handler_raises(self) -> None:
        bus = EventBus()

        def sync_handler(event: UserInputEvent) -> None:
            pass

        with pytest.raises(EventBusError):
            bus.subscribe(UserInputEvent, sync_handler)  # type: ignore

    async def test_multiple_handlers(self) -> None:
        bus = EventBus()
        handler1_called = False
        handler2_called = False

        async def handler1(event: UserInputEvent) -> None:
            nonlocal handler1_called
            handler1_called = True

        async def handler2(event: UserInputEvent) -> None:
            nonlocal handler2_called
            handler2_called = True

        bus.subscribe(UserInputEvent, handler1)
        bus.subscribe(UserInputEvent, handler2)

        await bus.publish(UserInputEvent(text="Multi", source="test"))
        assert handler1_called is True
        assert handler2_called is True

    async def test_handler_error_isolation(self) -> None:
        bus = EventBus()
        handler_ok_called = False

        async def handler_err(event: UserInputEvent) -> None:
            raise ValueError("Simulated error")

        async def handler_ok(event: UserInputEvent) -> None:
            nonlocal handler_ok_called
            handler_ok_called = True

        bus.subscribe(UserInputEvent, handler_err)
        bus.subscribe(UserInputEvent, handler_ok)

        # Should not raise exception out of publish
        await bus.publish(UserInputEvent(text="Error isolation", source="test"))
        assert handler_ok_called is True


# ── AssistantState Tests ──

class TestAssistantState:
    """Tests for AssistantState enums and runtime state containers."""

    def test_state_enum_members(self) -> None:
        expected_states = {
            "OFFLINE", "STARTING", "IDLE", "LISTENING",
            "THINKING", "EXECUTING", "SPEAKING", "SHUTTING_DOWN"
        }
        actual_states = {state.name for state in AssistantState}
        assert expected_states == actual_states

    def test_state_transitions(self) -> None:
        state = AssistantRuntimeState()
        assert state.mode == AssistantState.OFFLINE
        state.mode = AssistantState.IDLE
        assert state.mode == AssistantState.IDLE


# ── ServiceContainer Tests ──

class TestServiceContainer:
    """Tests for the dependency injection ServiceContainer."""

    def test_lazy_service_creation(self) -> None:
        settings = Settings(
            app_name="ULTRON",
            app_version="0.1.0",
            app_env="development",
            debug=False,
            log_level="INFO",
            log_dir=Path("logs"),
            nvidia_api_key=SecretStr(""),
            nvidia_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_model="meta/llama-3.1-8b-instruct",
            llm_temperature=0.7,
            llm_max_tokens=1024,
            llm_timeout_seconds=30,
            stt_engine="whisper",
            tts_engine="pyttsx3",
            tts_voice_rate=175,
            tts_voice_volume=1.0,
            audio_sample_rate=16000,
            audio_channels=1,
            audio_chunk_size=1024,
            wakeword_engine="porcupine",
            wakeword_keyword="ULTRON",
            picovoice_access_key=SecretStr(""),
            wakeword_sensitivity=0.5,
            intent_confidence_threshold=0.75,
            max_plan_steps=10,
            secret_key=SecretStr("dev_secret_key")
        )
        container = ServiceContainer(settings)

        # Test settings resolution
        assert container.settings == settings

        # Test EventBus lazy creation
        bus1 = container.event_bus
        bus2 = container.event_bus
        assert bus1 is bus2
        assert isinstance(bus1, EventBus)

        # Test State lazy creation
        state1 = container.state
        state2 = container.state
        assert state1 is state2
        assert isinstance(state1, AssistantRuntimeState)

    def test_custom_registration(self) -> None:
        settings = Settings(
            app_name="ULTRON",
            app_version="0.1.0",
            app_env="development",
            debug=False,
            log_level="INFO",
            log_dir=Path("logs"),
            nvidia_api_key=SecretStr(""),
            nvidia_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_model="meta/llama-3.1-8b-instruct",
            llm_temperature=0.7,
            llm_max_tokens=1024,
            llm_timeout_seconds=30,
            stt_engine="whisper",
            tts_engine="pyttsx3",
            tts_voice_rate=175,
            tts_voice_volume=1.0,
            audio_sample_rate=16000,
            audio_channels=1,
            audio_chunk_size=1024,
            wakeword_engine="porcupine",
            wakeword_keyword="ULTRON",
            picovoice_access_key=SecretStr(""),
            wakeword_sensitivity=0.5,
            intent_confidence_threshold=0.75,
            max_plan_steps=10,
            secret_key=SecretStr("dev_secret_key")
        )
        container = ServiceContainer(settings)

        class CustomService:
            pass

        service = CustomService()
        container.register("custom", service)
        assert container.get("custom") is service

    def test_unregistered_raises(self) -> None:
        settings = Settings(
            app_name="ULTRON",
            app_version="0.1.0",
            app_env="development",
            debug=False,
            log_level="INFO",
            log_dir=Path("logs"),
            nvidia_api_key=SecretStr(""),
            nvidia_base_url="https://integrate.api.nvidia.com/v1",
            nvidia_model="meta/llama-3.1-8b-instruct",
            llm_temperature=0.7,
            llm_max_tokens=1024,
            llm_timeout_seconds=30,
            stt_engine="whisper",
            tts_engine="pyttsx3",
            tts_voice_rate=175,
            tts_voice_volume=1.0,
            audio_sample_rate=16000,
            audio_channels=1,
            audio_chunk_size=1024,
            wakeword_engine="porcupine",
            wakeword_keyword="ULTRON",
            picovoice_access_key=SecretStr(""),
            wakeword_sensitivity=0.5,
            intent_confidence_threshold=0.75,
            max_plan_steps=10,
            secret_key=SecretStr("dev_secret_key")
        )
        container = ServiceContainer(settings)
        with pytest.raises(ServiceNotFoundError):
            container.get("unregistered")


class TestContainerShutdownReleasesResources:
    """Regression: shutdown() cleared the registry without closing anything.

    WebSkill owns a long-lived httpx.AsyncClient. Dropping the reference
    leaks its connection pool; the research loop made that the hottest client
    in the process.
    """

    @pytest.mark.asyncio
    async def test_async_close_is_awaited(self):
        from config.settings import Settings
        from core.container import ServiceContainer

        closed = []

        class AsyncService:
            async def close(self):
                closed.append("async")

        class SyncService:
            def close(self):
                closed.append("sync")

        container = ServiceContainer(Settings())
        container._registry["a"] = AsyncService()
        container._registry["b"] = SyncService()

        await container.shutdown()

        assert sorted(closed) == ["async", "sync"]
        assert container._registry == {}

    @pytest.mark.asyncio
    async def test_a_failing_close_does_not_block_shutdown(self):
        from config.settings import Settings
        from core.container import ServiceContainer

        closed = []

        class Exploding:
            def close(self):
                raise RuntimeError("nope")

        class Fine:
            def close(self):
                closed.append("fine")

        container = ServiceContainer(Settings())
        container._registry["boom"] = Exploding()
        container._registry["fine"] = Fine()

        await container.shutdown()

        assert closed == ["fine"]
        assert container._registry == {}

    @pytest.mark.asyncio
    async def test_services_without_close_are_skipped(self):
        from config.settings import Settings
        from core.container import ServiceContainer

        container = ServiceContainer(Settings())
        container._registry["plain"] = object()

        await container.shutdown()

        assert container._registry == {}
