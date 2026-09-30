<p align="center">
  <img src="assets/ultron-banner.png" alt="ULTRON" width="280" />
</p>

<h1 align="center">
  U L T R O N
</h1>

<p align="center">
  <strong>Autonomous Desktop Agent · Streaming Live RAG · Multi-Provider LLM Hub</strong><br>
  <sub>Made by <b>4 Bottle Codeka</b> · Thapar Institute of Engineering & Technology, Patiala</sub>
</p>

<p align="center">
  <a href="https://ultron.abhinavkumarsingh.tech/">🌐 Website</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="https://youtu.be/16i0Lc2PuY8">🎬 Demo Video</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-quick-start">🚀 Quick Start</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="https://github.com/abhinav29102005/ultron">⭐ GitHub</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square"/>
  <img src="https://img.shields.io/badge/Platform-Win%20·%20macOS%20·%20Linux-0ea5e9?style=flat-square"/>
  <img src="https://img.shields.io/badge/LLM-NVIDIA%20NIM%20·%20Groq%20·%20OpenRouter%20·%20Ollama-76B900?style=flat-square&logo=nvidia&logoColor=white"/>
  <img src="https://img.shields.io/badge/RAG-Streaming%20Live-ef4444?style=flat-square"/>
</p>

<br>

---

## 🏆 Samsung PRISM GenAI Hackathon 2026 — Theme 4: Streaming Live RAG

| | |
|---|---|
| **Team** | 4 Bottle Codeka |
| **College** | Thapar Institute of Engineering & Technology, Patiala |
| **Members** | Abhinav Kumar Singh (Lead), Sukhansh Mittal, Lakkshya Jha, Vikramaditya Singh |
| **Demo** | [▶ Watch on YouTube](https://youtu.be/16i0Lc2PuY8) |
| **Website** | [ultron.abhinavkumarsingh.tech](https://ultron.abhinavkumarsingh.tech/) |
| **Release Tag** | `PRISM_GENAI_HACKATHON_Y2026` |

### 📦 Submission Deliverables

| Deliverable | File | Notes |
|---|---|---|
| Presentation (PPTX) | [`Thapar_4_Bottle_Codeka_Submission.pptx`](submission/Thapar_4_Bottle_Codeka_Submission.pptx) | 12-slide deck with architecture diagrams & telemetry HUD |
| Presentation (PDF) | [`Thapar_4_Bottle_Codeka_Submission.pdf`](submission/Thapar_4_Bottle_Codeka_Submission.pdf) | High-resolution PDF export |
| Demo Video | [YouTube](https://youtu.be/16i0Lc2PuY8) | Full walkthrough with 9 evaluation scenes |

### ⚡ Instant Verification

```bash
# Gate evaluation — all 10 Samsung PRISM gates (G0–G9)
PYTHONPATH=. python3 streaming_rag/benchmark.py

# Live demo — interactive 9-scene broadcast
python3 run.py demo

# Policy Q&A — 15 questions against 21-section master policy.pdf
PYTHONPATH=. python3 scripts/test_policy_questions.py

# Test suite — 11/11 green
pytest tests/test_streaming_rag.py -v

# Docker — one command
docker compose up
```

### 📊 Benchmark Scorecard

All 10 evaluation gates passed:

| Gate | Metric | Result |
|---|---|---|
| **G1** Reproducibility | Automated test pass | ✅ 11/11 green |
| **G2** Early Retrieval | Time gain before sentence end | ✅ **+1,300ms** (target ≥800ms) |
| **G3** Multi-Intent | Parallel sub-queries | ✅ **3 concurrent** |
| **G4** Factual Grounding | Section citations accuracy | ✅ **100%** — zero hallucinated IDs |
| **G5** Session Refinement | Incremental state lineage | ✅ V₁→V₂ with baseline preservation |
| **G6** Telemetry | End-to-end trace capture | ✅ Latency, TTFT, token budgets |
| **G7** Context Discontinuity | Cross-turn coreference | ✅ Anaphora resolution |
| **G8** Intra-Stream Pivot | Mid-speech correction | ✅ Cache invalidation |
| **G9** TTFT & Token Yield | Time to first token | ✅ **16.0ms** (target <50ms) |
| **G0** Presentation Suppression | Corpus queries on reformat | ✅ **0 queries** |

---

## 🧠 What is ULTRON?

**ULTRON** is a production-grade, open-source autonomous desktop agent that unifies voice interaction, multi-provider LLM intelligence, speculative streaming RAG, and an extensible skill system into a single coherent platform.

```
Voice / Text / GUI  →  Speculative RAG  →  Multi-LLM Reasoning  →  Skill Execution  →  Response
```

Built with a clean, layered architecture — every module is independently testable, every LLM provider is hot-swappable at runtime, and every factual assertion is grounded with explicit provenance citations.

---

## ✨ Core Capabilities

| | Capability | Details |
|---|---|---|
| ⚡ | **Speculative Streaming RAG** | Pre-retrieval starts mid-utterance before speech completes — **1.3s latency savings** |
| 🎯 | **Zero Parametric Hallucination** | All facts resolve to exact provenance sections `[Doc_XX §YY]` with uncertainty flags |
| 🔑 | **Multi-Provider LLM Hub** | NVIDIA NIM · Groq · OpenRouter · OpenAI · Anthropic · Ollama (offline) |
| 🎙️ | **Voice Pipeline** | Wake word → Silero VAD → Faster Whisper STT → Piper TTS — fully local |
| 🧩 | **14+ Built-in Skills** | Apps, browser, web search, math, volume, brightness, screenshots, memory, and more |
| 🧠 | **Persistent Memory** | Remembers facts about you across sessions — JSON-backed personal knowledge graph |
| 🖥️ | **Desktop GUI** | PyQt6 interface with async event loop via qasync |
| ⌨️ | **Text & CLI Mode** | Full terminal interaction — no microphone needed |
| 📡 | **Event-Driven Architecture** | Async pub/sub event bus for clean, decoupled module communication |
| 🐳 | **Containerized** | `docker compose up` — fully portable deployment |

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Entry Points                          │
│            main.py  ·  run.py  ·  main_gui.py                │
└─────────────────────────────┬────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────┐
│                    Core Orchestration                         │
│      Assistant  ·  Orchestrator  ·  EventBus  ·  Container   │
└─────────────────────────────┬────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  Intelligence  │  │      LLM       │  │     Skills     │
│  Intent Detect │  │  NVIDIA NIM    │  │  App Launcher  │
│  Planner       │  │  Groq Cloud    │  │  Web Search    │
│  Router        │  │  OpenRouter    │  │  System Ctrl   │
│  Parser        │  │  Ollama/Qwen   │  │  Memory        │
└────────────────┘  └────────────────┘  └────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────┐
│                      Infrastructure                          │
│   Speech I/O  ·  Streaming RAG  ·  Memory  ·  UI  ·  Utils  │
└──────────────────────────────────────────────────────────────┘
```

**Pipeline:** Voice/Text → STT → Intent Detection → Planner → Skill Execution → TTS → Response

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.13+** 
- **uv** (recommended) or pip
- A microphone (for voice modes)
- At least one LLM provider key, or [Ollama](https://ollama.com/) for fully offline use

### One-Line Install

```bash
# Linux / macOS
curl -fsSL https://ultron.abhinavkumarsingh.tech/install | bash

# Windows (PowerShell)
irm https://ultron.abhinavkumarsingh.tech/install | iex
```

### Manual Setup

```bash
git clone https://github.com/abhinav29102005/ultron.git && cd ultron

# Install dependencies
uv sync            # or: pip install -e .

# Configure environment
cp .env.example .env
# → Add your API keys to .env

# Launch
python run.py
```

### Windows (One-Click)

```batch
setup.bat          & :: Installs Python 3.13 + uv + all deps
run_ultron.bat     & :: Launches ULTRON
```

---

## 🔑 LLM Provider Setup

ULTRON supports multiple LLM providers. Obtain a free key and configure it with a single command:

| Provider | Free Tier | CLI Command |
|---|---|---|
| **NVIDIA NIM** | 1,000 free credits | `ultron /key nvidia nvapi-...` |
| **Groq Cloud** | Free tier (500+ tok/s) | `ultron /key groq gsk_...` |
| **OpenRouter** | 100+ models aggregator | `ultron /key openrouter sk-or-...` |
| **OpenAI** | GPT-4o & embeddings | `ultron /key openai sk-...` |
| **Anthropic** | Claude 3.5 Sonnet | `ultron /key anthropic sk-ant-...` |
| **Picovoice** | Free wake word | `ultron /key picovoice <key>` |
| **Ollama** | 100% offline — zero keys | `ultron /mode offline` |

---

## ⌨️ Usage Modes

| Mode | Command | Description |
|---|---|---|
| **Text** (default) | `python run.py` | Terminal-based interaction — no mic needed |
| **Push-to-Talk** | `python run.py --mode no-wake` | Hold `Right Shift` to talk, release to process |
| **Wake Word** | `python run.py --mode wakeword` | Say "Hey Ultron" to activate |
| **Continuous** | `python run.py --mode continuous` | Hands-free loop — listen → respond → listen |
| **GUI** | `python main_gui.py` | Full PyQt6 desktop interface |
| **Demo** | `python run.py demo` | 9-scene evaluation broadcast |

---

## ⚙ Configuration

All config lives in `.env`. Copy the example to get started:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `nvidia` | Backend: `nvidia`, `qwen`, `groq`, `openrouter` |
| `NVIDIA_API_KEY` | — | NVIDIA NIM API key |
| `NVIDIA_MODEL` | `meta/llama-3.1-8b-instruct` | Cloud LLM model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `QWEN_MODEL` | `qwen3:4b-instruct` | Local model name |
| `STT_MODEL` | `base` | Whisper size: `tiny.en` / `base` / `small` / `medium.en` |
| `STT_DEVICE` | `cpu` | Whisper device: `cpu` or `cuda` |
| `TTS_ENGINE` | `piper` | TTS: `piper` (local) or `pyttsx3` (offline) |
| `WAKEWORD_ENGINE` | `porcupine` | Wake word engine |
| `PICOVOICE_ACCESS_KEY` | — | Picovoice key (for Porcupine) |
| `HOLD_TO_TALK_KEY` | `right_shift` | Push-to-talk key |
| `SILENCE_TIMEOUT` | `1.0` | Seconds of silence before processing |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

Full reference: [`.env.example`](.env.example)

---

## 🧩 Skills

14+ built-in skills, fully extensible:

| Skill | What it does |
|---|---|
| `ApplicationSkill` | Open, close, switch desktop apps |
| `BrowserSkill` | Navigate URLs and browser automation |
| `WebSkill` | DuckDuckGo search + result summarization |
| `ClockSkill` | Current time and date |
| `MathSkill` | Mathematical expressions via SymPy |
| `VolumeSkill` | System volume control |
| `BrightnessSkill` | Screen brightness adjustment |
| `MicSkill` | Microphone mute/unmute/toggle |
| `ScreenshotSkill` | Capture screenshots |
| `FolderSkill` | File & folder navigation |
| `WeatherSkill` | Live weather information |
| `ChatSkill` | General conversation & Q&A |
| `MemorySkill` | Remember & recall personal facts |
| `DefaultSkill` | Fallback handler |

### Writing a Custom Skill

```python
from skills.base import Skill
from intelligence.task import Task


class MySkill(Skill):
    name = "MySkill"
    description = "Does something awesome."
    version = "1.0.0"
    enabled = True

    async def execute(self, task: Task) -> str:
        # your logic
        return "Done!"
```

Register it in `SkillRegistry` — the intent router dispatches automatically.

---

## 📁 Project Structure

```
ultron/
├── run.py                    # Unified launcher (text / voice / wakeword / demo)
├── main.py                   # CLI entry point
├── main_gui.py               # GUI entry point (PyQt6)
├── pyproject.toml            # Project config & dependencies
├── .env.example              # Environment variable template
│
├── config/                   # Settings, constants, logging
├── core/                     # Orchestration — Assistant, EventBus, DI Container
├── intelligence/             # NLU — intent detection, planning, routing
├── llm/                      # LLM providers — NVIDIA NIM, Groq, Ollama, OpenRouter
├── skills/                   # Extensible skill system (14+ built-in)
├── speech/                   # Audio I/O — STT, TTS, wake word, VAD
├── streaming_rag/            # Speculative streaming RAG engine
├── memory/                   # Persistent fact memory
├── vision/                   # Vision processing
├── ui/                       # PyQt6 desktop GUI
├── utils/                    # Shared utilities & CLI helpers
├── tests/                    # Test suite (pytest)
├── scripts/                  # Setup & bootstrap scripts
├── website/                  # Official website (ultron.abhinavkumarsingh.tech)
├── submission/               # Samsung PRISM submission assets
├── docs/                     # Documentation
└── assets/                   # Static assets & branding
```

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13+ |
| Package Manager | [uv](https://docs.astral.sh/uv/) |
| Config | Pydantic Settings + python-dotenv |
| LLM | NVIDIA NIM · Groq · OpenRouter · OpenAI · Anthropic · Ollama |
| STT | Faster Whisper + Silero VAD |
| TTS | Piper TTS |
| Wake Word | Porcupine + OpenWakeWord |
| GUI | PyQt6 + qasync |
| RAG | Custom speculative streaming engine |
| Logging | Loguru + structlog |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Type Checking | mypy (strict) |
| Deployment | Docker Compose |

---

## 🧪 Running Tests

```bash
pytest                              # Run all tests
pytest -v                           # Verbose output
pytest tests/test_streaming_rag.py  # Specific module
pytest --cov=. --cov-report=html    # Coverage report
```

---

## 🔄 Upgrading

```bash
# From terminal
ultron upgrade

# From inside the interactive CLI
/upgrade
```

---

## 🗺 Roadmap

- [x] **Phase 0** — Project scaffold, module signatures, DI container
- [x] **Phase 1** — Core voice pipeline (STT, TTS, Orchestrator)
- [x] **Phase 2** — Extensible skill system, desktop control skills
- [x] **Phase 3** — Speculative streaming RAG, multi-provider LLM hub
- [ ] **Phase 4** — Custom ONNX wake word models, vector memory, multi-step planning

---

## 🤝 Contributing

1. **Fork** the repo
2. **Branch** — `git checkout -b feature/my-feature`
3. **Code** — follow PEP 8 (Ruff enforced), Google-style docstrings, strict type hints
4. **Test** — `pytest`
5. **PR** — submit a pull request

| Team | Scope |
|---|---|
| Core Platform | `core/`, `config/`, `utils/` |
| Speech | `speech/` |
| LLM | `llm/` |
| Intelligence | `intelligence/` |
| Skills | `skills/` |
| RAG | `streaming_rag/` |

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built with ❤️ by <b>4 Bottle Codeka</b> — Thapar Institute of Engineering & Technology, Patiala</sub>
</p>
