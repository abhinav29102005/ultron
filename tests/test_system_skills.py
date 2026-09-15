"""
tests/test_system_skills.py – Tkinter GUI Skill Tester
======================================================
Provides a temporary UI to manually test System and Volume skills.
Run with:
    uv run python tests/test_system_skills.py
"""

from __future__ import annotations

import asyncio
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
from pathlib import Path

# ── Make sure the repo root is on sys.path ──────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from intelligence.task import Task, TaskStatus
from skills.System import BrightnessSkill, MicSkill
from skills.system_skills import VolumeSkill


# ── Helpers ──────────────────────────────────────────────────

def make_task(intent: str, **parameters) -> Task:
    """Build a minimal Task with the given intent and parameters."""
    return Task(
        task_id="test-001",
        skill_name="test",
        intent=intent,
        parameters=parameters,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )


def run_skill_sync(skill, **parameters):
    """Run an async skill synchronously from Tkinter."""
    task = make_task(skill.name, **parameters)
    try:
        # We can use asyncio.run because these skills don't depend on a running event loop
        result = asyncio.run(skill.execute(task))
        messagebox.showinfo("Success", str(result))
    except Exception as e:
        messagebox.showerror("Error", f"{type(e).__name__}: {e}")


class SkillTesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ULTRON Skill Tester")
        self.geometry("400x550")
        self.resizable(False, False)

        # Initialize skills
        self.brightness_skill = BrightnessSkill()
        self.volume_skill = VolumeSkill()
        self.mic_skill = MicSkill()

        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ── Brightness ──
        lf_bright = ttk.LabelFrame(main_frame, text="Brightness", padding="5")
        lf_bright.pack(fill=tk.X, pady=5)
        
        ttk.Button(lf_bright, text="Up (+10%)", command=lambda: run_skill_sync(self.brightness_skill, action="up")).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(lf_bright, text="Down (-10%)", command=lambda: run_skill_sync(self.brightness_skill, action="down")).grid(row=0, column=1, padx=2, pady=2)
        
        self.bright_level = tk.StringVar(value="50")
        ttk.Entry(lf_bright, textvariable=self.bright_level, width=5).grid(row=0, column=2, padx=5)
        ttk.Button(lf_bright, text="Set", command=lambda: self._set_brightness()).grid(row=0, column=3, padx=2, pady=2)

        # ── Volume ──
        lf_vol = ttk.LabelFrame(main_frame, text="Volume", padding="5")
        lf_vol.pack(fill=tk.X, pady=5)
        
        ttk.Button(lf_vol, text="Up (+10%)", command=lambda: run_skill_sync(self.volume_skill, action="up")).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(lf_vol, text="Down (-10%)", command=lambda: run_skill_sync(self.volume_skill, action="down")).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(lf_vol, text="Mute", command=lambda: run_skill_sync(self.volume_skill, action="mute")).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(lf_vol, text="Unmute", command=lambda: run_skill_sync(self.volume_skill, action="unmute")).grid(row=1, column=1, padx=2, pady=2)
        
        self.vol_level = tk.StringVar(value="50")
        ttk.Entry(lf_vol, textvariable=self.vol_level, width=5).grid(row=0, column=2, padx=5)
        ttk.Button(lf_vol, text="Set", command=lambda: self._set_volume()).grid(row=0, column=3, padx=2, pady=2)

        # ── Microphone ──
        lf_mic = ttk.LabelFrame(main_frame, text="Microphone", padding="5")
        lf_mic.pack(fill=tk.X, pady=5)
        
        ttk.Button(lf_mic, text="Mute", command=lambda: run_skill_sync(self.mic_skill, action="mute")).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(lf_mic, text="Unmute", command=lambda: run_skill_sync(self.mic_skill, action="unmute")).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(lf_mic, text="Toggle", command=lambda: run_skill_sync(self.mic_skill, action="toggle")).grid(row=0, column=2, padx=2, pady=2)




    def _set_brightness(self):
        try:
            lvl = int(self.bright_level.get())
            run_skill_sync(self.brightness_skill, action="set", level=lvl)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid integer (0-100).")

    def _set_volume(self):
        try:
            lvl = int(self.vol_level.get())
            run_skill_sync(self.volume_skill, action="set", level=lvl)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid integer (0-100).")


if __name__ == "__main__":
    app = SkillTesterApp()
    app.mainloop()
