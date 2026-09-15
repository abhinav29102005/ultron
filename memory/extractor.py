"""
memory/extractor.py – Durable Fact Extraction
===============================================
Asks the LLM which durable personal facts an utterance contains and parses
the JSON it returns. Owns the prompt; never touches disk.

Team: Core Platform Team
Phase: 3 (Context Memory)
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from config.logging_config import get_logger

if TYPE_CHECKING:
    from llm.base import BaseLLM

logger = get_logger("memory.extractor")


class FactExtractor:
    """
    Turns a user utterance into a list of (key, value) facts using the LLM.
    """

    def __init__(self, llm: BaseLLM) -> None:
        """
        Initialise FactExtractor.

        Args:
            llm: The configured language model provider.
        """
        self.llm = llm

    async def extract(self, utterance: str) -> list[tuple[str, str]]:
        """
        Extract durable personal facts from a single utterance.

        Args:
            utterance: The words the user actually said.

        Returns:
            A list of (key, value) pairs; empty when there is nothing durable
            to remember or when extraction failed for any reason.
        """
        if not utterance or not utterance.strip():
            return []

        messages = [
            self.llm.build_system_message(self._system_prompt()),
            self.llm.build_user_message(utterance.strip()),
        ]

        try:
            # json_mode=True is required: _parse_llm_response does a bare
            # json.loads, and the provider returns prose unless asked otherwise.
            response = await self.llm.complete(messages, json_mode=True)
            return self._parse_llm_response(response.content)
        except Exception as exc:
            # Memory is an enhancement, never a dependency: a model that is
            # down or off-format simply means nothing new is remembered.
            logger.debug(f"Fact extraction failed for {utterance!r}: {exc}")
            return []

    def _system_prompt(self) -> str:
        """
        Build the extraction prompt.

        Returns:
            The system prompt instructing the model to emit fact JSON.
        """
        return """
You are the long-term memory extractor for the ULTRON desktop assistant.

Read the user's message and pull out ONLY durable personal facts that the
user stated about THEMSELVES: their name, job, where they live, their
preferences, the projects they work on, their relationships, and the things
they own.

Extract NOTHING from commands, questions, or transient statements.
"Open Chrome", "what time is it", "I am tired right now" carry no durable
fact — return an empty array for those.

Keys must be short snake_case nouns, e.g. "name", "job", "favourite_editor".
Values must be short and self-contained: readable on their own without the
original sentence.

Return ONLY valid JSON.
Do not use markdown.
Do not include explanations.

Required JSON format:

{
  "facts": [
    {"key": "one_snake_case_noun", "value": "short self-contained value"}
  ]
}

Examples:

User: "My name is Ola and I work as a backend engineer"
{
  "facts": [
    {"key": "name", "value": "Ola"},
    {"key": "job", "value": "Backend engineer"}
  ]
}

User: "I use VS Code for everything and I live in Lagos"
{
  "facts": [
    {"key": "favourite_editor", "value": "VS Code"},
    {"key": "location", "value": "Lagos"}
  ]
}

User: "Open Chrome and search for AI news"
{
  "facts": []
}

Return JSON only.
"""

    def _parse_llm_response(self, content: str) -> list[tuple[str, str]]:
        """
        Parse the model's JSON into (key, value) pairs.

        Args:
            content: Raw text returned by the model.

        Returns:
            The extracted pairs.

        Raises:
            ValueError: If the payload is not the expected shape.
            json.JSONDecodeError: If the payload is not valid JSON.
        """
        content = (content or "").strip()

        # Remove markdown code fences if the model accidentally adds them.
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        result: Any = json.loads(content)

        if not isinstance(result, dict) or "facts" not in result:
            raise ValueError("LLM response missing 'facts' array.")

        facts = result["facts"]

        if not isinstance(facts, list):
            raise ValueError("'facts' must be a JSON array.")

        pairs: list[tuple[str, str]] = []

        for item in facts:
            if not isinstance(item, dict):
                continue

            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()

            if key and value:
                pairs.append((key, value))

        return pairs
