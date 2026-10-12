#!/usr/bin/env python3
"""
scripts/record_gui.py – Cross-Platform ULTRON GUI Video Recorder
================================================================
Records the live PyQt6 ULTRON desktop GUI (Orb, Waveform Pill, and Chat Card)
directly into MP4 and WebM video files without any external screen capture tools
or OS-level permission headaches.

Works 100% reliably on:
- Linux (Wayland & X11)
- Windows (10 & 11)
- macOS (Intel & Apple Silicon)

Usage:
    # Run the GUI normally and record interactive session until closed:
    python scripts/record_gui.py

    # Run the automated showcase demonstrating all Ultron features:
    python scripts/record_gui.py --demo

    # Specify custom output video path:
    python scripts/record_gui.py --output my_demo.mp4
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

# Set environment variable to ensure screen capture hider is disabled
os.environ["ULTRON_RECORDING"] = "1"
os.environ["ULTRON_ALLOW_CAPTURE"] = "1"

def main():
    parser = argparse.ArgumentParser(description="ULTRON Cross-Platform GUI Video Recorder")
    parser.add_argument("--demo", action="store_true", help="Run automated feature demonstration")
    parser.add_argument("--output", default="ultron_gui_demo.mp4", help="Output video path (.mp4 / .webm)")
    parser.add_argument("--fps", type=int, default=25, help="Frames per second (default: 25)")
    args, unknown = parser.parse_known_args()

    # Pass flags through to main_gui
    sys.argv = [sys.argv[0]]
    if args.demo:
        sys.argv.append("--demo")
    sys.argv.extend(["--record", "--output", args.output, "--fps", str(args.fps)])

    # Trampoline to main_gui.py
    import main_gui
    main_gui.main()

if __name__ == "__main__":
    main()
