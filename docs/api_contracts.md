# API Contracts

## Service Container Resolution Keys
- `settings` -> config.settings.Settings
- `event_bus` -> core.event_bus.EventBus
- `state` -> core.state.AssistantState
- `assistant` -> core.assistant.Assistant
- `orchestrator` -> core.orchestrator.Orchestrator
- `llm` -> llm.base.BaseLLM
- `stt` -> speech.speech_to_text.Transcriber
- `tts` -> speech.text_to_speech.Speaker
- `planner` -> planner.planner.Planner
- `skill_manager` -> skills.manager.SkillManager

## Exception Hierarchy
- FridayBaseError
  - AssistantNotInitialisedError
  - ConfigurationError
  - LLMError
  - SpeechError
  - WakeWordError
  - PlannerError
  - SkillError

## Dataclass Interfaces
- ConversationTurn (fields only)
- AssistantState (fields only)
- Task (fields only)
- DetectedIntent (fields only)
- LLMResponse (fields only)
