"""
core/validator.py – Task Validator
====================================
Ensures tasks have required parameters and are valid before execution.

Team: Core Platform Team
Phase: 2 (Executor)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from intelligence.task import Task, TaskStatus

@dataclass
class ValidationResult:
    valid: bool
    message: str
    task: Task
    warnings: list[str] = field(default_factory=list)
    missing_parameters: list[str] = field(default_factory=list)


class TaskValidator:
    """
    Validates tasks before execution.
    """

    VALID_VOLUME_ACTIONS = {"up", "down", "mute", "unmute", "max", "min", "set"}
    VALID_FOLDER_ACTIONS = {"open", "create", "list", "delete", "modify"}
    VALID_MEDIA_ACTIONS = {"pause", "resume", "play", "toggle", "next", "previous", "stop"}

    def validate(self, task: Task) -> ValidationResult:
        task.status = TaskStatus.VALIDATING

        intent = task.intent
        params = task.parameters

        if intent in ["open_application", "close_application"]:
            if not params.get("application"):
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Application name missing.",
                    task=task,
                    missing_parameters=["application"]
                )

        elif intent == "calculator":
            if not params.get("expression"):
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Invalid mathematical expression.",
                    task=task,
                    missing_parameters=["expression"]
                )

        elif intent in ["search_web", "open_website"]:
            if not params.get("url") and not params.get("query") and not params.get("website"):
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Missing 'url' or 'query'.",
                    task=task,
                    missing_parameters=["url", "query"]
                )

        elif intent == "web_lookup":
            # A lookup can always fall back to searching the words the user
            # said, so this normalises rather than rejects.
            query = str(params.get("query") or params.get("search_query") or "").strip()

            if not query:
                query = str(
                    params.get("text") or params.get("raw_utterance") or ""
                ).strip()

            if not query:
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Nothing to look up.",
                    task=task,
                    missing_parameters=["query"]
                )

            params["query"] = query

        elif intent == "play_music":
            # "Play some music" names nothing, and that is a valid request:
            # MediaSkill resumes whatever Spotify has loaded. Only normalise.
            query = str(
                params.get("query")
                or params.get("song")
                or params.get("track")
                or ""
            ).strip()

            if query:
                params["query"] = query
            else:
                params.pop("query", None)

        elif intent == "media_control":
            action = str(params.get("action") or "").strip().lower()

            if not action:
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Missing 'action' for media control.",
                    task=task,
                    missing_parameters=["action"]
                )

            if action not in self.VALID_MEDIA_ACTIONS:
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message=f"Unsupported media action: '{action}'.",
                    task=task,
                    missing_parameters=["action"]
                )

            params["action"] = action

        elif intent == "weather":
            if not params.get("location"):
                params["location"] = "Current Location"

        elif intent == "system_control":
            action = params.get("action")

            if not action:
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Missing 'action' for volume control.",
                    task=task,
                    missing_parameters=["action"]
                )

            if action not in self.VALID_VOLUME_ACTIONS:
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message=f"Unsupported volume action: '{action}'.",
                    task=task,
                    missing_parameters=["action"]
                )

            if action == "set":
                level = params.get("level")

                if level is None:
                    task.status = TaskStatus.INVALID
                    return ValidationResult(
                        valid=False,
                        message="Missing 'level' for setting volume.",
                        task=task,
                        missing_parameters=["level"]
                    )

                try:
                    level_int = int(level)
                except (TypeError, ValueError):
                    task.status = TaskStatus.INVALID
                    return ValidationResult(
                        valid=False,
                        message=f"Volume level must be a number, got: {level!r}.",
                        task=task,
                        missing_parameters=["level"]
                    )

                if not (0 <= level_int <= 100):
                    task.status = TaskStatus.INVALID
                    return ValidationResult(
                        valid=False,
                        message="Volume level must be between 0 and 100.",
                        task=task,
                        missing_parameters=["level"]
                    )

                # Normalize to int for downstream skill execution.
                params["level"] = level_int

        elif intent == "file_operation":
            action = params.get("action", "open")
            params["action"] = action

            if action not in self.VALID_FOLDER_ACTIONS:
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message=f"Unsupported folder action: '{action}'.",
                    task=task,
                    missing_parameters=["action"]
                )

            if not params.get("folder_name"):
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Missing 'folder_name'.",
                    task=task,
                    missing_parameters=["folder_name"]
                )

            if action == "modify" and not params.get("new_name") and not params.get("destination"):
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="'modify' requires 'new_name' and/or 'destination'.",
                    task=task,
                    missing_parameters=["new_name", "destination"]
                )

        elif intent == "memory_forget":
            if not str(params.get("target") or "").strip():
                task.status = TaskStatus.INVALID
                return ValidationResult(
                    valid=False,
                    message="Missing 'target' for forgetting.",
                    task=task,
                    missing_parameters=["target"]
                )

        elif intent in ["screenshot", "greeting", "farewell", "time", "date", "memory_recall"]:
            pass  # Always valid

        task.status = TaskStatus.VALID
        return ValidationResult(
            valid=True,
            message="Validation Passed",
            task=task
        )