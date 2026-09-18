import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import Settings
from config.user_settings import UserSettings
from core.assistant import Assistant
from core.container import ServiceContainer
from skills.chat_skill import ChatSkill


@pytest.mark.asyncio
async def test_chat_skill_verbosity_directives():
    mock_container = MagicMock()
    mock_container.user_settings = UserSettings(verbosity="moderate", user_name="Alice", user_email="alice@example.com")
    mock_container.memory.render_block.return_value = ""

    skill = ChatSkill(mock_container)

    # Test short
    assert skill._resolve_verbosity("summarize this keep it short") == "short"
    # Test detailed
    assert skill._resolve_verbosity("explain quantum mechanics in detail") == "detailed"
    # Test default moderate
    assert skill._resolve_verbosity("what is the distance to the moon") == "moderate"

    mock_llm = MagicMock()
    mock_llm.build_system_message.side_effect = lambda prompt: {"role": "system", "content": prompt}
    mock_llm.build_user_message.side_effect = lambda text: {"role": "user", "content": text}

    # Verify short directive in system prompt
    msgs_short = skill._build_messages(mock_llm, "keep it short please")
    sys_short = msgs_short[0]["content"]
    assert "RESPONSE LENGTH DIRECTIVE: SHORT" in sys_short
    assert "Alice" in sys_short
    assert "alice@example.com" in sys_short

    # Verify detailed directive in system prompt
    msgs_detailed = skill._build_messages(mock_llm, "explain in depth")
    sys_detailed = msgs_detailed[0]["content"]
    assert "RESPONSE LENGTH DIRECTIVE: DETAILED" in sys_detailed

    # Verify moderate directive in system prompt
    msgs_mod = skill._build_messages(mock_llm, "how does gravity work")
    sys_mod = msgs_mod[0]["content"]
    assert "RESPONSE LENGTH DIRECTIVE: MODERATE" in sys_mod


@pytest.mark.asyncio
async def test_assistant_profile_and_intro_fast_path():
    container = ServiceContainer(Settings())
    assistant = Assistant(container)

    # 1. /profile before setting
    p1 = await assistant._check_fast_path("/profile")
    assert "User Profile:" in p1
    assert "(Not set" in p1

    # 2. Conversational introduction
    intro = await assistant._check_fast_path("My name is John Doe and my email is john@test.com")
    assert "John Doe" in intro
    assert "john@test.com" in intro

    # 3. /profile after setting
    p2 = await assistant._check_fast_path("/profile")
    assert "John Doe" in p2
    assert "john@test.com" in p2

    # 4. /profile set verbosity detailed
    v_res = await assistant._check_fast_path("/profile set verbosity detailed")
    assert "detailed" in v_res.lower()
    assert container.user_settings.verbosity == "detailed"


@pytest.mark.asyncio
async def test_assistant_fallback_chat_resilience():
    container = ServiceContainer(Settings())
    assistant = Assistant(container)

    with patch.object(assistant, "_respond") as mock_respond, \
         patch("skills.chat_skill.ChatSkill.execute", new_callable=AsyncMock) as mock_chat_exec:
        
        mock_chat_exec.return_value = "Dual LLM synthesized conversational answer."

        await assistant._fallback_chat("How does photosynthesis work?")
        mock_respond.assert_called_once_with("Dual LLM synthesized conversational answer.")
