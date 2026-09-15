"""
llm/prompts.py – Prompt Library
=================================
Centralises prompt templates.
All methods raise NotImplementedError.

Team: LLM Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations


class PromptLibrary:
    """
    Prompt library.
    All methods raise NotImplementedError.
    """

    SYSTEM_BASE: str
    INTENT_DETECTION: str
    PLANNER: str

    @staticmethod
    def build_conversation_prompt(
        conversation_history: list[dict[str, str]],
        user_input: str,
    ) -> list[dict[str, str]]:
        """
        Build the conversation prompt sequence.
        TODO: Implement prompt construction.
        """
        raise NotImplementedError

    @staticmethod
    def build_intent_prompt(user_input: str) -> list[dict[str, str]]:
        """
        Build the intent classifier prompt sequence.
        TODO: Implement intent prompt construction.
        """
        raise NotImplementedError

    @staticmethod
    def build_planner_prompt(intent: str, entities: dict[str, object]) -> list[dict[str, str]]:
        """
        Build the planner prompt sequence.
        TODO: Implement planner prompt construction.
        """
        raise NotImplementedError
