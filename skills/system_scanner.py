"""
skills/system_scanner.py – Cross-Platform System Hardware & Environment Scanner
=================================================================================
Scans hardware resources, audio endpoints, screen brightness, browsers, and
running applications across Windows, macOS, and Linux before executing control actions.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import psutil
from skills.base import Skill

if TYPE_CHECKING:
    from intelligence.task import Task


class SystemScannerSkill(Skill):
    name = "SystemScannerSkill"
    description = "Scans PC status, CPU, RAM, battery, audio sinks/sources, volume, brightness, browsers, and running apps."
    version = "1.0.0"
    enabled = True

    def _scan_os_and_hardware(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "os": platform.system(),
            "release": platform.release(),
            "arch": platform.machine(),
            "hostname": platform.node(),
        }
        try:
            vm = psutil.virtual_memory()
            info["ram_total_gb"] = round(vm.total / (1024 ** 3), 1)
            info["ram_used_gb"] = round(vm.used / (1024 ** 3), 1)
            info["ram_percent"] = vm.percent
            info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            info["cpu_cores"] = psutil.cpu_count(logical=True)

            battery = psutil.sensors_battery()
            if battery:
                info["battery_percent"] = round(battery.percent)
                info["power_plugged"] = battery.power_plugged
            else:
                info["battery_percent"] = None
                info["power_plugged"] = None
        except Exception:
            pass
        return info

    def _scan_audio_state(self) -> Dict[str, Any]:
        sys_name = platform.system()
        audio: Dict[str, Any] = {
            "default_sink": None,
            "default_source": None,
            "sinks": [],
            "sources": [],
            "volume": None,
            "muted": None,
        }

        if sys_name == "Linux":
            if shutil.which("pactl"):
                try:
                    res_sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=2)
                    if res_sink.returncode == 0:
                        audio["default_sink"] = res_sink.stdout.strip()

                    res_source = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True, timeout=2)
                    if res_source.returncode == 0:
                        audio["default_source"] = res_source.stdout.strip()

                    res_sinks = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=2)
                    if res_sinks.returncode == 0:
                        audio["sinks"] = [line.split()[1] for line in res_sinks.stdout.strip().splitlines() if len(line.split()) >= 2]

                    res_sources = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True, timeout=2)
                    if res_sources.returncode == 0:
                        audio["sources"] = [line.split()[1] for line in res_sources.stdout.strip().splitlines() if len(line.split()) >= 2]

                    vol_out = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=2)
                    if vol_out.returncode == 0 and "/" in vol_out.stdout:
                        m = re.search(r"(\d+)%", vol_out.stdout)
                        if m:
                            audio["volume"] = int(m.group(1))

                    mute_out = subprocess.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=2)
                    if mute_out.returncode == 0:
                        audio["muted"] = "yes" in mute_out.stdout.lower()
                except Exception:
                    pass

        elif sys_name == "Windows":
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL, CoCreateInstance, GUID
                from pycaw.pycaw import IMMDeviceEnumerator, IAudioEndpointVolume, EDataFlow, ERole
                CLSID_MM = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
                enumerator = CoCreateInstance(CLSID_MM, IMMDeviceEnumerator, CLSCTX_ALL)
                endpoint = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
                vol_int = cast(endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
                audio["volume"] = round(vol_int.GetMasterVolumeLevelScalar() * 100)
                audio["muted"] = bool(vol_int.GetMute())
                audio["default_sink"] = "Windows Default Audio Endpoint"
            except Exception:
                pass

        elif sys_name == "Darwin":
            try:
                out = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"], capture_output=True, text=True, timeout=2)
                if out.returncode == 0 and out.stdout.strip().isdigit():
                    audio["volume"] = int(out.stdout.strip())
                mute_out = subprocess.run(["osascript", "-e", "output muted of (get volume settings)"], capture_output=True, text=True, timeout=2)
                if mute_out.returncode == 0:
                    audio["muted"] = "true" in mute_out.stdout.strip().lower()
            except Exception:
                pass

        return audio

    def _scan_brightness(self) -> Optional[int]:
        sys_name = platform.system()
        if sys_name == "Linux":
            backlight_dir = "/sys/class/backlight"
            if os.path.isdir(backlight_dir):
                devices = os.listdir(backlight_dir)
                if devices:
                    try:
                        dev = os.path.join(backlight_dir, devices[0])
                        with open(os.path.join(dev, "actual_brightness")) as f:
                            cur = int(f.read().strip())
                        with open(os.path.join(dev, "max_brightness")) as f:
                            max_val = int(f.read().strip())
                        return round((cur / max_val) * 100)
                    except Exception:
                        pass
            if shutil.which("brightnessctl"):
                try:
                    res = subprocess.run(["brightnessctl", "g"], capture_output=True, text=True, timeout=2)
                    max_res = subprocess.run(["brightnessctl", "m"], capture_output=True, text=True, timeout=2)
                    if res.returncode == 0 and max_res.returncode == 0:
                        return round((int(res.stdout.strip()) / int(max_res.stdout.strip())) * 100)
                except Exception:
                    pass
            if shutil.which("xrandr"):
                try:
                    res = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=2)
                    if res.returncode == 0 and "Brightness:" in res.stdout:
                        m = re.search(r"Brightness:\s+([0-9.]+)", res.stdout)
                        if m:
                            return round(float(m.group(1)) * 100)
                except Exception:
                    pass

        elif sys_name == "Windows":
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"],
                    capture_output=True, text=True, timeout=3
                )
                if res.stdout.strip().isdigit():
                    return int(res.stdout.strip())
            except Exception:
                pass

        elif sys_name == "Darwin":
            try:
                res = subprocess.run(["osascript", "-e", "tell application \"System Events\" to get the brightness"], capture_output=True, text=True, timeout=2)
                return round(float(res.stdout.strip()) * 100)
            except Exception:
                pass

        return None

    def _scan_browsers(self) -> List[str]:
        found = []
        candidates = [
            ("Google Chrome", ["google-chrome", "google-chrome-stable", "chrome", "chrome.exe"]),
            ("Mozilla Firefox", ["firefox", "firefox.exe"]),
            ("Brave Browser", ["brave-browser", "brave", "brave.exe"]),
            ("Microsoft Edge", ["microsoft-edge", "msedge", "msedge.exe"]),
        ]
        for name, bins in candidates:
            if any(shutil.which(b) for b in bins):
                found.append(name)
        return found

    def _scan_running_apps(self) -> List[str]:
        apps = set()
        common_procs = {
            "chrome": "Google Chrome",
            "firefox": "Firefox",
            "brave": "Brave Browser",
            "code": "VS Code",
            "spotify": "Spotify",
            "discord": "Discord",
            "slack": "Slack",
            "telegram": "Telegram",
            "terminal": "Terminal",
            "bash": "Bash Shell",
            "zsh": "Zsh Shell",
            "python": "Python Engine",
        }
        try:
            for p in psutil.process_iter(["name"]):
                pname = (p.info.get("name") or "").lower()
                for k, v in common_procs.items():
                    if k in pname:
                        apps.add(v)
        except Exception:
            pass
        return sorted(list(apps))[:8]

    async def execute(self, task: Task) -> str:
        hw = self._scan_os_and_hardware()
        audio = self._scan_audio_state()
        brightness = self._scan_brightness()
        browsers = self._scan_browsers()
        apps = self._scan_running_apps()

        b_str = f"{brightness}%" if brightness is not None else "N/A"
        v_str = f"{audio['volume']}%" if audio['volume'] is not None else "Unknown"
        if audio["muted"]:
            v_str += " (Muted)"

        sink_str = audio['default_sink'].split('.')[-1] if audio['default_sink'] else 'Default'
        battery_str = f"{hw.get('battery_percent')}% ({'Plugged In' if hw.get('power_plugged') else 'Discharging'})" if hw.get('battery_percent') is not None else "AC / Desktop"

        report = [
            f"🖥️ System Scan ({hw['os']} {hw['arch']})",
            f"• CPU: {hw.get('cpu_percent')}% load ({hw.get('cpu_cores')} cores) | RAM: {hw.get('ram_used_gb')}/{hw.get('ram_total_gb')} GB ({hw.get('ram_percent')}%) | Battery: {battery_str}",
            f"• Audio: Volume {v_str} | Active Output: {sink_str}",
            f"• Audio Devices: {len(audio.get('sinks', []))} outputs | {len(audio.get('sources', []))} mics",
            f"• Screen Brightness: {b_str}",
            f"• Installed Browsers: {', '.join(browsers) if browsers else 'System Default'}",
            f"• Running Applications: {', '.join(apps) if apps else 'None detected'}",
        ]

        task.result = {
            "hardware": hw,
            "audio": audio,
            "brightness": brightness,
            "browsers": browsers,
            "apps": apps,
        }
        return chr(10).join(report)
