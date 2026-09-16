# Repository Analysis Report

This document provides a detailed analysis of the ULTRON AI Desktop Assistant repository, detailing the purpose of every folder and file, along with their architecture, dependency flows, and implementation status.

## 1. Directory Overview

- **config/**: Configuration package for settings, constants, and logging.
- **core/**: Core application orchestration, dependency injection, state, and event bus.
- **docs/**: Documentation directory.
- **intelligence/**: Planning, intent detection, routing, and task structures.
- **llm/**: Interfaces and implementations for interacting with Large Language Models.
- **skills/**: The extensible skill system for actions the assistant can perform.
- **speech/**: Audio I/O, speech-to-text (STT), and text-to-speech (TTS) interfaces.
- **utils/**: Shared utility functions, decorators, exceptions, and validators.
- **wakeword/**: Wake-word detection engine and model interfaces.
- **tests/**: Test suite directory (not analyzed deeply as per standard repo structure).

---

## 2. File Analysis

### Root Directory

#### `main.py`
1. **File path:** `main.py`
2. **Primary purpose:** Entry point for bootstrapping the application, setting up the DI container, and booting the assistant.
3. **Classes defined:** None
4. **Functions/methods defined:**
   - `parse_args()`: Parse command-line arguments.
   - `run(args)`: Async bootstrap for application services and transitioning to IDLE.
   - `main()`: Synchronous entry point wrapping `run`.
5. **Implementation status:** Fully implemented (for Phase 0).
6. **Dependencies:** Uses `config.settings.Settings`, `config.logging_config.configure_logging`, `config.logging_config.get_logger`, `core.container.ServiceContainer`.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Currently used as the application entry point.
9. **Interfaces:** None.

#### `speechtesting.py`
1. **File path:** `speechtesting.py`
2. **Primary purpose:** Standalone script for testing STT and TTS speech pipelines.
3. **Classes defined:** None
4. **Functions/methods defined:** None
5. **Implementation status:** Partially implemented/Scaffold script.
6. **Dependencies:** Expected to use `speech.speech_to_text.stt_pipeline`, `speech.text_to_speech.tts_pipeline`.
7. **Phase:** Unspecified / Prototyping.
8. **Usage:** Unused by main application flow.
9. **Interfaces:** None.

### `config/` Directory

#### `config/constants.py`
1. **File path:** `config/constants.py`
2. **Primary purpose:** Stores immutable application constants.
3. **Classes defined:** None
4. **Functions/methods defined:** None
5. **Implementation status:** Fully implemented.
6. **Dependencies:** None.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Used across the application for default constants.
9. **Interfaces:** None.

#### `config/logging_config.py`
1. **File path:** `config/logging_config.py`
2. **Primary purpose:** Configures Loguru handlers for stdout and rotating file logging.
3. **Classes defined:** None
4. **Functions/methods defined:** 
   - `configure_logging(settings)`: Configure Loguru handlers.
   - `get_logger(name)`: Get a logger bound to a specific module.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Used by `main.py` and almost every file initializing a logger.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Extensively used globally.
9. **Interfaces:** None.

#### `config/settings.py`
1. **File path:** `config/settings.py`
2. **Primary purpose:** Application settings schema loaded from environment variables using Pydantic.
3. **Classes defined:**
   - `Settings`: Pydantic base settings class for the app.
4. **Functions/methods defined:**
   - `validate_log_level(v)`: Validator for log level.
   - `validate_log_dir(v)`: Validator to ensure log directory creation.
   - `load(env_file, debug)`: Load configuration from the environment.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Used heavily by `core.container` and component constructors.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Used throughout the application to load env settings.
9. **Interfaces:** None.

### `core/` Directory

#### `core/assistant.py`
1. **File path:** `core/assistant.py`
2. **Primary purpose:** Top-level assistant facade coordinating lifecycle and state transitions.
3. **Classes defined:**
   - `Assistant`: Facade class handling startup, shutdown, and state management.
4. **Functions/methods defined:**
   - `initialize()`: Initialize configurations and lifecycle.
   - `start()`: Boot lifecycle infrastructure and transition to IDLE.
   - `stop()`: Shut down infrastructure.
   - `state()`: Get current state.
   - `handle_text_input(text)`: Handle text input (Not implemented).
   - `handle_audio_trigger()`: Handle wake word trigger (Not implemented).
5. **Implementation status:** Partially implemented (starts up/shuts down, but core I/O handlers raise `NotImplementedError`).
6. **Dependencies:** Used by `main.py`. Uses `core.state.AssistantState`, `core.lifecycle.ApplicationLifecycle`.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Active in bootstrapping sequence.
9. **Interfaces:** None.

#### `core/container.py`
1. **File path:** `core/container.py`
2. **Primary purpose:** Dependency injection container managing lazy initialization of core services.
3. **Classes defined:**
   - `ServiceContainer`: Service container responsible for dependency injection.
4. **Functions/methods defined:**
   - `initialise()`: Eagerly initialize core services.
   - `shutdown()`: Gracefully dispose services.
   - Various `@property` methods for core services (`settings`, `event_bus`, `assistant`, `orchestrator`, `llm`, `stt`, `tts`, `planner`, `skill_manager`).
   - `get(key)`: Resolve registered service.
   - `register(key, instance)`: Manually register custom service.
5. **Implementation status:** Partially implemented (properties for LLM, STT, TTS, Planner, SkillManager raise `NotImplementedError`).
6. **Dependencies:** Used heavily globally. Uses all components to construct them.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Actively used in `main.py` and across core modules.
9. **Interfaces:** None.

#### `core/event_bus.py`
1. **File path:** `core/event_bus.py`
2. **Primary purpose:** Lightweight asynchronous publish-subscribe event system.
3. **Classes defined:**
   - `BaseEvent`: Base dataclass for all events.
   - Specific Events (`AssistantStartedEvent`, `AssistantStoppedEvent`, `StateChangedEvent`, `UserInputEvent`, `ResponseReadyEvent`, `ErrorEvent`).
   - `EventBus`: Lightweight async event bus.
4. **Functions/methods defined:**
   - `subscribe(event_type, handler)`: Register an event handler.
   - `unsubscribe(event_type, handler)`: Remove a registered handler.
   - `publish(event)`: Publish an event to subscribers concurrently.
   - `_run_handler(handler, event)`: Run a specific handler.
   - `handler_count(event_type)`: Return count of handlers.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Used by `core.container` and `core.orchestrator`.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Currently initialized, fully functional for messaging.
9. **Interfaces:** None.

#### `core/lifecycle.py`
1. **File path:** `core/lifecycle.py`
2. **Primary purpose:** Coordinates initialization and teardown of application resources.
3. **Classes defined:**
   - `ApplicationLifecycle`: Manages application startup and shutdown hooks.
4. **Functions/methods defined:**
   - `add_startup_hook(hook)`: Register startup hook.
   - `add_shutdown_hook(hook)`: Register shutdown hook.
   - `startup()`: Start infrastructure and run hooks.
   - `shutdown()`: Teardown infrastructure and run hooks.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Used by `core.assistant.Assistant`.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Actively used during boot and shutdown.
9. **Interfaces:** None.

#### `core/orchestrator.py`
1. **File path:** `core/orchestrator.py`
2. **Primary purpose:** Coordinates orchestration of application startup/shutdown and task pipelines.
3. **Classes defined:**
   - `Orchestrator`: Orchestrates application pipelines.
4. **Functions/methods defined:**
   - `run(user_input)`: Run orchestration pipeline (raises warning in Phase 0).
5. **Implementation status:** Partially implemented (scaffold for pipeline).
6. **Dependencies:** Created in `core.container`.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Lazily initialized; `run()` is stubbed.
9. **Interfaces:** None.

#### `core/state.py`
1. **File path:** `core/state.py`
2. **Primary purpose:** Defines shared Assistant runtime state, mode enums, and history log types.
3. **Classes defined:**
   - `AssistantState` (Enum): Operating state enumeration.
   - `ConversationTurn` (Dataclass): Single turn in conversation history.
   - `AssistantRuntimeState` (Dataclass): Mutable state container.
4. **Functions/methods defined:** None (Dataclass properties only).
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Used by `core.assistant`, `core.orchestrator`, `core.lifecycle`.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Actively tracks assistant state.
9. **Interfaces:** None.

### `intelligence/` Directory

#### `intelligence/intent_detector.py`
1. **File path:** `intelligence/intent_detector.py`
2. **Primary purpose:** Interface for intent and entity extraction from utterances.
3. **Classes defined:**
   - `DetectedIntent`: Parsed intent classification result.
   - `IntentDetector`: Extracts intents from text.
4. **Functions/methods defined:**
   - `detect(utterance)`: Detect intent from utterance.
   - `is_actionable(intent)`: Check confidence threshold.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Used in `intelligence` package structure.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** `IntentDetector` is an interface expected to be implemented using an LLM.

#### `intelligence/parser.py`
1. **File path:** `intelligence/parser.py`
2. **Primary purpose:** Parser helper utility for structured LLM output (JSON).
3. **Classes defined:**
   - `ResponseParser`: Static parser helpers.
4. **Functions/methods defined:**
   - `parse_json(text)`: Parse raw string to JSON dict.
   - `parse_json_list(text)`: Parse raw string to JSON list.
   - `extract_first_json(text)`: Regex extract JSON code block.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Exported via `intelligence/__init__.py`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** None.

#### `intelligence/planner.py`
1. **File path:** `intelligence/planner.py`
2. **Primary purpose:** Task decomposition engine interface.
3. **Classes defined:**
   - `Planner`: Decomposes intents into structured tasks.
4. **Functions/methods defined:**
   - `plan(intent)`: Generate a sequence of tasks.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Part of intelligence router flow.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** `Planner` interface expected to be implemented via LLM prompting.

#### `intelligence/router.py`
1. **File path:** `intelligence/router.py`
2. **Primary purpose:** Task routing engine interface.
3. **Classes defined:**
   - `TaskRouter`: Routes tasks to skills in dependency order.
4. **Functions/methods defined:**
   - `route(tasks)`: Execute pipeline in dependency order.
   - `execute_task(task)`: Dispatch single execution to SkillManager.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Exported via `intelligence/__init__.py`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** `TaskRouter` is the intended orchestrator of task DAGs.

#### `intelligence/task.py`
1. **File path:** `intelligence/task.py`
2. **Primary purpose:** Defines the Task data structure and lifecycle status enum.
3. **Classes defined:**
   - `TaskStatus` (Enum): State of task execution.
   - `Task` (Dataclass): Executable task item.
4. **Functions/methods defined:** None (Fields only).
5. **Implementation status:** Fully implemented (dataclasses).
6. **Dependencies:** Used by `Planner`, `TaskRouter`, `Skill` definitions.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Imported by stubs.
9. **Interfaces:** None.

### `llm/` Directory

#### `llm/base.py`
1. **File path:** `llm/base.py`
2. **Primary purpose:** Abstract base class for LLMs.
3. **Classes defined:**
   - `BaseLLM`: ABC for LLM providers.
4. **Functions/methods defined:**
   - `complete(messages, **kwargs)`: Complete a chat sequence.
   - `stream(messages, **kwargs)`: Stream chat tokens.
   - Formatters: `build_system_message`, `build_user_message`, `build_assistant_message`.
   - `provider_name()`: Property.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Inherited by `MockLLM` and `NvidiaLLM`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Abstract Base Class; implemented by `NvidiaLLM` and `MockLLM`.

#### `llm/mock.py`
1. **File path:** `llm/mock.py`
2. **Primary purpose:** Mock LLM implementation for testing.
3. **Classes defined:**
   - `MockLLM`: Mock implementation.
4. **Functions/methods defined:**
   - `complete`, `stream`, `set_response`, `reset`.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Inherits `BaseLLM`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Implements `BaseLLM`.

#### `llm/nvidia.py`
1. **File path:** `llm/nvidia.py`
2. **Primary purpose:** NVIDIA NIM LLM API Integration.
3. **Classes defined:**
   - `NvidiaLLM`: NIM API Client.
4. **Functions/methods defined:**
   - `complete`, `stream`.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Inherits `BaseLLM`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Implements `BaseLLM`.

#### `llm/prompts.py`
1. **File path:** `llm/prompts.py`
2. **Primary purpose:** Centralised prompt template generation.
3. **Classes defined:**
   - `PromptLibrary`: Prompt generator logic.
4. **Functions/methods defined:**
   - `build_conversation_prompt`, `build_intent_prompt`, `build_planner_prompt`.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Used by LLM pipelines.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** None.

#### `llm/response.py`
1. **File path:** `llm/response.py`
2. **Primary purpose:** Envelopes for LLM completions.
3. **Classes defined:**
   - `LLMUsage`: Token usage data.
   - `LLMResponse`: Standardised LLM output.
4. **Functions/methods defined:** None (Fields only).
5. **Implementation status:** Fully implemented (dataclasses).
6. **Dependencies:** Returned by `BaseLLM.complete`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Imported by LLM stubs.
9. **Interfaces:** None.

### `skills/` Directory

#### `skills/base.py`
1. **File path:** `skills/base.py`
2. **Primary purpose:** Abstract base class for extensible skills.
3. **Classes defined:**
   - `Skill`: ABC for a modular skill.
4. **Functions/methods defined:**
   - `execute(task)`: Execute skill logic.
   - `on_load()`, `on_unload()`: Lifecycle hooks.
   - `validate_parameters(parameters)`: Param validator.
   - `skill_id`: Getter.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Implemented by individual skills (none exist yet).
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Abstract Base Class; to be implemented by future individual skills.

#### `skills/manager.py`
1. **File path:** `skills/manager.py`
2. **Primary purpose:** Manages skill lifecycles and coordinates execution.
3. **Classes defined:**
   - `SkillManager`: Skill execution coordinator.
4. **Functions/methods defined:**
   - `load`, `unload`, `load_all`, `unload_all`: Lifecycle.
   - `get`, `has`, `enable`, `disable`, `list_skills`: State.
   - `execute(task)`: Execution wrapper.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Used in the core `ServiceContainer`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** `SkillManager` is the orchestrator for `Skill` implementations.

#### `skills/registry.py`
1. **File path:** `skills/registry.py`
2. **Primary purpose:** Stores skill mapping by name.
3. **Classes defined:**
   - `SkillRegistry`: In-memory skill mapping.
4. **Functions/methods defined:**
   - `register`, `replace`, `unregister`, `get`, `has`.
   - `all_skills`, `enabled_skills`, `skill_names`.
   - Iteration magic methods (`__iter__`, `__len__`, `__contains__`).
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Used by `SkillManager`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** None.

### `speech/` Directory

#### `speech/audio_player.py`
1. **File path:** `speech/audio_player.py`
2. **Primary purpose:** Plays audio bytes or files.
3. **Classes defined:**
   - `AudioPlayer`: Media player for system audio.
4. **Functions/methods defined:**
   - `play_file`, `play_bytes`, `play_file_async`, `play_bytes_async`, `stop`.
   - `volume` (property).
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Speech I/O interface.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Expected to be implemented with audio libraries.

#### `speech/microphone.py`
1. **File path:** `speech/microphone.py`
2. **Primary purpose:** Microphone abstraction stream.
3. **Classes defined:**
   - `Microphone`: Audio stream context manager.
4. **Functions/methods defined:**
   - `open`, `close`, `read`, `list_devices`.
   - Magic methods for context manager.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Used by `Recorder` and `WakeWordDetector`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Required hardware integration abstraction.

#### `speech/recorder.py`
1. **File path:** `speech/recorder.py`
2. **Primary purpose:** Interface for voice activity detection / threshold recording.
3. **Classes defined:**
   - `Recorder`: Captures audio streams into buffers.
4. **Functions/methods defined:**
   - `record`, `record_async`.
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Uses `Microphone`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Expected to utilize VAD logic.

#### `speech/speech_to_text.py`
1. **File path:** `speech/speech_to_text.py`
2. **Primary purpose:** Speech-to-Text transcription interface.
3. **Classes defined:**
   - `SpeechToText`: Transforms audio bytes into strings.
4. **Functions/methods defined:**
   - `transcribe`, `transcribe_async`.
   - `engine_name` (property).
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Part of the DI `ServiceContainer`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Interface for Whisper or other STT engines.

#### `speech/text_to_speech.py`
1. **File path:** `speech/text_to_speech.py`
2. **Primary purpose:** Text-to-Speech synthesis interface.
3. **Classes defined:**
   - `TextToSpeech`: Synthesises text to audio outputs.
4. **Functions/methods defined:**
   - `speak`, `speak_async`, `synthesise_to_bytes`, `set_rate`, `set_volume`.
   - `engine_name` (property).
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Part of the DI `ServiceContainer`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Interface for pyttsx3 or other TTS models.

#### `speech/speechconfig.py`
1. **File path:** `speech/speechconfig.py`
2. **Primary purpose:** Constants and configuration strings specifically for audio systems.
3. **Classes defined:** None
4. **Functions/methods defined:** None
5. **Implementation status:** Scaffold (Just constants).
6. **Dependencies:** Intended for internal speech modules.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** None.

### `utils/` Directory

#### `utils/decorators.py`
1. **File path:** `utils/decorators.py`
2. **Primary purpose:** Reusable Python decorators.
3. **Classes defined:** None
4. **Functions/methods defined:**
   - `singleton`: Singleton pattern class decorator.
   - `retry`: Retry logic decorator.
   - `timed`: Execution time logging decorator.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Utilised generically across codebases.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Generic tools.
9. **Interfaces:** None.

#### `utils/exceptions.py`
1. **File path:** `utils/exceptions.py`
2. **Primary purpose:** Standardized custom exception hierarchy.
3. **Classes defined:**
   - `UltronError` (Base), `AssistantNotInitialisedError`, `ConfigurationError`, `EventBusError`, `ValidationError`, `ServiceNotFoundError`.
   - Subsytem Stubs: `LLMError`, `SpeechError`, `WakeWordError`, `PlannerError`, `SkillError`, and inherited variations.
4. **Functions/methods defined:** Exception initializers.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Widely imported.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Used throughout for error handling.
9. **Interfaces:** None.

#### `utils/helpers.py`
1. **File path:** `utils/helpers.py`
2. **Primary purpose:** Stateless generic helper functions.
3. **Classes defined:** None
4. **Functions/methods defined:**
   - `project_root`: Path resolution.
   - `current_timestamp`: Epoch time.
   - `platform_name`: OS type.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Generic tools.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Minor usages throughout.
9. **Interfaces:** None.

#### `utils/validators.py`
1. **File path:** `utils/validators.py`
2. **Primary purpose:** Validation functions.
3. **Classes defined:** None
4. **Functions/methods defined:**
   - `validate_env`: Environment presence checker.
   - `validate_path`: Path safety check.
5. **Implementation status:** Fully implemented.
6. **Dependencies:** Generic validations.
7. **Phase:** Phase 0 (Implementation).
8. **Usage:** Can be used in configuration loading.
9. **Interfaces:** None.

### `wakeword/` Directory

#### `wakeword/detector.py`
1. **File path:** `wakeword/detector.py`
2. **Primary purpose:** Interface for wake-word stream listening and detection.
3. **Classes defined:**
   - `WakeWordDetector`: Evaluates microphone stream for trigger.
4. **Functions/methods defined:**
   - `start`, `stop`, `listen_loop`.
   - `is_listening`, `keyword` (properties).
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Uses `core.event_bus`, `speech.microphone`.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** Engine-agnostic detector wrapper.

#### `wakeword/model.py`
1. **File path:** `wakeword/model.py`
2. **Primary purpose:** Custom wake word model interface.
3. **Classes defined:**
   - `WakeWordModel`: Custom ONNX model logic.
4. **Functions/methods defined:**
   - `load`, `predict`, `is_triggered`.
   - `frame_length`, `threshold` (properties).
5. **Implementation status:** Scaffold (methods raise `NotImplementedError`).
6. **Dependencies:** Internal logic for wake word execution.
7. **Phase:** Phase 0 (Scaffold).
8. **Usage:** Unused/Scaffold.
9. **Interfaces:** None.

---

## Repository Architecture

The ULTRON system is designed as an event-driven, decoupled desktop assistant. The architecture revolves around a centralized **Service Container** (`core/container.py`) managing the lazy loading and lifecycle of key services. These services interact globally via a Publisher-Subscriber **Event Bus** (`core/event_bus.py`). 

The overall flow is expected to be:
1. **Bootstrapping**: `main.py` loads `config`, injects settings into the Service Container, starts the EventBus and boots the `Assistant` lifecycle.
2. **Listening Phase**: `WakeWordDetector` monitors `speech.Microphone`. Once triggered, `speech.Recorder` captures audio.
3. **Intelligence Phase**: Audio is transcribed by `speech.SpeechToText`. The transcript is passed to `intelligence.IntentDetector` and decomposed by the `intelligence.Planner` via an `llm.BaseLLM`.
4. **Execution Phase**: The DAG of Tasks is sent to `intelligence.TaskRouter`, which resolves capabilities via `skills.SkillManager`.
5. **Response Phase**: System feedback is formulated into speech via `speech.TextToSpeech` and played on the system `speech.AudioPlayer`.

## Dependency Flow

```text
main.py
    ↓
core/container.py (Dependency Injection)
    ├── config/settings.py
    ├── core/event_bus.py
    ├── core/state.py
    ├── core/assistant.py
    └── core/orchestrator.py
            ↓
            ├── wakeword/detector.py
            ├── speech/microphone.py -> speech/recorder.py -> speech/speech_to_text.py
            ├── intelligence/intent_detector.py -> intelligence/planner.py -> intelligence/router.py
            ├── llm/base.py (NvidiaLLM / MockLLM)
            ├── skills/manager.py -> skills/registry.py -> skills/base.py
            └── speech/text_to_speech.py -> speech/audio_player.py
```

## Feature Mapping

| Feature | Files Responsible |
|---------|-------------------|
| Dependency Injection | `core/container.py` |
| Application Lifecycle | `core/lifecycle.py`, `core/assistant.py` |
| Event Pub/Sub System | `core/event_bus.py` |
| State Tracking | `core/state.py` |
| LLM Integration | `llm/base.py`, `llm/nvidia.py`, `llm/mock.py` |
| Speech-to-Text (STT) | `speech/speech_to_text.py` |
| Text-to-Speech (TTS) | `speech/text_to_speech.py` |
| Audio Input / VAD | `speech/microphone.py`, `speech/recorder.py` |
| Wake Word Detection | `wakeword/detector.py`, `wakeword/model.py` |
| Intent Detection | `intelligence/intent_detector.py` |
| Planning | `intelligence/planner.py` |
| Task Routing | `intelligence/router.py` |
| Skill Execution | `skills/manager.py`, `skills/registry.py`, `skills/base.py` |
| Configuration | `config/settings.py`, `config/constants.py` |

## Phase Mapping

- **Phase 0 (Implementation - Fully working infra)**
  - `main.py`
  - `config/constants.py`
  - `config/logging_config.py`
  - `config/settings.py`
  - `core/__init__.py`
  - `core/assistant.py`
  - `core/container.py`
  - `core/event_bus.py`
  - `core/lifecycle.py`
  - `core/orchestrator.py`
  - `core/state.py`
  - `utils/__init__.py`, `utils/decorators.py`, `utils/exceptions.py`, `utils/helpers.py`, `utils/validators.py`
- **Phase 0 (Scaffold - Interface Defined, raises NotImplementedError)**
  - `intelligence/intent_detector.py`, `intelligence/parser.py`, `intelligence/planner.py`, `intelligence/router.py`, `intelligence/task.py`
  - `llm/__init__.py`, `llm/base.py`, `llm/mock.py`, `llm/nvidia.py`, `llm/prompts.py`, `llm/response.py`
  - `skills/__init__.py`, `skills/base.py`, `skills/manager.py`, `skills/registry.py`
  - `speech/__init__.py`, `speech/audio_player.py`, `speech/microphone.py`, `speech/recorder.py`, `speech/speech_to_text.py`, `speech/speechconfig.py`, `speech/text_to_speech.py`
  - `wakeword/__init__.py`, `wakeword/detector.py`, `wakeword/model.py`
- **Uncategorized/Testing**
  - `speechtesting.py`

## Entry Points

- **Starts the application:** `main.py`
- **Initializes services:** `core/container.py` (eager/lazy init triggers) and `core/lifecycle.py`.
- **Handles user input:** `speech/microphone.py` & `speech/recorder.py` (Audio), `core/assistant.py` (`handle_text_input` stub) for Text.
- **Communicates with LLM:** `llm/nvidia.py` (via abstract `llm/base.py`).
- **Handles skills:** `skills/manager.py` (Dispatched by `intelligence/router.py`).
- **Manages configuration:** `config/settings.py`.

## Missing Connections

Many abstract systems exist solely as scaffolding and are completely isolated from the current runtime execution paths:
- The entire **LLM Pipeline** (`llm/`, `intelligence/`) is currently unconnected to the runtime. `core/container.py` stubs the properties out with `NotImplementedError`.
- The **Speech Pipeline** (`speech/`) is defined, but is not attached to the `core/assistant.py` runtime loop (event handlers are stubbed). `speechtesting.py` attempts a standalone loop but isn't integrated.
- The **Wake Word engine** (`wakeword/`) is detached from `core/orchestrator.py` and `core/assistant.py`.
- The **Skills engine** (`skills/`) has no specific skills implemented yet, and the `SkillManager` is just a scaffold.

## Implementation Status

- **Completed modules:** `config` module, `utils` module, `core/event_bus.py`, `core/lifecycle.py`, `core/state.py`.
- **Partially completed modules:** `core/assistant.py`, `core/container.py`, `core/orchestrator.py` (Infrastructure functions exist, but payload handlers are stubs).
- **Placeholder/scaffold modules:** `intelligence`, `llm`, `skills`, `speech`, `wakeword`. These contain fully typed abstractions, data classes, and properties, but all core implementation logic raises `NotImplementedError`.
- **Empty files:** None. All files contain docstrings, imports, and scaffolding logic.
