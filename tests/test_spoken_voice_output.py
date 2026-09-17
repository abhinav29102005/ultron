"""
tests/test_spoken_voice_output.py
=================================
Validates spoken audio output, Piper TTS synthesis with Ultron DSP effect,
clean_for_speech text normalization, and voice turn auto-speech dispatch.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from speech.text_to_speech.tts_pipeline import clean_for_speech, play_audio
from speech.text_to_speech.speaker import Speaker
from core.assistant import Assistant
from core.event_bus import UserInputEvent
from config.user_settings import UserSettings
from utils.cli_dashboard import CyberneticCLI


def test_clean_for_speech_markdown_and_citations():
    raw = (
        "### Operational Status\n"
        "All systems are **nominal** and *ready*.\n"
        "Here is the plan [Doc_01 §4]:\n"
        "- Step 1: Initialize core\n"
        "- Step 2: Open link https://example.com\n"
        "```python\nprint('hello')\n```\n"
        "Done with `inline_command`."
    )
    cleaned = clean_for_speech(raw)
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "[Doc_01 §4]" not in cleaned
    assert "https://example.com" not in cleaned
    assert "```" not in cleaned
    assert "All systems are nominal and ready." in cleaned
    assert "inline_command" in cleaned


def test_speaker_piper_voice_loaded():
    speaker = Speaker()
    assert speaker.voice is not None
    chunks = list(speaker.generate("Ultron is operational."))
    assert len(chunks) > 0
    first_chunk = chunks[0]
    assert hasattr(first_chunk, "audio_float_array")
    assert len(first_chunk.audio_float_array) > 0
    assert first_chunk.sample_rate > 0


@pytest.mark.asyncio
async def test_assistant_speaks_on_voice_input_turn():
    container = MagicMock()
    container.settings = MagicMock()
    container.user_settings = UserSettings(voice_enabled=False)
    container.state = MagicMock()
    container.state.mode = MagicMock()
    container.state.last_response = ""
    container.state.conversation_history = []
    container.event_bus = MagicMock()
    container.event_bus.handler_count.return_value = 1

    assistant = Assistant(container)
    assistant._tts_available = True

    with patch("speech.text_to_speech.tts_pipeline.play_audio") as mock_play:
        # Simulate a voice turn (Push-to-Talk or Wake-Word)
        container.state.last_user_input_source = "voice"
        assistant._speak("Acknowledged, speaking response.")
        
        # Should have scheduled speech task
        assert len(assistant._speech_tasks) == 1
        # Wait briefly for thread to dispatch
        await asyncio.sleep(0.05)
        mock_play.assert_called_once_with("Acknowledged, speaking response.")


@pytest.mark.asyncio
async def test_assistant_stays_silent_on_text_turn_with_voice_disabled():
    container = MagicMock()
    container.settings = MagicMock()
    container.user_settings = UserSettings(voice_enabled=False)
    container.state = MagicMock()
    container.state.mode = MagicMock()
    container.event_bus = MagicMock()

    assistant = Assistant(container)
    assistant._tts_available = True

    with patch("speech.text_to_speech.tts_pipeline.play_audio") as mock_play:
        # Simulate typed text turn with voice_enabled=False
        container.state.last_user_input_source = "text"
        assistant._speak("Silent response.")
        
        # Should NOT have scheduled speech task
        assert len(assistant._speech_tasks) == 0
        mock_play.assert_not_called()


@pytest.mark.asyncio
async def test_assistant_speaks_on_text_turn_with_voice_enabled():
    container = MagicMock()
    container.settings = MagicMock()
    container.user_settings = UserSettings(voice_enabled=True)
    container.state = MagicMock()
    container.state.mode = MagicMock()
    container.event_bus = MagicMock()

    assistant = Assistant(container)
    assistant._tts_available = True

    with patch("speech.text_to_speech.tts_pipeline.play_audio") as mock_play:
        # Simulate typed text turn with voice_enabled=True
        container.state.last_user_input_source = "text"
        assistant._speak("Spoken response.")
        
        assert len(assistant._speech_tasks) == 1
        await asyncio.sleep(0.05)
        mock_play.assert_called_once_with("Spoken response.")


@pytest.mark.asyncio
async def test_cli_mode_switches_activate_voice_enabled():
    sm = MagicMock()
    sm.active_session = MagicMock()
    sm.db = MagicMock()
    settings = UserSettings(voice_enabled=False)
    cli = CyberneticCLI(sm, settings)

    assert settings.voice_enabled is False

    res = await cli.handle_command("/nowake")
    assert res == "switch_mode:no-wake"
    assert settings.voice_enabled is True

    # Reset and test /mode wakeword
    settings.voice_enabled = False
    res = await cli.handle_command("/mode wakeword")
    assert res == "switch_mode:wakeword"
    assert settings.voice_enabled is True
