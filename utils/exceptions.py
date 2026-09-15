"""
utils/exceptions.py – Exception Hierarchy for ULTRON
=====================================================
Defines all custom exceptions for the application and its subsystems.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations


class UltronError(Exception):
    """
    Base exception class for all errors in the ULTRON system.
    """

    def __init__(self, message: str = "", *args: object) -> None:
        super().__init__(message, *args)
        self.message = message

    def __str__(self) -> str:
        return self.message


# Deprecated aliases – kept for backward compatibility
FridayError = UltronError
FridayBaseError = UltronError


class AssistantNotInitialisedError(UltronError):
    """
    Raised when a method is called before the Assistant has been started.
    """
    pass


class ConfigurationError(UltronError):
    """
    Raised when there is a configuration error (e.g. missing environment variables or validation errors).
    """
    pass


class EventBusError(UltronError):
    """
    Raised when an error occurs in the EventBus operations.
    """
    pass


class ValidationError(UltronError):
    """
    Raised when input validation fails.
    """
    pass


class ServiceNotFoundError(UltronError):
    """
    Raised when a requested service cannot be resolved from the container.
    """
    pass


# ── Subsystem exceptions ──────────────────────────────────────────────────────

class LLMError(UltronError):
    """Base class for all LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM API call exceeds the configured timeout."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when the LLM API rejects the provided credentials."""
    pass


class SpeechError(UltronError):
    """Base class for all speech subsystem errors."""
    pass


class MicrophoneError(SpeechError):
    """Raised when the microphone cannot be opened or read from."""
    pass


class STTError(SpeechError):
    """Raised when speech-to-text transcription fails."""
    pass


class TTSError(SpeechError):
    """Raised when text-to-speech synthesis fails."""
    pass


class WakeWordError(UltronError):
    """Raised when the wake-word detection engine fails."""
    pass


class PlannerError(UltronError):
    """Base class for planner / intent errors."""
    pass


class IntentDetectionError(PlannerError):
    """Raised when intent detection cannot classify the user utterance."""
    pass


class SkillError(UltronError):
    """Base class for skill execution errors."""
    pass


class SkillNotFoundError(SkillError):
    """Raised when the requested skill is not registered in the registry."""
    pass


class SkillExecutionError(SkillError):
    """Raised when a skill raises an unexpected exception during execution."""
    pass
