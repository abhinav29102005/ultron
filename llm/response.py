"""
llm/response.py – LLM Response Envelope
=========================================
Defines the output structure of LLM completions.
These are dataclasses containing fields only.

Team: LLM Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class LLMUsage:
    """
    Token usage metrics.
    Contains fields only.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """
    Standardised LLM completion output.
    Contains fields only.
    """

    content: str
    model: str
    finish_reason: str
    usage: LLMUsage
    provider: str
    latency_ms: float
    timestamp: datetime
    raw: object
