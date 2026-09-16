"""
llm/switcher.py – Switchable LLM Provider
==========================================
Wraps NVIDIA NIM and local Qwen (Ollama) providers
behind a single BaseLLM interface, allowing runtime switching.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING

from llm.base import BaseLLM
from llm.response import LLMResponse, LLMUsage

if TYPE_CHECKING:
    from config.settings import Settings


class LLMSwitcher(BaseLLM):
    """
    Delegate LLM that can switch between configured providers at runtime.
    """

    def __init__(self, settings: Settings) -> None:
        # Initialize with settings; inner LLMs are created lazily
        super().__init__(
            model=settings.nvidia_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        self._settings = settings
        self._provider = settings.llm_provider.lower()
        self._nvidia: BaseLLM | None = None
        self._qwen: BaseLLM | None = None
        self._groq: BaseLLM | None = None

    def _get_groq(self) -> BaseLLM:
        if self._groq is None:
            from llm.groq import GroqLLM
            self._groq = GroqLLM(self._settings)
        return self._groq

    def _get_nvidia(self) -> BaseLLM:
        if self._nvidia is None:
            from llm.nvidia import NvidiaLLM
            self._nvidia = NvidiaLLM(self._settings)
        return self._nvidia

    def _get_qwen(self) -> BaseLLM:
        if self._qwen is None:
            from llm.qwen import QwenLLM
            self._qwen = QwenLLM(self._settings)
        return self._qwen

    def _active(self) -> BaseLLM:
        provider = self._provider
        if provider == "groq":
            return self._get_groq()
        if provider == "qwen":
            return self._get_qwen()
        if provider == "nvidia":
            return self._get_nvidia()
        return self._get_groq() if self.is_available("groq") else self._get_nvidia()

    def is_available(self, provider: str) -> bool:
        provider = (provider or "").lower()
        if provider == "groq":
            key = getattr(self._settings, "groq_api_key", None)
            value = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key or "")
            return bool(value and not value.startswith("your_"))
        if provider == "nvidia":
            key = self._settings.nvidia_api_key
            value = key.get_secret_value() if hasattr(key, "get_secret_value") else key
            return bool(value and not str(value).startswith("your_"))
        if provider == "qwen":
            from utils.preflight import probe_ollama
            return probe_ollama(self._settings.ollama_base_url) is not None
        return False

    def available_providers(self) -> list[str]:
        return [p for p in ("groq", "qwen", "nvidia") if self.is_available(p)]

    def switch(self, provider: str) -> None:
        provider = provider.lower()
        if provider not in ("groq", "nvidia", "qwen"):
            raise ValueError(f"Unknown LLM provider: {provider}. Use 'groq', 'nvidia' or 'qwen'.")
        if not self.is_available(provider):
            # Refuse here, where the caller can report it, rather than letting
            # every later request blow up.
            reason = (
                "NVIDIA_API_KEY is not set"
                if provider == "nvidia"
                else f"Ollama is not responding at {self._settings.ollama_base_url}"
            )
            raise ValueError(
                f"{provider.upper()} is not configured "
                f"({reason}), so it cannot be selected."
            )
        self._provider = provider

    @property
    def current_provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._active().model

    @model.setter
    def model(self, value: str) -> None:
        pass  # delegated to active provider

    @property
    def temperature(self) -> float:
        return self._active().temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        pass

    @property
    def max_tokens(self) -> int:
        return self._active().max_tokens

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        pass

    @property
    def provider_name(self) -> str:
        return f"switcher({self._provider})"

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> LLMResponse:
        return await self._active().complete(messages, **kwargs)

    async def complete_with_tools(self, messages: list[dict], tools: list[dict], **kwargs):
        return await self._active().complete_with_tools(messages, tools, **kwargs)

    async def stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncIterator[str]:
        async for chunk in self._active().stream(messages, **kwargs):
            yield chunk

    def build_system_message(self, content: str) -> dict[str, str]:
        return self._active().build_system_message(content)

    def build_user_message(self, content: str) -> dict[str, str]:
        return self._active().build_user_message(content)

    def build_assistant_message(self, content: str) -> dict[str, str]:
        return self._active().build_assistant_message(content)
