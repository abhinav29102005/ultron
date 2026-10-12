# ULTRON Main CLI — Video Recording & Screenshot Guide

This guide explains how to record videos and capture pixel-perfect screenshots of the **ULTRON Autonomous AI Desktop Agent & Cloud LLM Hub** CLI on **Windows**, **macOS**, and **Linux**.

---

## 📸 1. One-Command Screenshot Capture (Cross-Platform)

You can generate high-resolution, broadcast-ready screenshots of the main Ultron CLI without any external tools:

### Method A: Using the CLI Script
```bash
python scripts/record_cli_video.py --screenshots
```
- **Output**: Generates pristine 720p/1080p `.png` files saved directly to [`./screenshots/`](file:///home/bigboyaks/Projects/ultron/screenshots):
  - `scene_01.png` — Ultron ASCII Banner & Online Initialization
  - `scene_02.png` — System Telemetry & Available Desktop Skills
  - `scene_03.png` — Autonomous Web Search & Application Launching
  - `scene_04.png` — Multi-Provider LLM Switcher (`/model` with Groq, NVIDIA, Qwen, Ollama)
  - `scene_05.png` — Grounded Knowledge Retrieval & Citations (`/rag`)
  - `scene_06_final_summary.png` — Session Telemetry & Token Metrics (`/tokens`)

### Method B: From Inside the Interactive Ultron CLI
While running `ultron`, simply type:
```text
ultron [Main Chat] > /screenshot
```
This instantly saves the entire screenshot suite into `./screenshots/`.

### Method C: Vector SVG Screenshots (Razor-Sharp at 4K)
```bash
python scripts/record_demo.py --screenshots --mode auto --speed fast
```
- Exports vector `.svg` files (`demo_01_banner.svg`, `demo_02_capabilities.svg`, etc.) that can be opened in any browser (Chrome, Edge, Safari) and scale infinitely without blur.

---

## 🎥 2. Automated Terminal Video & Animation Generation

If you don't want to manually record your screen, the automated generator creates a complete demonstration video with simulated typing, tool execution, and token streaming:

### Run on Windows, macOS, or Linux:
```bash
# 1. Standard MP4 (Uses FFmpeg if present; falls back automatically to WebP if missing)
python scripts/record_cli_video.py

# 2. Pure Python WebP Animation (100% works on Windows with ZERO external tools needed)
python scripts/record_cli_video.py --format webp

# 3. Generate Everything (MP4, animated WebP, animated GIF, and all PNG screenshots)
python scripts/record_cli_video.py --format all

# 4. Custom resolution (e.g., 1080p 30fps)
python scripts/record_cli_video.py --width 1920 --height 1080 --fps 30
```

> **FFmpeg on Windows**: If you want MP4 format on Windows and don't have FFmpeg, install it in 10 seconds via PowerShell:
> ```powershell
> winget install Gyan.FFmpeg
> ```

---

## 🔴 3. Live Screen Recording on Any PC (Native Tools)

If you prefer recording your actual terminal while using Ultron interactively:

### On Windows 10 / 11:
1. **Windows Terminal Setup**:
   - Open **Windows Terminal** (or PowerShell).
   - Set font to **Cascadia Code** or **Consolas** (Size: 14–16).
   - Recommended window size: ~120 columns × 35 rows.
2. **Built-in Screen Recorder (Xbox Game Bar)**:
   - Press **`Win + Alt + R`** to start recording immediately.
   - Run `ultron` or `python scripts/record_demo.py --mode step`.
   - Press **`Win + Alt + R`** again to stop.
   - Video is automatically saved in `C:\Users\<You>\Videos\Captures\`.
3. **Snipping Tool Video Mode**:
   - Press **`Win + Shift + S`**, switch to the camera/video icon, select the terminal window, and click **Record**.

### On macOS:
1. Open **Terminal** or **iTerm2**.
2. Press **`Cmd + Shift + 5`** to open the native screen capture toolbar.
3. Select "Record Selected Portion", drag over the terminal window, and click **Record**.
4. Run `ultron` or `python3 scripts/record_demo.py --mode step`.
5. Click the Stop icon in the menu bar. Video saves to your Desktop.

### On Linux (Ubuntu / Fedora / Arch):
1. **OBS Studio**: Add "Window Capture" targeting your terminal.
2. **SimpleScreenRecorder / Kooha**: Select the terminal window and record at 30fps.
3. **Or launch the automated demo runner**:
   ```bash
   python3 scripts/record_demo.py --mode step
   ```

---

## 🌐 4. Interactive Web HUD Demonstration (Browser-Based)

You can also record the visual Cybernetic Terminal in any web browser:
1. Open [`docs/cli_demo.html`](file:///home/bigboyaks/Projects/ultron/docs/cli_demo.html) directly in Chrome, Edge, or Firefox (no server required; just double-click).
2. Or access it online at: **`https://ultron.abhinavkumarsingh.tech/demo`**
3. The web HUD will automatically type prompts, stream tokens, and update telemetry cards in real-time. Use your browser's recording tool or OBS to capture it.

---

## 🎙️ 5. Storyboard & Narration Script (2-Minute Walkthrough)

Use this script when recording voiceover for the normal Ultron application:

| Scene | Action / Command | Narration |
| :--- | :--- | :--- |
| **1. Intro (0:00–0:20)** | Launch `ultron` and show ASCII banner | *"Welcome to ULTRON, a production-grade autonomous desktop AI assistant and cloud LLM hub. Ultron combines high-speed cloud inference, local offline execution, and autonomous desktop tool execution into a single unified cybernetic CLI."* |
| **2. Capabilities (0:20–0:45)** | Ask: *"What can you do and what's my system status?"* | *"Ultron continuously tracks hardware telemetry and manages registered desktop skills—including system diagnostics, web lookup, media and audio devices, and persistent chat sessions."* |
| **3. Skills in Action (0:45–1:10)** | Ask: *"Search the web for latest AI news and open the browser"* | *"Here, Ultron decomposes the user's intent, invokes the DuckDuckGo web search API in real-time, opens the default browser with relevant research tabs, and summarizes the findings with zero manual intervention."* |
| **4. Cloud LLM Hub (1:10–1:35)** | Type: `/model` | *"Ultron features a dual-tier LLM architecture. We can dynamically route between Groq for 500-tokens-per-second inference, NVIDIA NIM for deep complex reasoning, OpenRouter for 100+ models, or run 100% offline with local Ollama."* |
| **5. Live RAG (1:35–1:55)** | Type: `/rag <question>` | *"When querying enterprise documents or policy guidelines, Ultron's Streaming Live RAG triggers speculative retrieval before the user finishes speaking, grounding every assertion in verified citations with zero parametric hallucination."* |
| **6. Summary & Tokens (1:55–2:15)** | Type: `/tokens` | *"All sessions persist state, token counts, and latency telemetry locally. Thank you for watching this demonstration of the ULTRON autonomous desktop agent."* |
