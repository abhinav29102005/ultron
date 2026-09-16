"""
Regression tests for llm/switcher.py.

Bug this covers: clicking the model button switched to NVIDIA even with no
API key. switch() accepted it, then *every subsequent message* died inside
intent detection with "NVIDIA_API_KEY not set in configuration". The
assistant looked randomly broken and stayed broken until you toggled back.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from config.settings import Settings
from llm.switcher import LLMSwitcher


def _settings(nvidia_key: str = "", provider: str = "qwen", groq_key: str = "") -> Settings:
    s = Settings()
    s.groq_api_key = SecretStr(groq_key)
    s.nvidia_api_key = SecretStr(nvidia_key)
    s.llm_provider = provider
    return s


@pytest.fixture(autouse=True)
def ollama_up(monkeypatch):
    """Pretend Ollama is running unless a test says otherwise.

    Qwen availability is now a live probe rather than a constant, so without
    this the whole file would depend on whether the developer happened to
    have `ollama serve` running.
    """
    monkeypatch.setattr(
        "utils.preflight.probe_ollama", lambda base_url, **kw: ["qwen2.5:3b"]
    )


@pytest.fixture
def ollama_down(monkeypatch):
    monkeypatch.setattr("utils.preflight.probe_ollama", lambda base_url, **kw: None)


class TestProviderAvailability:
    def test_qwen_is_available_when_ollama_is_running(self):
        assert LLMSwitcher(_settings()).is_available("qwen") is True

    def test_qwen_is_unavailable_when_ollama_is_down(self, ollama_down):
        """The regression: a local model needing no API key was treated as
        permanently usable, so a stopped Ollama was only discovered one dead
        message at a time."""
        assert LLMSwitcher(_settings()).is_available("qwen") is False

    def test_available_providers_is_empty_when_nothing_is_usable(self, ollama_down):
        assert LLMSwitcher(_settings()).available_providers() == []

    def test_switching_to_qwen_with_ollama_down_raises(self, ollama_down):
        sw = LLMSwitcher(_settings(nvidia_key="sk-test", provider="nvidia"))
        with pytest.raises(ValueError, match="Ollama is not responding"):
            sw.switch("qwen")

    def test_nvidia_unavailable_without_a_key(self):
        assert LLMSwitcher(_settings(nvidia_key="")).is_available("nvidia") is False

    def test_nvidia_available_with_a_key(self):
        assert LLMSwitcher(_settings(nvidia_key="sk-test")).is_available("nvidia") is True

    def test_unknown_provider_is_not_available(self):
        assert LLMSwitcher(_settings()).is_available("llama") is False

    def test_available_providers_excludes_the_unconfigured_one(self):
        assert LLMSwitcher(_settings()).available_providers() == ["qwen"]

    def test_available_providers_lists_both_when_configured(self):
        assert LLMSwitcher(_settings(nvidia_key="sk-test")).available_providers() == [
            "qwen",
            "nvidia",
        ]


class TestSwitchRefusesUnusableProviders:
    def test_switching_to_unconfigured_nvidia_raises(self):
        sw = LLMSwitcher(_settings())
        with pytest.raises(ValueError, match="not configured"):
            sw.switch("nvidia")

    def test_provider_is_unchanged_after_a_refused_switch(self):
        """The regression itself: a failed switch must not corrupt state."""
        sw = LLMSwitcher(_settings())
        with pytest.raises(ValueError):
            sw.switch("nvidia")
        assert sw.current_provider == "qwen"

    def test_assistant_still_works_after_a_refused_switch(self):
        sw = LLMSwitcher(_settings())
        with pytest.raises(ValueError):
            sw.switch("nvidia")
        # Before the fix this raised NVIDIA_API_KEY not set.
        assert sw.build_system_message("hello")

    def test_switching_to_configured_nvidia_is_allowed(self):
        sw = LLMSwitcher(_settings(nvidia_key="sk-test"))
        sw.switch("nvidia")
        assert sw.current_provider == "nvidia"

    def test_unknown_provider_still_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMSwitcher(_settings()).switch("llama")
