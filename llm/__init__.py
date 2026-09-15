"""
llm/__init__.py – LLM Package
==============================
The ``llm`` package provides a clean, provider-agnostic interface for
interacting with Large Language Models in ULTRON.

Architecture:
    - :class:`~llm.base.BaseLLM` defines the abstract contract.
    - :class:`~llm.nvidia.NvidiaLLM` is the production implementation.
    - :class:`~llm.mock.MockLLM` is used for offline testing and development.
    - :class:`~llm.prompts.PromptLibrary` holds system and few-shot prompts.
    - :class:`~llm.response.LLMResponse` is the typed response envelope.

Team: LLM Team
Phase: 0 (Scaffold) → Phase 1 (Implementation)
"""

from llm.base import BaseLLM
from llm.mock import MockLLM
from llm.nvidia import NvidiaLLM
from llm.response import LLMResponse

__all__: list[str] = [
    "BaseLLM",
    "MockLLM",
    "NvidiaLLM",
    "LLMResponse",
]
