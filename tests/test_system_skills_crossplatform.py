import pytest
import platform
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

from intelligence.task import Task, TaskStatus
from skills.System import BrightnessSkill, MicSkill
from skills.system_skills import VolumeSkill, ApplicationSkill
from skills.system_scanner import SystemScannerSkill
from skills.audio_device_skill import AudioDeviceSkill


def make_task(intent: str, parameters: dict) -> Task:
    return Task(
        task_id=str(uuid.uuid4()),
        skill_name="",
        intent=intent,
        parameters=parameters,
        status=TaskStatus.READY_FOR_EXECUTION,
        result=None,
        error=None,
        created_at=datetime.utcnow(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


@pytest.mark.asyncio
async def test_brightness_skill_linux():
    skill = BrightnessSkill()
    with patch("platform.system", return_value="Linux"), \
         patch.object(skill, "_get_brightness_linux", return_value=50), \
         patch.object(skill, "_set_brightness_linux") as mock_set:
        
        res = await skill.execute(make_task("brightness_control", {"action": "up"}))
        assert "Brightness increased to 60%." in res
        mock_set.assert_called_with(60)

        res_down = await skill.execute(make_task("brightness_control", {"action": "down"}))
        assert "Brightness decreased to 40%." in res_down
        mock_set.assert_called_with(40)

        res_set = await skill.execute(make_task("brightness_control", {"action": "set", "level": 85}))
        assert "Brightness set to 85%." in res_set
        mock_set.assert_called_with(85)


@pytest.mark.asyncio
async def test_mic_skill_linux():
    skill = MicSkill()
    with patch("platform.system", return_value="Linux"), \
         patch.object(skill, "_execute_linux", return_value="Microphone muted.") as mock_exec:
        
        res = await skill.execute(make_task("mic_control", {"action": "mute"}))
        assert res == "Microphone muted."
        mock_exec.assert_called_with("mute")


@pytest.mark.asyncio
async def test_volume_skill_linux():
    skill = VolumeSkill()
    with patch("platform.system", return_value="Linux"), \
         patch.object(skill, "_execute_linux", return_value="Volume increased by 10%.") as mock_vol:
        
        res = await skill.execute(make_task("system_control", {"action": "up"}))
        assert "Volume increased by 10%." in res
        mock_vol.assert_called_with("up", None)


@pytest.mark.asyncio
async def test_application_skill_linux():
    skill = ApplicationSkill()
    with patch("platform.system", return_value="Linux"), \
         patch.object(skill, "_execute_linux", return_value="Google Chrome opened successfully.") as mock_app:
        
        res = await skill.execute(make_task("open_application", {"application": "chrome"}))
        assert "opened successfully" in res
        mock_app.assert_called_with("open_application", "chrome", "chrome")


@pytest.mark.asyncio
async def test_system_scanner_skill():
    skill = SystemScannerSkill()
    task = make_task("system_scan", {})
    report = await skill.execute(task)
    assert "System Scan" in report
    assert "CPU:" in report
    assert "Audio:" in report
    assert task.result is not None
    assert "hardware" in task.result
    assert "audio" in task.result


@pytest.mark.asyncio
async def test_audio_device_skill_list():
    skill = AudioDeviceSkill()
    with patch("platform.system", return_value="Linux"), \
         patch.object(skill, "_get_linux_devices", return_value={
             "outputs": [{"id": "1", "name": "sink1", "description": "Built-in Speakers"}],
             "inputs": [{"id": "2", "name": "source1", "description": "Built-in Mic"}],
         }):
        res = await skill.execute(make_task("audio_device_control", {"action": "list"}))
        assert "Audio Devices Available" in res
        assert "Built-in Speakers" in res
        assert "Built-in Mic" in res


@pytest.mark.asyncio
async def test_audio_device_skill_switch():
    skill = AudioDeviceSkill()
    with patch("platform.system", return_value="Linux"), \
         patch.object(skill, "_switch_linux_device", return_value="Switched default audio output to: Built-in Speakers.") as mock_sw:
        res = await skill.execute(make_task("audio_device_control", {"action": "switch", "device": "Built-in Speakers"}))
        assert "Switched default audio output" in res
        mock_sw.assert_called_with("Built-in Speakers", is_input=False)
