"""
tests/test_groq_llm.py – Unit tests for Groq LLM Provider
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import SecretStr

from config.settings import Settings
from llm.groq import GroqLLM


def test_groq_llm_auto_migrates_deprecated_models():
    settings = Settings(
        groq_api_key=SecretStr("gsk_test1234567890"),
        groq_model="llama-3.3-70b-versatile",
        groq_fast_model="llama-3.1-8b-instant",
    )
    llm = GroqLLM(settings)
    assert llm.model == "openai/gpt-oss-120b"
    assert llm._fast_model == "openai/gpt-oss-20b"


def test_groq_llm_accepts_valid_model():
    settings = Settings(
        groq_api_key=SecretStr("gsk_test1234567890"),
        groq_model="openai/gpt-oss-120b",
        groq_fast_model="openai/gpt-oss-20b",
    )
    llm = GroqLLM(settings)
    assert llm.model == "openai/gpt-oss-120b"
    assert llm._fast_model == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_groq_llm_complete_auto_recovers_from_model_not_found():
    settings = Settings(
        groq_api_key=SecretStr("gsk_test1234567890"),
        groq_model="some-old-model",
        groq_fast_model="openai/gpt-oss-20b",
    )
    llm = GroqLLM(settings)

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Hello!"), finish_reason="stop")]
    mock_resp.usage = MagicMock(prompt_tokens=5, completion_tokens=2)

    # First call raises 404 model_not_found, second call succeeds with openai/gpt-oss-120b
    calls = []
    async def fake_create(*args, **kwargs):
        calls.append(kwargs.get("model"))
        if len(calls) == 1:
            raise Exception("Error code: 404 - {'error': {'message': 'The model does not exist', 'code': 'model_not_found'}}")
        return mock_resp

    with patch.object(llm._client.chat.completions, "create", side_effect=fake_create):
        resp = await llm.complete([{"role": "user", "content": "hi"}])
        assert resp.content == "Hello!"
        assert calls == ["some-old-model", "openai/gpt-oss-120b"]
        assert llm.model == "openai/gpt-oss-120b"
