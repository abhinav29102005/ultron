import pytest
from core.database import DatabaseManager
from core.session_manager import SessionManager
from config.user_settings import UserSettings
from utils.cli_dashboard import CyberneticCLI


async def create_test_db(tmp_path) -> DatabaseManager:
    db_file = tmp_path / "test_ultron.db"
    db = DatabaseManager(f"sqlite+aiosqlite:///{db_file}")
    await db.initialize()
    return db


@pytest.mark.asyncio
async def test_session_lifecycle(tmp_path):
    test_db = await create_test_db(tmp_path)
    try:
        sm = SessionManager(test_db)
        s1 = await sm.initialize(default_title="Sprint Planning")
        assert s1.id.startswith("chat_")
        assert s1.title == "Sprint Planning"

        # Add message turn
        await sm.record_turn("user", "What is the project milestone?", latency_ms=15.0, prompt_tokens=8)
        await sm.record_turn(
            "assistant",
            "Milestone 1 completes by tomorrow.",
            citations=["Doc_01 §2"],
            latency_ms=110.0,
            completion_tokens=14,
        )

        # Verify context window
        cw = await sm.get_context_window()
        assert len(cw) == 2
        assert cw[0]["role"] == "user"
        assert cw[1]["role"] == "assistant"

        # Verify token totals
        assert sm.active_session.prompt_tokens == 8
        assert sm.active_session.completion_tokens == 14
        assert sm.active_session.total_tokens == 22

        # Create second session and switch
        s2 = await sm.create_session("Architecture Review")
        assert s2.title == "Architecture Review"
        sessions = await sm.list_sessions()
        assert len(sessions) == 2

        # Switch back to s1
        switched = await sm.switch_session(s1.id)
        assert switched is not None
        assert switched.id == s1.id
        assert switched.title == "Sprint Planning"

        # Delete s2
        deleted = await sm.delete_session(s2.id)
        assert deleted is True
        sessions_after = await sm.list_sessions()
        assert len(sessions_after) == 1
    finally:
        await test_db.close()


@pytest.mark.asyncio
async def test_user_settings_and_modes(tmp_path):
    test_db = await create_test_db(tmp_path)
    try:
        settings = UserSettings()
        await settings.load_from_db(test_db)

        # Test mode updating
        ok, msg = await settings.update_setting(test_db, "execution_mode", "offline")
        assert ok is True
        assert settings.execution_mode == "offline"

        ok, msg = await settings.update_setting(test_db, "execution_mode", "online")
        assert ok is True
        assert settings.execution_mode == "online"

        ok, msg = await settings.update_setting(test_db, "execution_mode", "hybrid")
        assert ok is True
        assert settings.execution_mode == "hybrid"

        # Invalid mode
        ok, msg = await settings.update_setting(test_db, "execution_mode", "invalid_mode")
        assert ok is False

        # Test voice toggle
        ok, msg = await settings.update_setting(test_db, "voice_enabled", "true")
        assert ok is True
        assert settings.voice_enabled is True

        ok, msg = await settings.update_setting(test_db, "voice_enabled", "off")
        assert ok is True
        assert settings.voice_enabled is False
    finally:
        await test_db.close()


@pytest.mark.asyncio
async def test_guardrails_check():
    settings = UserSettings(guardrails_enabled=True)

    # Safe command
    safe, reason = settings.check_guardrails("python main.py")
    assert safe is True
    assert reason is None

    # Destructive blocked command
    safe, reason = settings.check_guardrails("rm -rf /")
    assert safe is False
    assert "Security Guardrail" in reason

    # Sensitive path
    safe, reason = settings.check_guardrails("cat /etc/shadow")
    assert safe is False
    assert "/etc" in reason

    # Disabled guardrails
    settings.guardrails_enabled = False
    safe, reason = settings.check_guardrails("cat /etc/shadow")
    assert safe is True


@pytest.mark.asyncio
async def test_cybernetic_cli_commands(tmp_path):
    test_db = await create_test_db(tmp_path)
    try:
        sm = SessionManager(test_db)
        await sm.initialize("Command Test")
        settings = UserSettings()
        await settings.load_from_db(test_db)
        cli = CyberneticCLI(sm, settings)

        # Non-command returns False
        res = await cli.handle_command("Hello assistant")
        assert res is False

        # Valid slash commands return True or specific action
        res = await cli.handle_command("/mode offline")
        assert res is True
        assert settings.execution_mode == "offline"

        res = await cli.handle_command("/voice on")
        assert res is True
        assert settings.voice_enabled is True

        res = await cli.handle_command("/tokens")
        assert res is True

        res = await cli.handle_command("/exit")
        assert res == "exit"
    finally:
        await test_db.close()
