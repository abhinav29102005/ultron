# NEBULA: Antigravity Context & Master Session Handover

> **Welcome to the NEBULA workspace!**  
> This file is your complete ground-truth onboarding document when opening this repository in a new Antigravity IDE window or conversation. It summarizes the architecture, submission tracks, tech stack, and state of the project.

---

## 1. Project Overview & Identity

- **Project Name:** **NEBULA**
- **Repository URL:** [https://github.com/abhinav29102005/nebula](https://github.com/abhinav29102005/nebula)
- **Local Directory:** `/home/bigboyaks/Projects/nebula`
- **Target Event:** **Nebius Global AI Hackathon** ([Official Rules & Details](https://nebiusglobalaihackathon.devpost.com/rules))
- **Chosen Tracks:**
  1. **Personal AI Track** (Primary) – Always-on, private assistant with persistent memory, reusable skills, local data sovereignty, and hardware agency.
  2. **Best Apps and Agents Track** – Powerful copilot powered by NVIDIA Nemotron on Nebius Token Factory with hierarchical Nano + Super/Ultra routing.

> [!CRITICAL]
> **Zero Brand Confusion Rule:** The project is exclusively **NEBULA**. There must be **ZERO occurrences of any older project names** in code, comments, configs, assets, databases, or documentation.

---

## 2. Technical Stack & Architecture

### A. Intelligence & Model Routing (Nebius Token Factory)
- **Engine Provider:** `nebius` (via OpenAI-compatible API in `llm/nebius.py`).
- **Endpoint:** `https://api.tokenfactory.nebius.com/v1`
- **Hierarchical Two-Tier Model Architecture:**
  - **Tier 1 (Fast Calls & Stream Decider):** `nvidia/nemotron-3-nano-30b-a3b`  
    *Purpose:* Handles real-time speculative stream evaluation (<150ms TTFT), intent classification, speech boundary detection, and everyday commands. Maximizes responsiveness and stretches Nebius credits.
  - **Tier 2 (Deep Reasoning & Tool Synthesis):** `nvidia/nemotron-3-super-120b-a12b` (or `nemotron-3-ultra` / `nvidia/llama-3.1-nemotron-70b-instruct`)  
    *Purpose:* Complex multi-turn reasoning, cross-platform hardware tool execution, multi-intent decomposition, and strict grounded synthesis.
- **Provider Switching:** Runtime hot-switching supported via `/model nebius`, `/model dual`, `/model nvidia`, `/model groq`, `/model qwen`.

### B. Sovereign Personal Persistence
- **Database Engine:** Local ACID SQLite database in `data/nebula.db` (via `core/database.py` and SQLAlchemy/aiosqlite).
- **Entities Tracked:**
  - Multi-turn conversation sessions (`sessions` table)
  - Full message lineage, citations, token metrics, and latency (`messages` table)
  - Dynamic user profile and hardware preferences (`user_settings` table)
- **Zero Cloud Leakage:** All session context, user identity, and history remain strictly on the user's local machine.

### C. Operating System Hardware Agency
- **System Scanner (`skills/system_scanner.py`):** Scans CPU load, RAM usage, battery, display brightness, active applications, and all available audio endpoints via `/scan`.
- **Audio Device Switcher (`skills/audio_device_skill.py`):** Enumerate and hot-switch default audio playback sinks (headphones, speakers) and recording sources (microphones) across Linux (`pactl`), Windows (`pycaw`), and macOS.
- **System Controls (`skills/system_skills.py`, `skills/System.py`):** Native volume control, screen brightness adjustment, application launcher, and Chrome/browser automation.

### D. Speculative Live RAG Pipeline (`streaming_rag/`)
- **Real-Time Streaming Evaluation:** Evaluates timestamped partial speech transcript chunks (`0.0s`, `0.8s`, `1.6s`) and speculatively triggers dense+sparse retrieval *before* utterance completion.
- **Compound Query Decomposer:** Splits complex queries into parallel sub-queries using Nemotron-3-Nano.
- **Delta Constraint Resolver:** Updates existing answers on late-arriving constraints without restarting turns.
- **Strict Grounding:** Enforces section citations (`[Doc_XX §YY]`) with zero parametric hallucination.

### E. Speech & Voice Engine (`speech/`)
- **TTS Engine:** Piper Neural TTS using ONNX models (`speech/text_to_speech/models/en_US-bryce-medium.onnx`).
- **DSP Filter:** Nebula DSP acoustic enhancement (`speech/text_to_speech/nebula_dsp.py`).
- **Audio Bus:** Full barge-in interrupt support and real-time terminal visualizer.

---

## 3. Directory Layout

```
/home/bigboyaks/Projects/nebula/
├── assets/                  # Logos (nebula_logo.png), audio samples, visual assets
├── config/                  # Settings (settings.py, user_settings.py), logging
├── core/                    # Assistant orchestration, event bus, database persistence
├── deploy/                  # Docker configs, serverless manifests, installer
├── docs/                    # Architectural specs, hardware guides, RAG docs
├── intelligence/            # Router, tool registry, agent loop
├── llm/                     # Nebius Token Factory, NVIDIA, Dual, Groq, Qwen providers
├── memory/                  # Vector memory and long-term storage
├── scripts/                 # Bootstrap, tune, and launcher scripts
├── skills/                  # Hardware controls, scanner, audio devices, apps, web
├── speech/                  # STT streaming, Piper TTS models, Nebula DSP
├── streaming_rag/           # Speculative Live RAG engine, benchmark, corpus
├── tests/                   # Automated test suite (all real tests, zero mocks)
├── ui/                      # Cybernetic CLI terminal, system tray, orb widget
├── utils/                   # CLI dashboard, updater, API key manager, preflight
├── plan.md                  # Master hackathon blueprint, video script, Devpost details
├── README.md                # Public GitHub repository documentation
├── run.py                   # Main unified CLI entry point
├── nebula.bat / nebula.ps1  # Windows native launchers
└── pyproject.toml           # Package configuration (nebula-ai)
```

---

## 4. How to Run & Verify in This Window

### Activate Virtual Environment / Dependencies
```bash
cd /home/bigboyaks/Projects/nebula
uv sync   # or: pip install -e .
```

### Run the Interactive Cybernetic CLI
```bash
python run.py
# Or with specific mode:
python run.py --mode text
```

### Self-Upgrade & Diagnostics Engine
```bash
python run.py upgrade --check
python run.py upgrade --force
python run.py --version
```

### Run Test Suite
```bash
pytest tests/test_updater.py tests/test_system_skills_crossplatform.py tests/test_dual_llm_and_security.py -v
```

---

## 5. Current Git Status & Upstream Link

- **Local Branch:** `main`
- **Remote:** `origin` -> `https://github.com/abhinav29102005/nebula.git`
- **Status:** Clean working tree, fully pushed and synced with GitHub.

---

## 6. Immediate Next Steps for the Hackathon

1. **Review `plan.md` Section 4:** Follow the 3-minute video storyboard covering:
   - System scanner & hardware agency (`/scan`, audio device switching, brightness)
   - Nebius Token Factory inference with Nemotron-3-Nano (speculative RAG) and Nemotron-3-Super (grounded citations)
   - Local sovereign memory in `data/nebula.db`
2. **Record & Upload Demo Video:** Upload the 3-minute demonstration to YouTube.
3. **Submit on Devpost:** Submit using the project title, tagline, track selection, and written feedback provided in `plan.md` Section 5 & 6.
