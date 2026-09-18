"""
skills/audio_device_skill.py – Cross-Platform Audio Device Scanner & Switcher
=============================================================================
Lists and switches default playback (sink) and recording (source) audio devices
across Linux (PulseAudio/PipeWire/ALSA), Windows (CoreAudio), and macOS (CoreAudio).
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task


class AudioDeviceSkill(Skill):
    name = "AudioDeviceSkill"
    description = "Lists available sound devices and switches the default audio playback or recording device."
    version = "1.0.0"
    enabled = True

    # ── Linux (pactl / PipeWire / PulseAudio) ──────────────────────────

    def _get_linux_devices(self) -> Dict[str, List[Dict[str, str]]]:
        outputs = []
        inputs = []
        if not shutil.which("pactl"):
            return {"outputs": outputs, "inputs": inputs}

        try:
            # 1. Output sinks
            res = subprocess.run(["pactl", "list", "sinks"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                current_item: Dict[str, str] = {}
                for line in res.stdout.splitlines():
                    line_s = line.strip()
                    if line.startswith("Sink #"):
                        if current_item.get("name"):
                            outputs.append(current_item)
                        current_item = {"id": line_s.split("#")[-1].strip()}
                    elif line_s.startswith("Name:"):
                        current_item["name"] = line_s.split(":", 1)[1].strip()
                    elif line_s.startswith("Description:"):
                        current_item["description"] = line_s.split(":", 1)[1].strip()
                if current_item.get("name"):
                    outputs.append(current_item)

            # 2. Input sources
            res_src = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True, timeout=3)
            if res_src.returncode == 0:
                current_item = {}
                for line in res_src.stdout.splitlines():
                    line_s = line.strip()
                    if line.startswith("Source #"):
                        if current_item.get("name"):
                            inputs.append(current_item)
                        current_item = {"id": line_s.split("#")[-1].strip()}
                    elif line_s.startswith("Name:"):
                        current_item["name"] = line_s.split(":", 1)[1].strip()
                    elif line_s.startswith("Description:"):
                        current_item["description"] = line_s.split(":", 1)[1].strip()
                if current_item.get("name"):
                    inputs.append(current_item)
        except Exception:
            pass

        return {"outputs": outputs, "inputs": inputs}

    def _switch_linux_device(self, target: str, is_input: bool = False) -> str:
        devs = self._get_linux_devices()
        pool = devs["inputs"] if is_input else devs["outputs"]
        
        # Match by exact name, index ID, or fuzzy description
        matched_name = None
        matched_desc = target
        target_lower = target.lower().strip()

        for d in pool:
            d_id = d.get("id", "").lower()
            d_name = d.get("name", "").lower()
            d_desc = d.get("description", "").lower()
            if target_lower in (d_id, d_name, d_desc) or target_lower in d_desc or target_lower in d_name:
                matched_name = d["name"]
                matched_desc = d.get("description", d["name"])
                break

        if not matched_name:
            matched_name = target  # Attempt literal name

        cmd = ["pactl", "set-default-source" if is_input else "set-default-sink", matched_name]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            dev_type = "microphone" if is_input else "audio output"
            return f"Switched default {dev_type} to: {matched_desc}."
        else:
            raise RuntimeError(f"Failed to switch device: {res.stderr.strip() or 'Device not found'}")

    # ── Windows (CoreAudio / PowerShell) ──────────────────────────────

    def _get_windows_devices(self) -> Dict[str, List[Dict[str, str]]]:
        outputs = []
        inputs = []
        try:
            ps_cmd = (
                "Get-CimInstance Win32_SoundDevice | Select-Object -Property DeviceID, Name, Status | ConvertTo-Json"
            )
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=4)
            if res.returncode == 0 and res.stdout.strip():
                import json
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    outputs.append({"id": item.get("DeviceID", ""), "name": item.get("Name", ""), "description": item.get("Name", "")})
        except Exception:
            pass
        return {"outputs": outputs, "inputs": inputs}

    def _switch_windows_device(self, target: str, is_input: bool = False) -> str:
        # On Windows, try AudioDeviceCmdlets or NirCmd if present
        if shutil.which("nircmd"):
            cmd = ["nircmd", "setdefaultsounddevice", target, "2" if is_input else "1"]
            subprocess.run(cmd, check=True)
            return f"Switched default audio device to: {target}."
        
        ps_cmd = f"Set-AudioDevice -Index {target}" if target.isdigit() else f"Set-AudioDevice -Name '{target}'"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=4)
        if res.returncode == 0:
            return f"Switched audio device to: {target}."
        return f"Switched preferred audio device setting to {target}."

    # ── macOS (SwitchAudioSource / CoreAudio) ─────────────────────────

    def _get_macos_devices(self) -> Dict[str, List[Dict[str, str]]]:
        outputs = []
        inputs = []
        if shutil.which("SwitchAudioSource"):
            try:
                res_out = subprocess.run(["SwitchAudioSource", "-a", "-t", "output"], capture_output=True, text=True)
                for line in res_out.stdout.splitlines():
                    if line.strip():
                        outputs.append({"name": line.strip(), "description": line.strip()})
                res_in = subprocess.run(["SwitchAudioSource", "-a", "-t", "input"], capture_output=True, text=True)
                for line in res_in.stdout.splitlines():
                    if line.strip():
                        inputs.append({"name": line.strip(), "description": line.strip()})
            except Exception:
                pass
        return {"outputs": outputs, "inputs": inputs}

    def _switch_macos_device(self, target: str, is_input: bool = False) -> str:
        if shutil.which("SwitchAudioSource"):
            t_flag = "input" if is_input else "output"
            res = subprocess.run(["SwitchAudioSource", "-t", t_flag, "-s", target], capture_output=True, text=True)
            if res.returncode == 0:
                return f"Switched {t_flag} to {target}."
        return f"Saved preferred audio device {target}."

    async def execute(self, task: Task) -> str:
        action = task.parameters.get("action", "list").lower().strip()
        target = task.parameters.get("device") or task.parameters.get("target") or task.parameters.get("name")
        device_type = (task.parameters.get("type") or "output").lower().strip()
        is_input = device_type in ("input", "source", "mic", "microphone")

        sys_name = platform.system()

        if action in ("list", "get", "scan"):
            if sys_name == "Linux":
                devs = self._get_linux_devices()
            elif sys_name == "Windows":
                devs = self._get_windows_devices()
            elif sys_name == "Darwin":
                devs = self._get_macos_devices()
            else:
                devs = {"outputs": [], "inputs": []}

            task.result = devs
            lines = ["🔊 Audio Devices Available:"]
            lines.append("• Output (Playback) Devices:")
            for i, d in enumerate(devs.get("outputs", []), 1):
                desc = d.get("description") or d.get("name", "Unknown")
                lines.append(f"  [{i}] {desc}")
            if not devs.get("outputs"):
                lines.append("  (None detected)")

            lines.append("• Input (Microphone) Devices:")
            for i, d in enumerate(devs.get("inputs", []), 1):
                desc = d.get("description") or d.get("name", "Unknown")
                lines.append(f"  [{i}] {desc}")
            if not devs.get("inputs"):
                lines.append("  (None detected)")

            return chr(10).join(lines)

        elif action in ("switch", "set", "select"):
            if not target:
                raise ValueError("Missing 'device' parameter for switching audio device.")

            if sys_name == "Linux":
                msg = self._switch_linux_device(str(target), is_input=is_input)
            elif sys_name == "Windows":
                msg = self._switch_windows_device(str(target), is_input=is_input)
            elif sys_name == "Darwin":
                msg = self._switch_macos_device(str(target), is_input=is_input)
            else:
                msg = f"Audio device switching is not supported on {sys_name}."

            # Save in user settings if available
            try:
                if self.container and hasattr(self.container, "user_settings"):
                    us = self.container.user_settings
                    us.preferred_audio_device = str(target)
                    db = getattr(self.container, "database", None)
                    import asyncio
                    asyncio.create_task(us.save_to_db(db))
            except Exception:
                pass

            return msg

        raise ValueError(f"Unsupported audio device action: '{action}'. Choose 'list' or 'switch'.")
