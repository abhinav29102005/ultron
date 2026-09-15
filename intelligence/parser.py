"""
planner/parser.py – LLM Response Parser & STT Parser
======================================================
Defines parser utility functions for LLM structured output and STT text.

Team: Planner Team
Phase: 2 (Intent Detection)
"""

from __future__ import annotations

import json
import re
from typing import Any


class ResponseParser:
    """
    Parser helper for LLM outputs.
    """

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        """
        Parse raw LLM string into JSON dictionary.
        """
        json_str = ResponseParser.extract_first_json(text)
        if json_str:
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def parse_json_list(text: str) -> list[dict[str, Any]]:
        """
        Parse raw LLM string into list of JSON objects.
        """
        json_str = ResponseParser.extract_first_json(text)
        if json_str:
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return []

    @staticmethod
    def extract_first_json(text: str) -> str:
        """
        Regex extract JSON code block or object.
        """
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            return match.group(1)
        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if match:
            return match.group(1)
        return ""


class STTParser:
    """
    Parses STT output, normalizes text, removes fillers, and extracts entities.
    """

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize STT output."""
        text = text.lower()
        # Keep every character that still carries meaning downstream: math
        # operators for the calculator, slashes and colons for URLs, and
        # apostrophes for contractions. The previous whitelist dropped * and /,
        # which silently turned "15 * 4" into "15  4" before the LLM saw it.
        text = re.sub(r"[^\w\s\.\+\-\*/\(\)%:',]", "", text)
        return text.strip()

    @staticmethod
    def remove_fillers(text: str) -> str:
        """Remove filler words."""
        for filler in ["you know"]:
            text = text.replace(filler, "")
        
        words = text.split()
        filtered = [w for w in words if w not in {"uh", "um", "like", "basically", "actually", "just", "so", "well"}]
        return " ".join(filtered).strip()

    @staticmethod
    def extract_entities(text: str) -> dict[str, Any]:
        """Extract entities using deterministic rules (regex/keyword matching)."""
        entities = {}
        
        # URL / Website extraction
        website_match = re.search(r'\b(?:go to|open|visit)\s+([a-zA-Z0-9\-\.]+\.(?:com|org|net|io|co))\b', text)
        if website_match:
            entities['website'] = website_match.group(1)
            
        # Application extraction
        app_match = re.search(r'\b(?:open|launch|start|close|exit|quit)\s+(?:the\s+)?([a-zA-Z0-9]+)(?:\s+app)?\b', text)
        if app_match and 'website' not in entities:
            app_name = app_match.group(1)
            if app_name not in ["website", "browser", "search", "app"]:
                entities['application'] = app_name

        # Search query
        search_match = re.search(r'\b(?:search|look up|google)\s+(?:for\s+)?(.*)', text)
        if search_match:
            entities['search_query'] = search_match.group(1).strip()
            
        # File operations
        file_match = re.search(r'\b(?:create|delete|move|copy|rename)\s+(?:file|folder|directory)\s+([a-zA-Z0-9\-\.]+)\b', text)
        if file_match:
            entities['file_name'] = file_match.group(1)

        # Arithmetic expression, for the rule-based path used when the LLM is
        # unavailable. MathSkill normalises spoken operators itself, so loosely
        # grabbing the digits-and-operators run is enough here.
        math_match = re.search(
            r'(\d+(?:\.\d+)?(?:\s*(?:[\+\-\*/x]|times|plus|minus|divided by|over)'
            r'\s*\d+(?:\.\d+)?)+)',
            text,
        )
        if math_match:
            entities['expression'] = math_match.group(1).strip()
            
        return entities

    @staticmethod
    def parse(text: str) -> dict[str, Any]:
        """Return structured data for the intent detector."""
        normalized = STTParser.normalize(text)
        cleaned = STTParser.remove_fillers(normalized)
        entities = STTParser.extract_entities(cleaned)
        return {
            "normalized_text": cleaned,
            "entities": entities
        }
