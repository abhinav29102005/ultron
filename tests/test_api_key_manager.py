"""
tests/test_api_key_manager.py – Test suite for Cloud LLM Key Hub & Setup Wizard
"""

import os
import pytest
from pathlib import Path
from utils.api_key_manager import (
    PROVIDERS,
    update_env_file,
    set_key_for_provider,
    has_any_cloud_key,
    render_provider_hub,
)


def test_providers_metadata():
    """Verify all required cloud providers have direct portal URLs and configuration."""
    required = ["nvidia", "groq", "openrouter", "openai", "anthropic", "picovoice"]
    for prov_id in required:
        assert prov_id in PROVIDERS, f"Missing provider: {prov_id}"
        p = PROVIDERS[prov_id]
        assert p.portal_url.startswith("https://")
        assert len(p.free_tier_info) > 10
        assert p.env_var != ""


def test_update_env_file(tmp_path):
    """Verify update_env_file writes new keys or updates existing values."""
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING_KEY=old_val\n", encoding="utf-8")

    # Update existing
    ok = update_env_file("EXISTING_KEY", "new_val", str(env_file))
    assert ok
    content = env_file.read_text(encoding="utf-8")
    assert "EXISTING_KEY=new_val" in content

    # Append new key
    ok = update_env_file("NEW_KEY", "secret_123", str(env_file))
    assert ok
    content = env_file.read_text(encoding="utf-8")
    assert "NEW_KEY=secret_123" in content
    assert os.getenv("NEW_KEY") == "secret_123"


def test_set_key_for_provider(tmp_path, monkeypatch):
    """Test setting key with validation for valid and invalid providers."""
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    # Mock default env path
    monkeypatch.setattr("utils.api_key_manager.update_env_file", 
                        lambda k, v: update_env_file(k, v, str(env_file)))

    # Valid provider
    try:
        ok, msg = set_key_for_provider("groq", "gsk_test_key_123")
        assert ok
        assert "Successfully saved" in msg
        assert os.getenv("GROQ_API_KEY") == "gsk_test_key_123"
        assert os.getenv("LLM_PROVIDER") == "groq"
    finally:
        os.environ.pop("GROQ_API_KEY", None)
        os.environ.pop("LLM_PROVIDER", None)

    # Empty key error
    ok, msg = set_key_for_provider("groq", "   ")
    assert not ok
    assert "cannot be empty" in msg

    # Unknown provider
    ok, msg = set_key_for_provider("unknown_llm", "key_123")
    assert not ok
    assert "Unknown provider" in msg


def test_has_any_cloud_key(monkeypatch):
    """Verify detection of cloud keys."""
    for p in PROVIDERS.values():
        monkeypatch.delenv(p.env_var, raising=False)

    assert not has_any_cloud_key()

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test123")
    assert has_any_cloud_key()
