"""
llm/base.py – Abstract LLM Base Class
=======================================
Defines the abstract base class for LLMs.
Uses the ABC class style.

Team: LLM Team
Phase: 0 (Scaffold)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator

from llm.response import LLMResponse

if TYPE_CHECKING:
    from llm.tools import ToolCallResponse


class BaseLLM(ABC):
    """
    Abstract Base Class for LLM providers.
    """

    def __init__(
        self,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> LLMResponse:
        """
        Complete a chat sequence.
        TODO: Implement in concrete LLM provider.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> AsyncIterator[str]:
        """
        Stream chat tokens.
        TODO: Implement in concrete LLM provider.
        """
        ...

    async def complete_with_tools(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        **kwargs: object,
    ) -> "ToolCallResponse":
        """Complete a chat sequence in which the model may call tools.

        Not abstract, and not silently ignoring ``tools``: a provider that
        cannot do function calling raises, and the assistant catches that to
        fall back to the intent-classifier pipeline. Returning a plain answer
        instead would look like a model that simply chose not to use a tool,
        which is indistinguishable from working and impossible to fall back
        from.
        """
        from llm.tools import ToolsUnsupportedError

        raise ToolsUnsupportedError(
            f"{type(self).__name__} does not support tool calling."
        )

    def build_system_message(self, content: str) -> dict[str, str]:
        """Format a system message dictionary."""
        return {"role": "system", "content": content}

    def build_user_message(self, content: str) -> dict[str, str]:
        """Format a user message dictionary."""
        return {"role": "user", "content": content}

    def build_assistant_message(self, content: str) -> dict[str, str]:
        """Format an assistant message dictionary."""
        return {"role": "assistant", "content": content}

    @property
    def provider_name(self) -> str:
        """
        Get the provider identifier.
        TODO: Implement provider name getter.
        """
        raise NotImplementedError
