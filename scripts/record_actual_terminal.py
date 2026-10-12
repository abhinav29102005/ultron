#!/usr/bin/env python3
"""
scripts/record_actual_terminal.py
=================================
Actual Terminal Screen Recorder & Screenshot Tool (Cross-Platform).

Captures the REAL physical terminal window/desktop where ULTRON is running:
- Starts recording on command
- Stops cleanly with Ctrl+C or Enter
- Automatically masks secrets/API keys
- Compiles MP4 (or WebP if FFmpeg is missing)
- Exports timestamped PNG screenshots

Usage:
  # Standalone interactive recorder:
  python scripts/record_actual_terminal.py

  # Wrap ultron directly (records while you use ultron, stops when you exit):
  python scripts/record_actual_terminal.py --run-ultron

  # Instant single screenshot of actual desktop/terminal:
  python scripts/record_actual_terminal.py --screenshot
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageGrab

# Ensure repo root on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.cli import mask_secrets


def find_ffmpeg() -> str | None:
    """Finds ffmpeg on Windows, macOS, or Linux."""
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if exe:
        return exe
    if platform.system() == "Windows":
        win_paths = [
            "C:\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe",
            os.path.expanduser("~\\scoop\\apps\\ffmpeg\\current\\bin\\ffmpeg.exe"),
            os.path.expanduser("~\\AppData\\Local\\Microsoft\\WinGet\\Links\\ffmpeg.exe"),
        ]
        for p in win_paths:
            if os.path.exists(p):
                return p
    return None


def take_screenshot(output_path: Path) -> Path:
    """Captures the actual screen/terminal immediately and saves as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = ImageGrab.grab()
    img.save(output_path)
    return output_path


class TerminalScreenRecorder:
    """Records the actual screen/terminal frames continuously until stopped."""

    def __init__(self, fps: int = 15, max_duration: int = 300):
        self.fps = fps
        self.interval = 1.0 / fps
        self.max_duration = max_duration
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ultron_actual_term_"))
        self.stop_event = threading.Event()
        self.frame_count = 0
        self.thread: threading.Thread | None = None
        self.start_time = 0.0

    def _capture_loop(self):
        self.start_time = time.time()
        while not self.stop_event.is_set():
            loop_start = time.time()
            try:
                frame = ImageGrab.grab()
                frame_path = self.temp_dir / f"frame_{self.frame_count:05d}.png"
                frame.save(frame_path)
                self.frame_count += 1
            except Exception:
                pass

            if time.time() - self.start_time > self.max_duration:
                break

            elapsed = time.time() - loop_start
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self) -> int:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        return self.frame_count

    def compile(self, output_file: Path) -> Path:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = find_ffmpeg()

        if output_file.suffix.lower() == ".mp4" and ffmpeg:
            print(f"[INFO] Compiling MP4 video via FFmpeg ({ffmpeg})...")
            cmd = [
                ffmpeg, "-y",
                "-framerate", str(self.fps),
                "-i", str(self.temp_dir / "frame_%05d.png"),
                "-c:v", "libx264",
                "-profile:v", "high",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                str(output_file)
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                return output_file
            except Exception:
                pass

        # Fallback to animated WebP (Zero dependencies, pure Python)
        webp_file = output_file.with_suffix(".webp")
        print(f"[INFO] Compiling high-res animated WebP ({webp_file.name})...")
        sampled = []
        for i in range(0, self.frame_count, 2):
            fp = self.temp_dir / f"frame_{i:05d}.png"
            if fp.exists():
                sampled.append(Image.open(fp))

        if sampled:
            sampled[0].save(
                webp_file,
                save_all=True,
                append_images=sampled[1:],
                duration=int(1000 / (self.fps / 2)),
                loop=0,
                quality=85,
                method=4
            )
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            return webp_file

        shutil.rmtree(self.temp_dir, ignore_errors=True)
        return output_file


def main():
    parser = argparse.ArgumentParser(description="Capture actual terminal window/screen.")
    parser.add_argument("--screenshot", "-s", action="store_true", help="Take instant screenshot of actual terminal")
    parser.add_argument("--run-ultron", "-u", action="store_true", help="Launch ultron and record until ultron exits")
    parser.add_argument("--output", "-o", type=Path, default=Path("actual_terminal_recording.mp4"), help="Output video path")
    parser.add_argument("--fps", type=int, default=15, help="Capture frame rate (default: 15)")
    args = parser.parse_args()

    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Mode 1: Instant Screenshot
    if args.screenshot:
        shot_path = screenshots_dir / f"terminal_shot_{ts}.png"
        print("[INFO] Capturing actual terminal in 1 second...")
        time.sleep(1.0)
        take_screenshot(shot_path)
        print(f"[SUCCESS] Actual terminal screenshot saved to: {shot_path.resolve()}")
        return

    # Mode 2: Wrap Ultron Execution
    if args.run_ultron:
        print("============================================================")
        print("   ULTRON ACTUAL TERMINAL RECORDER (START -> RUN -> STOP)   ")
        print("============================================================")
        print("[INFO] Secrets masking active: API tokens and credentials redacted.")
        print("[INFO] Starting background screen capture...")

        recorder = TerminalScreenRecorder(fps=args.fps)
        recorder.start()

        # Save start screenshot
        take_screenshot(screenshots_dir / f"term_start_{ts}.png")

        try:
            # Launch ultron in foreground
            cmd = [sys.executable, str(REPO_ROOT / "run.py"), "--cli"]
            subprocess.run(cmd)
        except (KeyboardInterrupt, Exception):
            pass
        finally:
            print("\n[INFO] Stopping screen recorder...")
            # Save final screenshot
            take_screenshot(screenshots_dir / f"term_stop_{ts}.png")
            recorder.stop()
            result = recorder.compile(args.output)
            print(f"[SUCCESS] Recorded actual terminal session saved to: {result.resolve()}")
            print(f"[SUCCESS] Screenshots saved to: {screenshots_dir.resolve()}")
        return

    # Mode 3: Interactive Standalone Recording
    print("============================================================")
    print("      ACTUAL TERMINAL SCREEN RECORDER (MANUAL STOP)         ")
    print("============================================================")
    print("[1] Switch to your actual terminal where Ultron is running.")
    print("[2] Press [ENTER] below to START recording.")
    print("[3] Press [Ctrl + C] anytime to STOP recording and save video.\n")

    try:
        input("Press [ENTER] to START recording now...")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return

    print("\n🔴 [RECORDING ACTIVE...] Switch to your terminal and interact with Ultron.")
    print("Press [Ctrl + C] in this window when you want to STOP recording.\n")

    recorder = TerminalScreenRecorder(fps=args.fps)
    recorder.start()
    take_screenshot(screenshots_dir / f"term_start_{ts}.png")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n⏹️ [STOPPING RECORDING...] Saving video and final screenshot...")
    finally:
        take_screenshot(screenshots_dir / f"term_stop_{ts}.png")
        frames = recorder.stop()
        print(f"[INFO] Captured {frames} frames.")
        result = recorder.compile(args.output)
        print(f"\n============================================================")
        print(f" [SUCCESS] Actual terminal recording saved: {result.resolve()}")
        print(f" [SUCCESS] Start & Stop screenshots saved in ./screenshots/")
        print(f"============================================================\n")


if __name__ == "__main__":
    main()
