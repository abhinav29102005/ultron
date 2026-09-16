"""
core/container.py – Dependency Injection Container
====================================================
Lazily creates and resolves application configuration and core services.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from core.event_bus import EventBus
from config.logging_config import get_logger
from utils.exceptions import ServiceNotFoundError

if TYPE_CHECKING:
    from config.settings import Settings
    from core.assistant import Assistant
    from core.orchestrator import Orchestrator
    from core.state import AssistantRuntimeState
    from llm.base import BaseLLM
    from memory.service import MemoryService
    from intelligence.planner import Planner
    from skills.manager import SkillManager
    from speech.speech_to_text import Transcriber, Recorder
    from speech.text_to_speech import Speaker, Player


class ServiceContainer:
    """
    Service container responsible for dependency injection.
    Manages lazy initialization of core services.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._registry: dict[str, Any] = {}
        self._logger = get_logger("container")

    async def initialise(self) -> None:
        """
        Eagerly initialize core services.
        """
        self._logger.info("Initializing ServiceContainer core services...")
        # Eagerly construct the event bus
        _ = self.event_bus
        # Start retrieval controller early so it can subscribe to partial
        # transcript events if implemented.
        try:
            await self.retrieval_controller.start()
        except Exception:
            # The controller is optional at this stage; startup should not fail
            # because it is missing a concrete event subscription implementation.
            self._logger.debug("RetrievalController start skipped or failed.")
        # Start the retrieval handler (consumer) so it can process retrieval
        # requests and produce retrieval results for downstream components.
        try:
            await self.retrieval_handler.start()
        except Exception:
            self._logger.debug("RetrievalHandler start skipped or failed.")
        # Start the decomposer so it can subscribe to retrieval results and
        # emit decomposed queries for downstream retrieval tasks.
        try:
            await self.decomposer.start()
        except Exception:
            self._logger.debug("Decomposer start skipped or failed.")
        # Start the hybrid retriever (web + optional vector DB) for production
        # retrieval behaviour. If it fails, the earlier retriever stub remains
        # available but is not started.
        try:
            await self.hybrid_retriever.start()
        except Exception:
            self._logger.debug("HybridRetriever start skipped or failed.")
        # Start the synthesizer so it can listen to retrieval results, compose
        # grounded answers with [Doc_XX §YY] citations, and record telemetry.
        try:
            await self.synthesizer.start()
        except Exception:
            self._logger.debug("Synthesizer start skipped or failed.")
        self._logger.info("ServiceContainer core services ready.")

    async def shutdown(self) -> None:
        """
        Gracefully dispose services and release resources.
        """
        self._logger.info("Shutting down ServiceContainer services...")

        # Registered services may hold real resources -- WebSkill owns a
        # long-lived httpx.AsyncClient, and clearing the registry without
        # closing it leaks the connection pool and emits "Unclosed client
        # session" on the way out. That was invisible while the web skill was
        # barely used; the research loop makes it the busiest client here.
        import inspect

        for name, service in list(self._registry.items()):
            close = getattr(service, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                # A service that will not close cleanly must not prevent the
                # rest from being released, nor block the process exiting.
                self._logger.warning(f"Failed to close service '{name}': {exc}")

        self._registry.clear()
        self._logger.info("ServiceContainer shutdown complete.")

    @property
    def settings(self) -> Settings:
        """Get the loaded application Settings."""
        return self._settings

    @property
    def event_bus(self) -> EventBus:
        """Get the shared EventBus instance, lazily initialized."""
        if "event_bus" not in self._registry:
            self._registry["event_bus"] = EventBus()
        return self._registry["event_bus"]

    @property
    def logger(self):
        """Get the default logger."""
        return get_logger("application")

    @property
    def state(self) -> AssistantRuntimeState:
        """Get the shared AssistantRuntimeState instance, lazily initialized."""
        if "state" not in self._registry:
            from core.state import AssistantRuntimeState
            self._registry["state"] = AssistantRuntimeState()
        return self._registry["state"]

    @property
    def assistant(self) -> Assistant:
        """Get the Assistant instance, lazily initialized."""
        if "assistant" not in self._registry:
            from core.assistant import Assistant
            self._registry["assistant"] = Assistant(container=self)
        return self._registry["assistant"]

    @property
    def orchestrator(self) -> Orchestrator:
        """Get the Orchestrator instance, lazily initialized."""
        if "orchestrator" not in self._registry:
            from core.orchestrator import Orchestrator
            self._registry["orchestrator"] = Orchestrator(
                container=self,
                event_bus=self.event_bus,
                state=self.state
            )
        return self._registry["orchestrator"]

    @property
    def llm(self) -> BaseLLM:
        """Get the shared LLM instance (switchable), lazily initialized."""
        if "llm" not in self._registry:
            from llm.switcher import LLMSwitcher
            from utils.cache import CachedLLM
            base_llm = LLMSwitcher(self._settings)
            self._registry["llm"] = CachedLLM(base_llm)
        return self._registry["llm"]

    @property
    def memory(self) -> MemoryService:
        """Get the MemoryService instance, lazily initialized."""
        if "memory" not in self._registry:
            from memory.extractor import FactExtractor
            from memory.service import MemoryService
            from memory.store import MemoryStore

            self._registry["memory"] = MemoryService(
                store=MemoryStore(
                    path=self._settings.memory_path,
                    max_facts=self._settings.memory_max_facts,
                ),
                extractor=FactExtractor(llm=self.llm),
                enabled=self._settings.memory_enabled,
            )
        return self._registry["memory"]

    @property
    def stt(self) -> Transcriber:
        """Get the SpeechToText (Transcriber) instance, lazily initialized."""
        if "stt" not in self._registry:
            from speech.speech_to_text import Transcriber
            self._registry["stt"] = Transcriber()
        return self._registry["stt"]

    @property
    def tts(self) -> Speaker:
        """Get the TextToSpeech (Speaker) instance, lazily initialized."""
        if "tts" not in self._registry:
            from speech.text_to_speech import Speaker
            self._registry["tts"] = Speaker()
        return self._registry["tts"]

    @property
    def recorder(self) -> Recorder:
        """Get the Recorder instance, lazily initialized."""
        if "recorder" not in self._registry:
            from speech.speech_to_text import Recorder
            self._registry["recorder"] = Recorder()
        return self._registry["recorder"]

    @property
    def audio_player(self) -> Player:
        """Get the shared Player — the same one tts_pipeline speaks through.

        Building a second Player here would create one that ``stop_audio()``
        cannot reach, so anything played through it would be unstoppable by a
        barge-in.
        """
        if "audio_player" not in self._registry:
            from speech.text_to_speech.tts_pipeline import get_player
            self._registry["audio_player"] = get_player()
        return self._registry["audio_player"]

    @property
    def intent_detector(self):
        """Get the IntentDetector instance, lazily initialized."""
        if "intent_detector" not in self._registry:
            from intelligence.intent_detector import IntentDetector

            self._registry["intent_detector"] = IntentDetector(
                llm=self.llm,
                confidence_threshold=self._settings.intent_confidence_threshold,
            )

        return self._registry["intent_detector"]

    @property
    def retrieval_controller(self):
        """Get the RetrievalController instance, lazily initialized."""
        if "retrieval_controller" not in self._registry:
            from intelligence.retrieval_controller import RetrievalController

            self._registry["retrieval_controller"] = RetrievalController(container=self)
        return self._registry["retrieval_controller"]

    @property
    def retrieval_handler(self):
        """Get the RetrievalHandler instance, lazily initialized."""
        if "retrieval_handler" not in self._registry:
            from intelligence.retrieval_handler import RetrievalHandler

            self._registry["retrieval_handler"] = RetrievalHandler(container=self)
        return self._registry["retrieval_handler"]

    @property
    def synthesizer(self):
        """Get the Synthesizer instance, lazily initialized."""
        if "synthesizer" not in self._registry:
            from intelligence.synthesizer import Synthesizer

            self._registry["synthesizer"] = Synthesizer(container=self)
        return self._registry["synthesizer"]

    @property
    def decomposer(self):
        """Get the Decomposer instance, lazily initialized."""
        if "decomposer" not in self._registry:
            from intelligence.decomposer import Decomposer

            self._registry["decomposer"] = Decomposer(container=self)
        return self._registry["decomposer"]

    @property
    def retriever(self):
        """Get the Retriever instance, lazily initialized."""
        if "retriever" not in self._registry:
            from intelligence.retriever import Retriever

            self._registry["retriever"] = Retriever(container=self)
        return self._registry["retriever"]

    @property
    def hybrid_retriever(self):
        """Get the HybridRetriever instance, lazily initialized."""
        if "hybrid_retriever" not in self._registry:
            from intelligence.hybrid_retriever import HybridRetriever

            self._registry["hybrid_retriever"] = HybridRetriever(container=self)
        return self._registry["hybrid_retriever"]

    @property
    def weaviate_client(self):
        """Optional Weaviate client wrapper. Lazily created when settings indicate a URL."""
        if "weaviate_client" not in self._registry:
            try:
                url = getattr(self._settings, "weaviate_url", None)
            except Exception:
                url = None

            if url:
                try:
                    from intelligence.weaviate_client import WeaviateClientWrapper

                    api_key = getattr(self._settings, "weaviate_api_key", None)
                    self._registry["weaviate_client"] = WeaviateClientWrapper(url, api_key=api_key)
                except Exception:
                    # Keep container functional even if Weaviate is unavailable
                    self._registry["weaviate_client"] = None
            else:
                self._registry["weaviate_client"] = None

        return self._registry["weaviate_client"]

    @property
    def embeddings(self):
        """Get an embeddings provider instance (OpenAI) when configured."""
        if "embeddings" not in self._registry:
            try:
                api_key = getattr(self._settings, "openai_api_key", None)
            except Exception:
                api_key = None

            if api_key:
                try:
                    from intelligence.embeddings import OpenAIEmbeddings

                    model = getattr(self._settings, "openai_embedding_model", "text-embedding-3-small")
                    self._registry["embeddings"] = OpenAIEmbeddings(str(api_key), model=model)
                except Exception:
                    self._registry["embeddings"] = None
            else:
                self._registry["embeddings"] = None

        return self._registry["embeddings"]

    @property
    def reranker(self):
        """Get the cross-encoder reranker instance (OpenAI-backed) when configured.

        If no OpenAI key is configured, a fallback lexical reranker is still
        returned so calling code does not need to special-case missing service.
        """
        if "reranker" not in self._registry:
            try:
                api_key = getattr(self._settings, "openai_api_key", None)
            except Exception:
                api_key = None

            try:
                from intelligence.reranker import CrossEncoderReranker

                key = str(api_key) if api_key is not None else None
                self._registry["reranker"] = CrossEncoderReranker(api_key=key)
            except Exception:
                self._registry["reranker"] = None

        return self._registry["reranker"]

    @property
    def cancellation_manager(self):
        """Get the CancellationManager instance, lazily initialized."""
        if "cancellation_manager" not in self._registry:
            from core.cancellation import CancellationManager

            self._registry["cancellation_manager"] = CancellationManager()
        return self._registry["cancellation_manager"]

    @property
    def planner(self) -> Planner:
        """Get the Planner instance, lazily initialized."""
        if "planner" not in self._registry:
            from intelligence.planner import Planner
            self._registry["planner"] = Planner()
        return self._registry["planner"]

    @property
    def router(self):
        """Get the TaskRouter instance, lazily initialized."""
        if "router" not in self._registry:
            from intelligence.router import TaskRouter
            self._registry["router"] = TaskRouter(container=self)
        return self._registry["router"]
        
    @property
    def validator(self):
        """Get the TaskValidator instance, lazily initialized."""
        if "validator" not in self._registry:
            from core.validator import TaskValidator
            self._registry["validator"] = TaskValidator()
        return self._registry["validator"]

    @property
    def skill_manager(self) -> SkillManager:
        raise NotImplementedError("SkillManager module is not implemented in Phase 0.")

    @property
    def emotion_detector(self):
        """Get the EmotionDetector instance, lazily initialized."""
        if "emotion_detector" not in self._registry:
            from intelligence.emotion_detector import EmotionDetector
            self._registry["emotion_detector"] = EmotionDetector(llm=self.llm, use_llm_refinement=False)
        return self._registry["emotion_detector"]

    @property
    def web_skill(self):
        """Get the WebSkill instance, lazily initialized."""
        if "web_skill" not in self._registry:
            from skills.web_skill import WebSkill
            self._registry["web_skill"] = WebSkill()
        return self._registry["web_skill"]

    @property
    def chat_skill(self):
        """Get the ChatSkill instance, lazily initialized."""
        if "chat_skill" not in self._registry:
            from skills.chat_skill import ChatSkill
            self._registry["chat_skill"] = ChatSkill()
        return self._registry["chat_skill"]

    @property
    def permission_manager(self):
        """Get the PermissionManager instance, lazily initialized."""
        if "permission_manager" not in self._registry:
            from core.permissions import PermissionManager
            self._registry["permission_manager"] = PermissionManager()
        return self._registry["permission_manager"]

    @property
    def db(self):
        """Get the unified DatabaseManager instance."""
        if 'db' not in self._registry:
            from core.database import DatabaseManager
            self._registry['db'] = DatabaseManager()
        return self._registry['db']

    @property
    def user_settings(self):
        """Get the UserSettings instance."""
        if 'user_settings' not in self._registry:
            from config.user_settings import UserSettings
            self._registry['user_settings'] = UserSettings()
        return self._registry['user_settings']

    @property
    def session_manager(self):
        """Get the SessionManager instance."""
        if 'session_manager' not in self._registry:
            from core.session_manager import SessionManager
            self._registry['session_manager'] = SessionManager(db=self.db)
        return self._registry['session_manager']

    @property
    def executor(self):
        """Get the Executor instance, lazily initialized."""
        if "executor" not in self._registry:
            from intelligence.executor import Executor
            self._registry["executor"] = Executor(container=self)
        return self._registry["executor"]

    def get(self, key: str) -> Any:
        """
        Resolve a custom registered service by its key name.
        """
        if key not in self._registry:
            raise ServiceNotFoundError(f"Service '{key}' not found in container registry.")
        return self._registry[key]

    def register(self, key: str, instance: Any) -> None:
        """
        Manually register a custom service instance into the container.
        """
        self._registry[key] = instance
        self._logger.debug(f"Registered custom service instance under key '{key}'.")

