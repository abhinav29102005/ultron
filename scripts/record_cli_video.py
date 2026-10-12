#!/usr/bin/env python3
"""
scripts/record_cli_video.py
===========================
Cross-Platform High-Definition Terminal Video & Screenshot Recorder
for the ULTRON Autonomous AI Desktop Agent CLI.

Works seamlessly on Windows, macOS, and Linux:
- Cross-platform font discovery (Windows Consolas/Cascadia, macOS Menlo/Monaco, Linux Adwaita/DejaVu)
- Multiple export formats: MP4 (via ffmpeg), animated WebP & GIF (pure Python / Pillow, zero dependencies)
- High-resolution standalone PNG screenshots saved to ./screenshots/
- Native Windows Terminal / Linux / macOS styling

Usage:
    python scripts/record_cli_video.py                    # Generates MP4 (or WebP if no ffmpeg) + screenshots
    python scripts/record_cli_video.py --screenshots      # Fast screenshot generation only (PNG)
    python scripts/record_cli_video.py --format webp      # Pure Python animated WebP (no ffmpeg needed)
    python scripts/record_cli_video.py --format all       # Generates MP4, WebP, GIF, and all PNG screenshots
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Ensure repo root on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Color Palette (Ultron Cybernetic Monospace Dark)
BG_DARK = (10, 14, 23)
TERMINAL_BG = (13, 17, 26)
TITLE_BAR_BG = (20, 26, 38)
TEXT_WHITE = (235, 240, 248)
TEXT_CYAN = (0, 235, 255)
TEXT_GREEN = (50, 255, 120)
TEXT_YELLOW = (255, 205, 50)
TEXT_MAGENTA = (255, 80, 180)
TEXT_DIM = (120, 135, 155)
TEXT_BLUE = (70, 150, 255)
RED_BTN = (255, 95, 86)
YELLOW_BTN = (255, 189, 46)
GREEN_BTN = (39, 201, 63)


def find_system_font(size: int = 15, bold: bool = False):
    """Robust cross-platform font resolver for Windows, macOS, and Linux."""
    candidates = []

    # 1. Windows Fonts
    windir = os.environ.get("WINDIR", "C:\\Windows")
    localapp = os.environ.get("LOCALAPPDATA", "")
    if bold:
        candidates.extend([
            os.path.join(windir, "Fonts", "consolab.ttf"),
            os.path.join(windir, "Fonts", "CascadiaMonoBold.ttf"),
            os.path.join(windir, "Fonts", "courbd.ttf"),
            os.path.join(windir, "Fonts", "arialbd.ttf"),
            "consolab.ttf", "courbd.ttf"
        ])
    candidates.extend([
        os.path.join(windir, "Fonts", "consola.ttf"),
        os.path.join(windir, "Fonts", "CascadiaMono.ttf"),
        os.path.join(windir, "Fonts", "CascadiaCode.ttf"),
        os.path.join(windir, "Fonts", "lucon.ttf"),
        os.path.join(windir, "Fonts", "cour.ttf"),
        os.path.join(localapp, "Microsoft", "Windows", "Fonts", "CascadiaMono.ttf"),
        "consola.ttf", "CascadiaMono.ttf", "cour.ttf", "arial.ttf"
    ])

    # 2. macOS Fonts
    candidates.extend([
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/Library/Fonts/Courier New.ttf",
        "/Library/Fonts/Arial.ttf"
    ])

    # 3. Linux Fonts
    if bold:
        candidates.extend([
            "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Bold.ttf",
            "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/liberation-mono/LiberationMono-Bold.ttf",
        ])
    candidates.extend([
        "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Regular.ttf",
        "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/liberation-mono/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "AdwaitaMono-Regular.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"
    ])

    # Try loading directly
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    # Try loading by name via Pillow's internal resolution
    for name in ["consola.ttf", "CascadiaMono.ttf", "DejaVuSansMono.ttf", "cour.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue

    # Fallback scan in standard directories
    scan_dirs = [
        "/usr/share/fonts",
        os.path.join(windir, "Fonts"),
        "/System/Library/Fonts",
        os.path.expanduser("~/.local/share/fonts")
    ]
    for d in scan_dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")) and any(k in f.lower() for k in ["mono", "consola", "code"]):
                        try:
                            return ImageFont.truetype(os.path.join(root, f), size)
                        except Exception:
                            continue

    # Ultimate fallback
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def get_fonts():
    font_regular = find_system_font(15, bold=False)
    font_bold = find_system_font(15, bold=True) or font_regular
    font_small = find_system_font(12, bold=False) or font_regular
    return font_regular, font_bold, font_small


def find_ffmpeg_executable() -> str | None:
    """Finds ffmpeg across standard PATH and typical Windows install directories."""
    # 1. System PATH
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if exe:
        return exe

    # 2. Typical Windows Locations
    if platform.system() == "Windows":
        win_candidates = [
            "C:\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe",
            os.path.expanduser("~\\scoop\\apps\\ffmpeg\\current\\bin\\ffmpeg.exe"),
            os.path.expanduser("~\\AppData\\Local\\Microsoft\\WinGet\\Links\\ffmpeg.exe"),
        ]
        # Check WinGet package directories
        winget_root = os.path.expanduser("~\\AppData\\Local\\Microsoft\\WinGet\\Packages")
        if os.path.exists(winget_root):
            for root, _, files in os.walk(winget_root):
                if "ffmpeg.exe" in files:
                    win_candidates.append(os.path.join(root, "ffmpeg.exe"))

        for c in win_candidates:
            if os.path.exists(c):
                return c

    return None


def create_frame_canvas(width: int, height: int, font_small, os_style: str = "auto"):
    """Renders high-definition terminal container with OS-adapted window borders."""
    img = Image.new("RGB", (width, height), BG_DARK)
    draw = ImageDraw.Draw(img)

    if os_style == "auto":
        os_style = "windows" if platform.system() == "Windows" else "linux"

    # Top Status Bar
    draw.rectangle([0, 0, width, 40], fill=(11, 15, 24))
    draw.text((25, 12), "ULTRON AUTONOMOUS DESKTOP AGENT // CLOUD LLM HUB // DUAL INFERENCE", fill=TEXT_CYAN, font=font_small)
    draw.text((width - 320, 12), "STATUS: ONLINE [GROQ LPU + NVIDIA NIM]", fill=TEXT_GREEN, font=font_small)
    draw.line([(0, 40), (width, 40)], fill=(0, 180, 255), width=1)

    # Terminal Container
    term_x, term_y = 30, 60
    term_w, term_h = width - 60, height - 85
    draw.rectangle([term_x, term_y, term_x + term_w, term_y + term_h], fill=TERMINAL_BG, outline=(30, 45, 70), width=2)

    # Title Bar
    draw.rectangle([term_x, term_y, term_x + term_w, term_y + 32], fill=TITLE_BAR_BG)

    if os_style == "windows":
        # Windows Terminal Style Title Bar
        draw.text((term_x + 15, term_y + 8), "Windows PowerShell - ultron v0.2.0 (Autonomous Agent)", fill=TEXT_WHITE, font=font_small)
        draw.text((term_x + term_w - 230, term_y + 8), "Dual LLM · Port 8000", fill=TEXT_CYAN, font=font_small)
        # Windows Controls: Minimize, Maximize, Close
        cx = term_x + term_w - 50
        draw.text((cx, term_y + 6), "─   □   ✕", fill=TEXT_DIM, font=font_small)
    else:
        # Mac / Linux Style Window Buttons
        draw.ellipse([term_x + 15, term_y + 10, term_x + 27, term_y + 22], fill=RED_BTN)
        draw.ellipse([term_x + 35, term_y + 10, term_x + 47, term_y + 22], fill=YELLOW_BTN)
        draw.ellipse([term_x + 55, term_y + 10, term_x + 67, term_y + 22], fill=GREEN_BTN)
        draw.text((term_x + 85, term_y + 8), "ultron-cli — bash / zsh — v0.2.0 (Dual LLM Engine)", fill=TEXT_DIM, font=font_small)
        draw.text((term_x + term_w - 240, term_y + 8), "SESSION: main_interactive", fill=TEXT_CYAN, font=font_small)

    draw.line([(term_x, term_y + 32), (term_x + term_w, term_y + 32)], fill=(30, 45, 70), width=1)

    return img, (term_x + 20, term_y + 45, term_w - 40, term_h - 60)


def get_normal_cli_storyboard():
    """Generates the true, realistic conversational sequence of the Main Ultron CLI."""
    return [
        # Scene 1: Ultron Banner & Initialization
        ("text", "$ ultron", TEXT_CYAN),
        ("text", "╭──────────────────────────────────────────────────────────────────────────╮", TEXT_BLUE),
        ("text", "│  ██╗   ██╗██╗  ████████╗██████╗  ██████╗ ███╗   ██╗                      │", TEXT_CYAN),
        ("text", "│  ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔═══██╗████╗  ██║                      │", TEXT_CYAN),
        ("text", "│  ██║   ██║██║     ██║   ██████╔╝██║   ██║██╔██╗ ██║                      │", TEXT_CYAN),
        ("text", "│  ██║   ██║██║     ██║   ██╔══██╗██║   ██║██║╚██╗██║                      │", TEXT_CYAN),
        ("text", "│  ╚██████╔╝███████╗██║   ██║  ██║╚██████╔╝██║ ╚████║                      │", TEXT_CYAN),
        ("text", "│  AUTONOMOUS AI DESKTOP AGENT & CLOUD LLM HUB · v0.2.0                    │", TEXT_WHITE),
        ("text", "│  STATUS: ONLINE │ ENGINE: Dual LLM (Groq ⚡ + NVIDIA ☁) │ MODE: Text     │", TEXT_GREEN),
        ("text", "╰──────────────────────────────────────────────────────────────────────────╯", TEXT_BLUE),
        ("blank", "", TEXT_WHITE),

        # Scene 2: Natural Query & System Diagnostic
        ("prompt", "ultron [Main Chat] > What's my system status and what tools are ready?", TEXT_YELLOW),
        ("text", "  [⚡ ULTRON INTELLIGENCE] Gathering active telemetry and skill registry...", TEXT_GREEN),
        ("text", "  ● OS: Linux/Windows (x86_64) │ CPU: 12% │ Memory: 4.8 GB / 16.0 GB", TEXT_WHITE),
        ("text", "  ● Active Engine: Dual LLM Router (Fast: Groq LPU 500+ tok/s, Deep: NVIDIA NIM)", TEXT_CYAN),
        ("text", "  ● Registered Skills: System Control, Web Search, Audio Devices, App Launch, Notes", TEXT_WHITE),
        ("text", "  ● I'm ready to manage your workflow, launch applications, or query live documents.", TEXT_WHITE),
        ("blank", "", TEXT_WHITE),

        # Scene 3: Skill Execution / Tool Calling
        ("prompt", "ultron [Main Chat] > Search the web for latest AI news and open the browser", TEXT_YELLOW),
        ("text", "  [🔧 TOOL EXECUTION] Invoking WebSearchSkill(query='latest AI agents')...", TEXT_MAGENTA),
        ("text", "  ✓ Retrieved 5 verified news articles via DuckDuckGo Search API.", TEXT_GREEN),
        ("text", "  [🔧 TOOL EXECUTION] Invoking ApplicationSkill(action='open_browser')...", TEXT_MAGENTA),
        ("text", "  ✓ Default web browser successfully opened with requested research tabs.", TEXT_GREEN),
        ("text", "  Summary: Recent breakthroughs highlight multi-agent orchestration and low-latency RAG.", TEXT_WHITE),
        ("blank", "", TEXT_WHITE),

        # Scene 4: Slash Command LLM Switcher (/model)
        ("prompt", "ultron [Main Chat] > /model", TEXT_YELLOW),
        ("text", "  ╭── LLM ENGINE SWITCHER ───────────────────────────────────────────────╮", TEXT_BLUE),
        ("text", "  │  ● Current: Dual LLM (Groq 70B Fast + NVIDIA Nemotron-3 Deep)        │", TEXT_GREEN),
        ("text", "  │  1. groq    — Ultra high-speed LPU inference (500+ tokens/sec)       │", TEXT_CYAN),
        ("text", "  │  2. nvidia  — Deep complex reasoning & instruction following (NIM)  │", TEXT_CYAN),
        ("text", "  │  3. qwen    — Balanced multi-lingual instruct model                  │", TEXT_CYAN),
        ("text", "  │  4. offline — 100% private local execution with Ollama (Zero keys)   │", TEXT_DIM),
        ("text", "  ╰──────────────────────────────────────────────────────────────────────╯", TEXT_BLUE),
        ("blank", "", TEXT_WHITE),

        # Scene 5: Knowledge & Document Query (/rag)
        ("prompt", "ultron [Main Chat] > /rag What is the cancellation policy in our enterprise guidelines?", TEXT_YELLOW),
        ("text", "  [⚡ STREAMING RAG] Speculative retrieval triggered at t=0.6s (Gain: 1100ms)", TEXT_GREEN),
        ("text", "  [ANSWER] Confirmed enterprise reservations require 14 days advance written notice", TEXT_WHITE),
        ("text", "  for a 100% full refund [Doc_31 §4]. Cancellations under 7 days incur standard fee.", TEXT_WHITE),
        ("text", "  [CITATIONS] ['Doc_31 §4'] │ TTFT: 1.2ms │ Provenance Grounded: 100%", TEXT_CYAN),
        ("blank", "", TEXT_WHITE),

        # Scene 6: Session Tokens & Telemetry (/tokens)
        ("prompt", "ultron [Main Chat] > /tokens", TEXT_YELLOW),
        ("text", "  [📊 TELEMETRY] Session Tokens: 482 Prompt + 312 Completion = 794 Total", TEXT_GREEN),
        ("text", "  [⚡ LATENCY] Average TTFT: 1.4ms │ Router Speed: 420 tok/sec │ Errors: 0", TEXT_CYAN),
        ("text", "  [💾 STATE] Chat Session: 'Main Chat' (Persistent SQLite vector history active)", TEXT_WHITE),
    ]


def render_and_export(
    output_dir: Path,
    video_filename: str = "ultron_cli_demo.mp4",
    export_format: str = "auto",
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    save_screenshots: bool = True,
    os_style: str = "auto"
):
    font_regular, font_bold, font_small = get_fonts()
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = output_dir / "screenshots"
    if save_screenshots:
        screenshots_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp(prefix="ultron_record_"))
    print(f"============================================================")
    print(f"        ULTRON CLI CROSS-PLATFORM RECORDER & SCREENSHOTS    ")
    print(f"============================================================")
    print(f"[INFO] Host OS: {platform.system()} ({platform.release()})")
    print(f"[INFO] Resolution: {width}x{height} @ {fps}fps")
    print(f"[INFO] Temporary frame buffer: {temp_dir}\n")

    storyboard = get_normal_cli_storyboard()
    frame_idx = 0
    active_lines = []
    scene_number = 1
    captured_frames_for_webp = []

    print("[1/3] Rendering simulated CLI frames...")

    for item_type, content, col in storyboard:
        if item_type == "prompt":
            prefix_len = content.find(">") + 2 if ">" in content else 9
            prompt_prefix = content[:prefix_len]
            to_type = content[prefix_len:]

            # Typing simulation
            step = 3 if len(to_type) > 40 else 2
            for i in range(1, len(to_type) + 1, step):
                curr_text = to_type[:i]
                img, term_box = create_frame_canvas(width, height, font_small, os_style=os_style)
                draw = ImageDraw.Draw(img)

                y = term_box[1]
                for _, l_text, l_col in active_lines[-18:]:
                    draw.text((term_box[0], y), l_text, fill=l_col, font=font_regular)
                    y += 24

                draw.text((term_box[0], y), prompt_prefix + curr_text + "█", fill=col, font=font_bold)
                frame_path = temp_dir / f"frame_{frame_idx:05d}.png"
                img.save(frame_path)
                frame_idx += 1

            active_lines.append(("prompt", content, col))

        elif item_type == "text":
            active_lines.append(("text", content, col))
            # Hold text output for 2-3 frames
            for _ in range(2):
                img, term_box = create_frame_canvas(width, height, font_small, os_style=os_style)
                draw = ImageDraw.Draw(img)
                y = term_box[1]
                for _, l_text, l_col in active_lines[-18:]:
                    draw.text((term_box[0], y), l_text, fill=l_col, font=font_regular)
                    y += 24
                frame_path = temp_dir / f"frame_{frame_idx:05d}.png"
                img.save(frame_path)
                frame_idx += 1

        elif item_type == "blank":
            active_lines.append(("blank", "", TEXT_WHITE))
            # Save a key milestone screenshot at each section break
            if save_screenshots:
                img, term_box = create_frame_canvas(width, height, font_small, os_style=os_style)
                draw = ImageDraw.Draw(img)
                y = term_box[1]
                for _, l_text, l_col in active_lines[-18:]:
                    draw.text((term_box[0], y), l_text, fill=l_col, font=font_regular)
                    y += 24
                shot_name = screenshots_dir / f"scene_{scene_number:02d}.png"
                img.save(shot_name)
                print(f"  [📸 SCREENSHOT] Saved: {shot_name.name}")
                scene_number += 1

    # Hold on final frame for 3.0 seconds
    final_img, term_box = create_frame_canvas(width, height, font_small, os_style=os_style)
    final_draw = ImageDraw.Draw(final_img)
    y = term_box[1]
    for _, l_text, l_col in active_lines[-18:]:
        final_draw.text((term_box[0], y), l_text, fill=l_col, font=font_regular)
        y += 24

    if save_screenshots:
        shot_name = screenshots_dir / f"scene_{scene_number:02d}_final_summary.png"
        final_img.save(shot_name)
        print(f"  [📸 SCREENSHOT] Saved: {shot_name.name}")

    for _ in range(int(fps * 3.0)):
        frame_path = temp_dir / f"frame_{frame_idx:05d}.png"
        final_img.save(frame_path)
        frame_idx += 1

    print(f"\n[2/3] Completed rendering {frame_idx} frames.")

    # Check for FFmpeg
    ffmpeg_exe = find_ffmpeg_executable()
    has_ffmpeg = ffmpeg_exe is not None

    if export_format == "screenshots_only":
        print(f"[3/3] Screenshots generated successfully.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return

    # Video / Animation Encoding
    print(f"[3/3] Compiling video/animation output...")

    # 1. MP4 Encoding (if requested/auto and ffmpeg exists)
    mp4_target = output_dir / video_filename
    if export_format in ("auto", "mp4", "all"):
        if has_ffmpeg:
            print(f"  Encoding MP4 via FFmpeg ({ffmpeg_exe})...")
            cmd = [
                ffmpeg_exe, "-y",
                "-framerate", str(fps),
                "-i", str(temp_dir / "frame_%05d.png"),
                "-c:v", "libx264",
                "-profile:v", "high",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                str(mp4_target)
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"  [✔ MP4 VIDEO] {mp4_target.resolve()} ({mp4_target.stat().st_size / 1024:.1f} KB)")
            except Exception as e:
                print(f"  [WARNING] FFmpeg compilation failed ({e}). Falling back to WebP animation.")
                has_ffmpeg = False
        else:
            print("  [NOTE] FFmpeg not found on this system.")
            if platform.system() == "Windows":
                print("         To install on Windows: winget install Gyan.FFmpeg (or choco install ffmpeg)")
            elif platform.system() == "Darwin":
                print("         To install on macOS:   brew install ffmpeg")
            else:
                print("         To install on Linux:   sudo apt install ffmpeg (or sudo dnf install ffmpeg)")
            print("         -> Automatically exporting high-resolution animated WebP (no ffmpeg needed)...")

    # 2. Pure Python Animated WebP (Zero dependencies, 100% reliable on Windows & all OS)
    webp_target = output_dir / (Path(video_filename).stem + ".webp")
    if export_format in ("webp", "all") or (export_format == "auto" and not has_ffmpeg):
        print(f"  Compiling animated WebP with Pillow (sample rate: 2x)...")
        # Step every 2 frames for fast WebP encoding and small file size
        sampled_imgs = []
        for i in range(0, frame_idx, 2):
            p = temp_dir / f"frame_{i:05d}.png"
            if p.exists():
                sampled_imgs.append(Image.open(p))

        if sampled_imgs:
            sampled_imgs[0].save(
                webp_target,
                save_all=True,
                append_images=sampled_imgs[1:],
                duration=int(1000 / (fps / 2)),
                loop=0,
                quality=90,
                method=4
            )
            print(f"  [✔ ANIMATED WEBP] {webp_target.resolve()} ({webp_target.stat().st_size / 1024:.1f} KB)")

    # 3. Pure Python Animated GIF (if requested)
    gif_target = output_dir / (Path(video_filename).stem + ".gif")
    if export_format in ("gif", "all"):
        print(f"  Compiling animated GIF with Pillow (sample rate: 3x)...")
        gif_imgs = []
        for i in range(0, frame_idx, 3):
            p = temp_dir / f"frame_{i:05d}.png"
            if p.exists():
                gif_imgs.append(Image.open(p).convert("P", palette=Image.ADAPTIVE))

        if gif_imgs:
            gif_imgs[0].save(
                gif_target,
                save_all=True,
                append_images=gif_imgs[1:],
                duration=int(1000 / (fps / 3)),
                loop=0
            )
            print(f"  [✔ ANIMATED GIF] {gif_target.resolve()} ({gif_target.stat().st_size / 1024:.1f} KB)")

    # Cleanup temporary frame images
    shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"\n============================================================")
    print(f" [SUCCESS] Recording & Screenshots completed successfully!  ")
    print(f"============================================================")
    if save_screenshots:
        print(f" 📸 Screenshots: {screenshots_dir.resolve()} ({scene_number} PNG images)")
    if mp4_target.exists():
        print(f" 🎥 MP4 Video:   {mp4_target.resolve()}")
    if webp_target.exists():
        print(f" 🌐 WebP Video:  {webp_target.resolve()}")
    if gif_target.exists():
        print(f" 🎞️ GIF Video:   {gif_target.resolve()}")
    print(f"============================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Record Ultron Main CLI Demo Video & Screenshots.")
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("."), help="Directory for video & screenshots")
    parser.add_argument("--name", type=str, default="ultron_cli_demo.mp4", help="Output video file name")
    parser.add_argument("--format", choices=["auto", "mp4", "webp", "gif", "all", "screenshots_only"],
                        default="auto", help="Output format: auto (MP4 if ffmpeg else WebP), mp4, webp, gif, all, screenshots_only")
    parser.add_argument("--screenshots", action="store_true", help="Generate standalone high-res PNG screenshots")
    parser.add_argument("--no-screenshots", action="store_true", help="Skip PNG screenshots")
    parser.add_argument("--os", choices=["auto", "windows", "linux", "mac"], default="auto",
                        help="Window border styling (auto adapts to Windows/Mac/Linux)")
    parser.add_argument("--fps", type=int, default=24, help="Frames per second (default: 24)")
    parser.add_argument("--width", type=int, default=1280, help="Width in pixels (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Height in pixels (default: 720)")
    args = parser.parse_args()

    save_shots = not args.no_screenshots
    fmt = "screenshots_only" if args.screenshots else args.format

    render_and_export(
        output_dir=args.output_dir,
        video_filename=args.name,
        export_format=fmt,
        width=args.width,
        height=args.height,
        fps=args.fps,
        save_screenshots=save_shots,
        os_style=args.os
    )


if __name__ == "__main__":
    main()
