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

## 💻 CLI Command Reference

Once inside the interactive CLI (`python run.py`), all commands start with `/`. You can also type bare words like `demo` or `rag` and they auto-route to their slash equivalents.

### General

| Command | Description |
|---|---|
| `/help` | Show all available commands |
| `/clear` | Clear current conversation context and start fresh |
| `/exit` or `/quit` | Save session and shut down ULTRON |

### LLM & Model Management

| Command | Description |
|---|---|
| `/model` | Show current active LLM provider |
| `/model groq` | Switch to Groq Cloud |
| `/model nvidia` | Switch to NVIDIA NIM |
| `/model qwen` | Switch to local Ollama/Qwen |
| `/model dual` | Switch to dual-tier (fast + heavy) mode |
| `/model nebius` | Switch to Nebius Token Factory |
| `/key <provider> <api_key>` | Set an API key — e.g. `/key nvidia nvapi-xxxx` |
| `/setup` or `/keys` | Launch interactive API key setup wizard |
| `/hub` or `/providers` | Show all available LLM provider portals with links |

### Voice & Interaction Modes

| Command | Description |
|---|---|
| `/listen` or `/talk` or `/mic` | Capture a single voice turn (speak → process) |
| `/nowake` | Switch to Push-to-Talk mode (no wake word) |
| `/wakeword` | Switch to Wake Word mode ("Hey Ultron") |
| `/continuous` or `/voicechat` | Switch to Continuous listening mode |
| `/voice on` or `/voice off` | Enable/disable spoken voice replies |
| `/text` | Switch to text-only responses (no audio) |
| `/mode <mode>` | Switch mode: `no-wake`, `wakeword`, `continuous`, `text`, `online`, `offline`, `hybrid` |

### Streaming RAG (Theme 4)

| Command | Description |
|---|---|
| `/rag <question>` | Run a question through the Streaming Live RAG engine |
| `/rag stream <question>` | Stream RAG response token-by-token with live citations |
| `/rag corpus` | View indexed enterprise & Samsung PRISM corpus |
| `/rag context` or `/rag state` | Inspect active RAG session state (version, entities, citations) |
| `/rag add <file>` or `/rag ingest` | Ingest a new document into the RAG corpus |
| `/rag select` | Browse and select documents to ingest |
| `/rag reset` | Clear RAG session memory for current session |
| `/rag benchmark` | Run the full Samsung PRISM benchmark suite |
| `/rag demo` or `/rag record` | Launch the 9-scene demo broadcast |
| `/rag policy` or `/rag eval` | Evaluate 15 official policy questions |
| `/rag questions` | List all 15 official evaluation questions |

### Session Management

| Command | Description |
|---|---|
| `/chats` | List all saved chat sessions |
| `/switch <session_id>` | Switch to a different chat session |
| `/new [title]` | Create a new chat session |
| `/delete <session_id>` | Delete a chat session |
| `/rename <new_title>` | Rename current chat session |

### Settings & Configuration

| Command | Description |
|---|---|
| `/settings` | View all current settings |
| `/set <key> <value>` | Update a setting — e.g. `/set voice_enabled true` |
| `/tokens` | Show token usage statistics |
| `/guardrails on` or `/guardrails off` | Toggle safety guardrails |

### System & Utilities

| Command | Description |
|---|---|
| `/ps <command>` or `!<command>` | Execute a shell/PowerShell command |
| `/demo [auto\|step]` | Run the 9-scene evaluation demo |
| `/policy` | Run policy question evaluation |
| `/questions` | Display the 15 official evaluation questions |
| `/upgrade` | Update ULTRON to latest release (pulls repo, deps, migrations) |

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
│
│── Entry Points
├── run.py                       # Unified launcher — text / voice / wakeword / demo / hub / upgrade
├── main.py                      # Lightweight CLI entry point
├── main_gui.py                  # PyQt6 GUI entry point
│
│── Configuration
├── pyproject.toml               # Project metadata, deps, scripts
├── .env.example                 # Environment variable template (copy to .env)
├── docker-compose.yml           # Containerized deployment
├── Dockerfile                   # Container image definition
│
├── config/                      # Application configuration
│   ├── settings.py              #   Pydantic-based settings loader
│   ├── user_settings.py         #   Per-user runtime settings (voice, guardrails, mode)
│   ├── constants.py             #   Application-wide constants
│   └── logging_config.py        #   Structured logging (Loguru + structlog)
│
├── core/                        # Core orchestration layer
│   ├── assistant.py             #   Top-level Assistant facade — state machine
│   ├── orchestrator.py          #   Pipeline coordinator (input → intent → skill → response)
│   ├── container.py             #   Dependency injection container
│   ├── event_bus.py             #   Async event pub/sub system
│   ├── state.py                 #   State machine definitions (IDLE → LISTENING → THINKING → RESPONDING)
│   ├── lifecycle.py             #   Application boot/shutdown hooks
│   ├── session_manager.py       #   Multi-session chat management
│   ├── database.py              #   SQLite persistence layer
│   ├── reminder_scheduler.py    #   Scheduled reminder execution
│   ├── permissions.py           #   Skill permission gating
│   ├── validator.py             #   Input validation layer
│   └── cancellation.py          #   Async task cancellation
│
├── intelligence/                # NLU & reasoning pipeline
│   ├── intent_detector.py       #   LLM-powered intent classification
│   ├── planner.py               #   Task planning from detected intents
│   ├── router.py                #   Route tasks → skills
│   ├── parser.py                #   LLM response parsing & extraction
│   ├── agent_loop.py            #   Autonomous agent loop (multi-step)
│   ├── decomposer.py            #   Multi-intent query decomposition
│   ├── executor.py              #   Plan executor
│   ├── synthesizer.py           #   Response synthesis from skill outputs
│   ├── tool_dispatcher.py       #   Tool calling dispatch
│   ├── tool_registry.py         #   Tool registration & schema
│   ├── task.py                  #   Task data model
│   ├── models.py                #   NLU data models
│   ├── telemetry.py             #   Inference telemetry
│   ├── embeddings.py            #   Text embedding generation
│   ├── retriever.py             #   Vector retrieval
│   ├── hybrid_retriever.py      #   Hybrid (dense + sparse) retrieval
│   ├── reranker.py              #   Cross-encoder reranking
│   ├── retrieval_controller.py  #   Retrieval strategy controller
│   ├── retrieval_handler.py     #   Retrieval execution handler
│   ├── emotion_detector.py      #   Emotion/sentiment detection
│   ├── weaviate_client.py       #   Weaviate vector DB client
│   └── ingest_weaviate.py       #   Weaviate document ingestion
│
├── llm/                         # Multi-provider LLM abstraction
│   ├── base.py                  #   Abstract LLM interface
│   ├── nvidia.py                #   NVIDIA NIM implementation
│   ├── groq.py                  #   Groq Cloud (LPU) implementation
│   ├── nebius.py                #   Nebius Token Factory
│   ├── dual.py                  #   Dual-tier (fast + heavy) strategy
│   ├── qwen.py                  #   Ollama/Qwen local implementation
│   ├── mock.py                  #   Mock provider for testing
│   ├── switcher.py              #   Runtime hot-swap between providers
│   ├── tools.py                 #   Tool/function calling definitions
│   ├── prompts.py               #   System & few-shot prompts
│   └── response.py              #   Typed response envelope
│
├── skills/                      # Extensible skill system (25+ skills)
│   ├── base.py                  #   Abstract Skill contract
│   ├── registry.py              #   Skill lookup registry
│   ├── manager.py               #   Lifecycle management
│   ├── system_skills.py         #   Volume, brightness, mic control
│   ├── browser_skill.py         #   URL navigation & browser launch
│   ├── chrome_control_skill.py  #   Chrome tab/window automation
│   ├── chrome_takeover.py       #   Full Chrome session takeover
│   ├── web_skill.py             #   Web search & result summarization
│   ├── chat_skill.py            #   General conversation & Q&A
│   ├── memory_skills.py         #   Fact store/recall
│   ├── file_skill.py            #   File operations (CRUD)
│   ├── code_skill.py            #   Code generation & execution
│   ├── document_skill.py        #   Document creation & editing
│   ├── excel_skill.py           #   Excel/spreadsheet generation
│   ├── notes_skill.py           #   Note taking
│   ├── reminder_skill.py        #   Reminder scheduling
│   ├── research_skill.py        #   Deep web research
│   ├── vision_skill.py          #   Screen/image analysis
│   ├── screen_text_skill.py     #   OCR from screen regions
│   ├── clipboard_skill.py       #   Clipboard read/write
│   ├── desktop_skill.py         #   Desktop environment control
│   ├── window_skill.py          #   Window management (move, resize, snap)
│   ├── media_skill.py           #   Media playback control
│   ├── audio_device_skill.py    #   Audio device switching
│   ├── farewell_skill.py        #   Graceful farewell/exit handling
│   ├── System.py                #   Low-level system commands
│   └── system_scanner.py        #   Hardware/software scanner
│
├── speech/                      # Audio I/O subsystem
│   ├── speechconfig.py          #   Audio device configuration
│   ├── hold_to_talk.py          #   Push-to-talk key controller
│   ├── microphone.py            #   Microphone input handler
│   ├── recorder.py              #   Audio capture
│   ├── audio_bus.py             #   Audio stream routing
│   ├── audio_player.py          #   Audio output playback
│   ├── mic_guard.py             #   Mic mute during TTS playback
│   ├── stt_stream.py            #   Streaming STT with partial transcripts
│   ├── speech_to_text/          #   STT pipeline
│   │   ├── transcriber.py       #     Faster Whisper transcription
│   │   ├── recorder.py          #     Audio capture with VAD
│   │   ├── stt_pipeline.py      #     End-to-end STT orchestration
│   │   └── vad.py               #     Silero Voice Activity Detection
│   ├── text_to_speech/          #   TTS pipeline
│   │   ├── speaker.py           #     Piper speech synthesis
│   │   ├── player.py            #     Audio output playback
│   │   ├── tts_pipeline.py      #     End-to-end TTS orchestration
│   │   └── ultron_dsp.py        #     Audio DSP (pitch, speed, effects)
│   └── wake_word/               #   Wake word detection
│       └── detector.py          #     Porcupine / OpenWakeWord engine
│
├── streaming_rag/               # Speculative Streaming Live RAG engine
│   ├── pipeline.py              #   Main RAG pipeline (speculative pre-retrieval)
│   ├── controller.py            #   Stream controller & orchestration
│   ├── retrieval.py             #   Document retrieval with citation tracking
│   ├── decomposer.py            #   Multi-intent query decomposition
│   ├── synthesizer.py           #   Grounded answer synthesis with provenance
│   ├── corpus.py                #   Enterprise corpus management
│   ├── ingest.py                #   Document ingestion (PDF, DOCX, TXT)
│   ├── session.py               #   Session state & entity tracking
│   ├── models.py                #   Data models (StreamingChunk, RAGResult)
│   ├── telemetry.py             #   Latency & token telemetry
│   ├── benchmark.py             #   Samsung PRISM gate evaluation (G0–G9)
│   └── cli.py                   #   RAG CLI sub-commands
│
├── memory/                      # Persistent context memory
│   ├── models.py                #   MemoryFact data model
│   ├── store.py                 #   JSON-backed persistence
│   ├── extractor.py             #   Fact extraction from conversations
│   └── service.py               #   Memory service facade
│
├── vision/                      # Vision & screen analysis
│   ├── vision_client.py         #   Multi-provider vision API client
│   ├── screen_capture.py        #   Screenshot capture
│   ├── screen_context.py        #   Screen context extraction
│   ├── screen_hider.py          #   Privacy screen hiding
│   ├── ocr.py                   #   On-screen OCR
│   └── pasted_image.py          #   Clipboard image handling
│
├── ui/                          # Desktop GUI
│   ├── main_window.py           #   PyQt6 main window
│   ├── chat_panel.py            #   Chat message panel
│   ├── orb_widget.py            #   Animated orb status indicator
│   └── tray.py                  #   System tray integration
│
├── utils/                       # Shared utilities
│   ├── cli.py                   #   Terminal UI helpers & banner
│   ├── cli_dashboard.py         #   Full interactive CLI dashboard & slash commands
│   ├── api_key_manager.py       #   Multi-provider API key management
│   ├── model_picker.py          #   Interactive model selection
│   ├── updater.py               #   Self-update (git pull + deps)
│   ├── cache.py                 #   LLM response caching
│   ├── preflight.py             #   System dependency checks
│   ├── single_instance.py       #   Prevent duplicate launches
│   ├── autostart.py             #   OS autostart registration
│   ├── consent.py               #   User consent management
│   ├── console.py               #   Rich console utilities
│   ├── env.py                   #   .env file manipulation
│   ├── record_store.py          #   Audio recording storage
│   ├── speech_text.py           #   Speech/text conversion utils
│   ├── when.py                  #   Conditional execution helpers
│   ├── decorators.py            #   Reusable decorators
│   ├── helpers.py               #   General utilities
│   ├── exceptions.py            #   Custom exception hierarchy
│   └── validators.py            #   Input validation
│
├── tests/                       # Test suite — 60+ test modules (pytest)
├── scripts/                     # Setup, bootstrap, demo recording scripts
├── website/                     # Official website (ultron.abhinavkumarsingh.tech)
├── submission/                  # Samsung PRISM submission assets
├── docs/                        # Documentation
├── deploy/                      # Cloudflare Workers installer
└── assets/                      # Static assets & branding
```

### 🔄 Request Lifecycle Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INPUT                                        │
│  Voice (Mic → VAD → Faster Whisper)  or  Text (CLI Prompt)  or  GUI        │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  1. EVENT BUS — UserInputEvent published                                     │
│     - Guardrails check (safety filter)                                       │
│     - Slash command interception (/rag, /model, /demo, etc.)                 │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                          ┌────────┴────────┐
                          ▼                 ▼
                   Regular Prompt      /rag <query>
                          │                 │
                          ▼                 ▼
┌──────────────────────────────┐  ┌────────────────────────────────────────────┐
│  2. INTELLIGENCE PIPELINE    │  │  2b. STREAMING RAG PIPELINE                │
│  ┌─────────────────────────┐ │  │  ┌──────────────────────────────────────┐  │
│  │ Intent Detection (LLM)  │ │  │  │ Speculative Pre-Retrieval            │  │
│  │ → classify user intent  │ │  │  │ → starts BEFORE speech completes     │  │
│  └───────────┬─────────────┘ │  │  └───────────────┬──────────────────────┘  │
│  ┌───────────▼─────────────┐ │  │  ┌───────────────▼──────────────────────┐  │
│  │ Multi-Intent Decomposer │ │  │  │ Query Decomposition                  │  │
│  │ → split compound queries│ │  │  │ → parallel sub-query fan-out         │  │
│  └───────────┬─────────────┘ │  │  └───────────────┬──────────────────────┘  │
│  ┌───────────▼─────────────┐ │  │  ┌───────────────▼──────────────────────┐  │
│  │ Task Planner            │ │  │  │ Retrieval + Reranking                │  │
│  │ → create execution plan │ │  │  │ → corpus search with citation tags   │  │
│  └───────────┬─────────────┘ │  │  └───────────────┬──────────────────────┘  │
│  ┌───────────▼─────────────┐ │  │  ┌───────────────▼──────────────────────┐  │
│  │ Router → Skill Dispatch │ │  │  │ Grounded Synthesis [Doc_XX §YY]      │  │
│  └──────────────────────── ┘ │  │  │ → zero hallucination, uncertainty    │  │
└──────────────────────────────┘  │  └──────────────────────────────────────┘  │
                          │       └────────────────────────────────────────────┘
                          │                 │
                          ▼                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  3. SKILL EXECUTION                                                          │
│     ApplicationSkill, BrowserSkill, WebSkill, MathSkill, FileSkill,          │
│     VisionSkill, MemorySkill, ChatSkill, SystemSkills, ...                   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  4. RESPONSE SYNTHESIS                                                       │
│     - Format response text                                                   │
│     - Attach citations (RAG) / telemetry / token counts                      │
│     - ResponseReadyEvent published on EventBus                               │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                          ┌────────┴────────┐
                          ▼                 ▼
                    CLI / GUI          Voice (TTS)
                    Rich Panel       Piper → Speaker
                                   → Audio Playback
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
