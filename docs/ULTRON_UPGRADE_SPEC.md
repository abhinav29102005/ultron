# ULTRON → ULTRON Upgrade Spec

> **STATUS (updated after implementation): W1, W2, W3 and W5 are BUILT, TESTED, AND VERIFIED WORKING.**
> Only W4 (authenticated connectors / Instagram) is not started — it needs a Meta app and OAuth
> credentials that cannot be created from here. See [§0 Implementation status](#0-implementation-status).


**Purpose of this document:** a self-contained handoff for an AI model (or engineer) with no prior
context on this repository. It explains the current architecture, diagnoses five reported problems
down to specific files and lines, and specifies the fixes — including which libraries/tools to add
and in what order to build. Read the whole thing before writing code.

Repo: `ultron` (Windows 11, Python 3.13, venv at `.venv/`).
Test suite: `pytest` — **705 tests passing** at the time of writing; keep it that way.
Run it with: `.venv/Scripts/python.exe -m pytest -q -o addopts=""`
(the configured addopts require pytest-cov flags; `-o addopts=""` bypasses that).

---

## 0. Implementation status

### Built and verified (W1 + W2)

| Piece | File | Tests |
|---|---|---|
| Tool types / schema | [llm/tools.py](../llm/tools.py) | `tests/test_agent_tools.py` |
| Tool registry (23 tools) | [intelligence/tool_registry.py](../intelligence/tool_registry.py) | `tests/test_agent_tools.py` |
| Agent loop (budgets, confirm, fallback) | [intelligence/agent_loop.py](../intelligence/agent_loop.py) | `tests/test_agent_loop.py` |
| Tool → Task dispatcher | [intelligence/tool_dispatcher.py](../intelligence/tool_dispatcher.py) | `tests/test_tool_dispatcher.py` |
| `complete_with_tools` (NIM + Ollama + switcher) | `llm/nvidia.py`, `llm/qwen.py`, `llm/switcher.py`, `llm/base.py` | `tests/test_llm_tool_calling.py` |
| Screen OCR | [skills/screen_text_skill.py](../skills/screen_text_skill.py) | `tests/test_screen_tools.py` |
| Active window | [skills/window_skill.py](../skills/window_skill.py) | `tests/test_screen_tools.py` |
| Clipboard (was a stub) | [skills/clipboard_skill.py](../skills/clipboard_skill.py) | `tests/test_screen_tools.py` |
| Read / write / list files | [skills/code_skill.py](../skills/code_skill.py) | `tests/test_code_skill.py` |
| Consent parsing | [utils/consent.py](../utils/consent.py) | `tests/test_consent.py` |
| Assistant wiring + confirmation | [core/assistant.py](../core/assistant.py) | `tests/test_agent_mode.py` |

### Built and verified (W3 — control)

| Piece | File | Tests |
|---|---|---|
| Browser control (Playwright) | [skills/browser_skill.py](../skills/browser_skill.py) | `tests/test_control_skills.py` |
| Desktop control (window focus, keystrokes) | [skills/desktop_skill.py](../skills/desktop_skill.py) | `tests/test_control_skills.py` |

Tools: `browser_open`, `browser_read`, `browser_click`, `browser_type`, `focus_window`,
`press_keys`. The four acting tools are all `confirm: true`.

### Built and verified (W5 — the stubs)

| Piece | File | Tests |
|---|---|---|
| Notes (was a stub) | [skills/notes_skill.py](../skills/notes_skill.py) | `tests/test_notes_reminders.py` |
| Reminders (was a stub) | [skills/reminder_skill.py](../skills/reminder_skill.py) | `tests/test_notes_reminders.py` |
| Spoken-time parser | [utils/when.py](../utils/when.py) | `tests/test_when.py` |
| Reminder scheduler | [core/reminder_scheduler.py](../core/reminder_scheduler.py) | `tests/test_reminder_scheduler.py` |
| Atomic JSON store | [utils/record_store.py](../utils/record_store.py) | (exercised throughout) |

All three `DefaultSkill` stubs — `clipboard`, `notes`, `reminder` — are now real.

**Suite: 952 passing.** (One pre-existing unrelated failure — see the footer.)

**Verified live**, against real Ollama / `qwen2.5:3b` / real skills, not just mocks:

| Utterance | Before | After |
|---|---|---|
| "fix the bug in my code" | web search for "error" | calls `read_file` |
| "what time is it" | ok | `get_time` → "The current time is 09:35 PM." |
| "what window am I in right now" | not possible | `get_active_window` → correct window |
| "hello" / "thanks" | ok | answers in ~1s, **no** spurious tool calls |
| "what's 15 times 4" | ok | `calculate` → 60 |
| read screen text | not possible | OCR, accurate, ~6s warm on 1080p |

Settings added (`config/settings.py`): `AGENT_MODE` (default true), `AGENT_MAX_STEPS` (6),
`AGENT_TIME_BUDGET_SECONDS` (120), `AGENT_CONFIRM_TIMEOUT_SECONDS` (25).

Dependencies added: `rapidocr-onnxruntime`, `pygetwindow`, `pyperclip` (all installed).

Also verified live (real Playwright + real Chromium + real Ollama):

| Action | Result |
|---|---|
| `browser_open("example.com")` | opened, reported the page title |
| `browser_click("Learn more")` | clicked, navigated to iana.org |
| `browser_type("playwright python", target="Search", submit=True)` | **actually searched** — `?q=playwright+python` |
| `browser_open("nope.invalid")` | one clean line: `net::ERR_NAME_NOT_RESOLVED` |
| "make a note that the wifi password is swordfish" | `add_note` |
| "what notes do I have" | `list_notes` → reads them back |
| "remind me in 10 minutes to check the oven" | `set_reminder` → "I'll remind you to check the oven in 10 minutes." |
| scheduler tick with a due reminder | spoke `Reminder: check the oven` |

### Not started

- **W4** — connectors / Instagram Graph API. Needs a Meta app, OAuth credentials and a
  Business/Creator account, none of which can be created from this machine without the user's
  Meta login. The public-web half of the original request already works via `research`.
- **Proactive mode** (the optional half of W5) — a morning brief and unprompted interjections.
  The EventBus and the reminder scheduler are the hooks it would hang off.

### Known characteristics worth knowing

- **OCR takes ~6s warm** on a 1920×1080 screen (0.8s engine load, cached after the first call).
  Acceptable inside the 120s turn budget, noticeable in conversation. Reading the active window
  region rather than the whole desktop is the obvious next optimisation.
- **qwen2.5:3b invents file paths.** Asked to "fix the bug in my code" it calls `read_file` with a
  plausible-but-wrong path. The loop recovers — the failure goes back to the model, which can then
  call `get_active_window` — but a stronger model (NIM) plans this better. Switch with
  `LLM_PROVIDER=nvidia`; the key is already in `.env`.
- **Agent mode is on by default** and falls back to the classifier by itself whenever the provider
  cannot call tools, so it is safe to leave on. `AGENT_MODE=false` disables it.
- **The browser is a fresh Chromium by default, logged into nothing.** To drive your *own* Chrome
  with your sessions, set `BROWSER_ATTACH=true` and start Chrome with
  `--remote-debugging-port=9222` first. ULTRON never closes a browser it only attached to.
- **Headful falls back to headless.** A visible browser needs an interactive desktop session and
  fails with `spawn UNKNOWN` without one (a service, a scheduled task). Every browser tool still
  works headless; only the window is missing.
- **`press_keys` uses an allowlist.** Ordinary keys and shortcuts only — it will refuse anything
  else rather than sending arbitrary model output to a real window.

---

## 1. Current architecture (what exists today)

The pipeline for every utterance, voice or typed:

```
mic → STT (faster-whisper, works well)
    → IntentDetector.detect()        intelligence/intent_detector.py  (1550 lines)
    → TaskRouter.route()             intelligence/router.py           (ROUTING_TABLE dict)
    → Executor.execute()             intelligence/executor.py         (calls skill.execute(task))
    → TTS speaks the returned string
```

### The brain: one-shot intent classification

`IntentDetector` sends the utterance to the configured LLM **once**, asking it to classify into
one of **29 fixed intents** (`VALID_INTENTS`, intent_detector.py:341) with JSON output:

`weather, news, time, date, calculator, open_application, close_application, open_website,
search_web, web_lookup, play_music, media_control, system_control, file_operation,
brightness_control, mic_control, screenshot, clipboard, notes, reminder, help, greeting,
farewell, general_chat, memory_recall, memory_forget, screen_query, screen_read, file_search`

The router (`intelligence/router.py`) maps each intent to exactly one skill class via a static
`ROUTING_TABLE`. Note: `clipboard`, `notes`, and `reminder` all map to `DefaultSkill` — **they are
unimplemented stubs**.

### The models

Configured in `config/settings.py`, switched in `llm/switcher.py`:

| Role | Model | Where |
|---|---|---|
| Chat / intent | `qwen2.5:3b` | local Ollama, CPU (Intel UHD iGPU — no CUDA) |
| Vision (screen) | `qwen2.5vl:3b` | local Ollama |
| Cloud option | `meta/llama-3.1-8b-instruct` | **NVIDIA NIM — already integrated**, key in `.env` (`NVIDIA_API_KEY`), provider switch `LLM_PROVIDER=nvidia` |
| STT | faster-whisper `base` | local |

This matters for every fix below: **the machine is weak (3B model on CPU), but a cloud provider is
already wired in.** The heavy thinking can be moved to NIM without new plumbing.

### The patch layers (symptom of the core problem)

Because a 3B model misclassifies constantly, `intent_detector.py` has grown deterministic
correction layers stacked on top of the LLM:

- `WEB_LOOKUP_BLOCKERS` / `WEB_LOOKUP_TRIGGERS` (line ~43): regex lists deciding when the web
  may/must be used, overriding the model.
- `SCREEN_QUERY_RE` / `SCREEN_READ_RE` (line ~150): regex forcing screen intents because
  *"A local 3B model routes it to web_lookup about half the time"* (their own comment,
  `refers_to_the_screen`, line ~255).
- `_coalesce_site_search` (line ~460): merges "open youtube" + "search MKBHD" back into one action
  because *"a 3B model cannot be reliably instructed out of a decomposition this natural"*.
- `_fallback` (line ~1222): a full 300-line regex classifier for when Ollama is down.
- Screen follow-up detection (`continues_a_screen_turn`) with its own 30-regex list.

**Read these comments in the file — the previous developers have already documented that the 3B
model is the bottleneck.** Every reported symptom below traces back to this.

### Vision / screen context

- `skills/vision_skill.py`: on `screen_query`/`screen_read`, captures the screen
  (`vision/screen_capture.py`, JPEG, downscaled), sends **one image + one question** to
  `qwen2.5vl:3b`, speaks 1–3 sentences. No OCR, no multi-step, no actions.
- `vision/screen_context.py`: remembers exactly **one** look (image + Q + A) for **120 seconds**
  so a follow-up ("what about the second one?") can reuse it. This is the "context stored in
  parts" the user perceives. It is a *memory* of one screenshot — not an understanding of the
  user's working context.

### Research

`skills/research_skill.py` (`DeepResearchSkill`) is genuinely good and recently built: plans
sub-queries, searches (DuckDuckGo/Bing/Google HTML parsing in `skills/web_skill.py`), **fetches
the actual pages**, checks coverage, loops up to 2 rounds under a 45 s budget, and returns a cited
spoken answer. `search_web`, `web_lookup`, and `news` intents already route here.

### What does NOT exist (relevant gaps)

- No tool-calling / function-calling. The LLM never chooses tools; it labels sentences.
- No multi-step agency: every utterance = exactly one classify → one skill → one reply.
- No keyboard/mouse control, no window management, no UI automation library installed.
- No browser automation (no Playwright/Selenium/CDP — "browser control" = open a URL tab).
- No file *editing* (FileSkill opens/finds files; nothing writes code).
- No authenticated API connectors (no OAuth, no Instagram/Google/etc. clients).
- No OCR (screen text goes through a 3B vision model's eyes only).
- `clipboard` / `notes` / `reminder` intents: stubs.

Dependencies today (`pyproject.toml`): pydantic v2, httpx, ollama, openai (used for NIM),
faster-whisper, beautifulsoup4, PyQt6, sympy, psutil, etc. Nothing for automation.

---

## 2. Reported problems → root causes

### P1. "STT is fine, but the processing does something else than expected"

**Root cause: architecture, not STT.** The transcript is correct; then a 3B model performs
one-shot classification into 29 buckets. Three failure modes compound:

1. **Wrong bucket** — qwen2.5:3b misclassifies routinely (documented in-code, see §1).
2. **No bucket** — anything outside the 29 intents (e.g. *"fix the bug in my code"*,
   *"summarize this PDF"*, *"reply to that email"*) gets forced into the nearest wrong bucket or
   `general_chat`. There is no "I need to do several things with tools" path at all.
3. **Entity extraction is shallow** — one regex-normalized pass (`intelligence/parser.py`);
   nuance in the request is discarded before any skill sees it.

**Empirical demonstration** (run against the real code):

| Utterance | Screen correction | Web blocker | Result |
|---|---|---|---|
| "fix the bug in my code" | None | not blocked | 3B model free-classifies → `search_web`/`web_lookup` |
| "fix this error" | None | not blocked | same |
| "help me fix this error" | `screen_query` ✓ | — | works only for this exact phrasing |
| "can you debug my python file" | None | not blocked | free-classify → wrong |

This is exactly the user's observed behavior: *"instead of fixing it, it looks up 'error' in
Chrome"* — the utterance fell to the model, the model picked a web intent, and the router sent it
to a search/research skill.

### P2. "It screenshots, a small model stores context in parts, but it searches 'error' instead of fixing my bug"

Two independent causes:

- **Routing** (above): coding requests have no intent, so they become web searches.
- **Capability**: even routed correctly, `VisionSkill` can only *describe* a screenshot in 1–3
  spoken sentences. It cannot read code precisely (3B VL model, downscaled JPEG), cannot open the
  file, cannot edit anything. The single 120 s `ScreenContext` slot is a conversational memory,
  not project context.

### P3. "I want it to control my laptop — edit code, do Chrome tasks"

No layer for this exists (see gaps list). This is a new subsystem, not a fix.

### P4. "Cloud lookups / my Instagram stats — research like Claude does"

Half exists: `DeepResearchSkill` already does multi-round cited web research for public info.
What's missing is **authenticated, account-scoped data**: Instagram stats require the Instagram
Graph API with an OAuth token — no connector framework exists.

### P5. "Work like ULTRON — add missing skills"

Addressed by the roadmap in §4, including the stub intents (clipboard/notes/reminder), proactive
behaviors, and the agent loop that ties skills together.

---

## 3. The core fix: replace one-shot classification with a tool-calling agent loop

This is the single highest-leverage change; P1–P4 all hang off it.

### 3.1 What to build

A new `intelligence/agent_loop.py` implementing the standard tool-use loop:

```
user utterance
  → LLM (with tool/function schemas for every skill + new tools)
  → while model returns tool_calls:
        execute tool → append result → call LLM again
  → final natural-language answer → TTS
```

- Expose each existing skill as a **tool with a JSON schema** (name, description, typed
  parameters). The `Skill` base class (`skills/base.py`) should gain a `to_tool_schema()`
  classmethod; most skills already have `name`/`description` fields.
- Multi-step requests ("open YouTube and search MKBHD", "screenshot then email it") become
  natural sequential tool calls — deleting the need for `_coalesce_site_search` and the compound
  intent machinery.
- **Keep the current pipeline as fallback** exactly as the regex `_fallback` is kept today: when
  the agent provider is unreachable, degrade to the existing classify-route path. Do not delete
  `intent_detector.py` in phase 1; strangle it gradually.

### 3.2 Which model runs the loop

Tool calling on qwen2.5:3b is unreliable — do not build on it. Options in order of preference:

1. **NVIDIA NIM (already integrated)** — switch the agent loop to `LLM_PROVIDER=nvidia` and use a
   tool-capable model. `meta/llama-3.1-8b-instruct` supports tool calling; better:
   `meta/llama-3.3-70b-instruct` or `qwen/qwen2.5-coder-32b-instruct` on NIM (free tier
   credits; already have the API key + `openai`-client plumbing in `llm/nvidia*.py` /
   `llm/switcher.py`). The `openai` SDK's `tools=` parameter works against NIM endpoints.
2. **Local upgrade for offline mode**: `qwen3:4b` or `llama3.1:8b` via Ollama both support
   function calling through Ollama's `/api/chat` `tools=` parameter (the `ollama` Python package
   ≥0.3 supports it). Slower on this CPU but private. Use `utils/model_picker.py` (exists) to
   choose by RAM/VRAM.
3. Hybrid (recommended end state): **cloud for the agent/planner, local for quick classification
   and offline fallback.** `llm/switcher.py` already abstracts providers; extend it with a
   `complete_with_tools()` method on `llm/base.py` implemented by both providers.

### 3.3 Voice-safety rules for the loop

The output is spoken; the loop must be budgeted like `research_skill.py` is (read its budget
section — same philosophy): max N tool calls per turn (default 6), per-tool timeout, wall-clock
cap, and **confirmation before destructive/irreversible tools** (file writes, sending anything,
closing apps with unsaved state). Add a spoken confirm step: "I'm about to X — go ahead?"

---

## 4. Workstreams (build in this order)

### W1 — Agent loop + tool registry  *(fixes P1; prerequisite for everything)*

1. `llm/base.py`: add `complete_with_tools(messages, tools) -> ToolCallsOrText`.
2. Implement for NIM (`openai` SDK `tools=`) and Ollama (`ollama.chat(tools=)`).
3. `skills/base.py`: `to_tool_schema()`; write schemas for existing skills (app control, media,
   volume/brightness/mic, files, screenshot, vision, research, memory, clock, weather, math).
4. `intelligence/agent_loop.py`: the loop, budgets, confirmation gate.
5. Wire into `core/assistant.py` behind a setting `AGENT_MODE=true|false` (default true when a
   tool-capable provider is available; else fall back to current pipeline).
6. Tests: mock LLM returning scripted tool calls; assert sequencing, budgets, fallback,
   confirmation gating. Follow the existing test style (see `tests/test_research.py` — every
   test is offline, network stubbed).

**Acceptance:** "open youtube and look up MKBHD" executes as tool calls with no
`_coalesce_site_search`; "fix the bug in my code" no longer reaches web search (it reaches W2's
tool or asks a clarifying question).

### W2 — Real screen/code understanding  *(fixes P2)*

1. **Add OCR**: `rapidocr-onnxruntime` (no external binary, pip-only, works on CPU) — preferred
   over `pytesseract` which needs a system Tesseract install. New `vision/ocr.py`: screenshot →
   exact text with bounding boxes. The 3B VL model describes; OCR reads *exactly*. Combine both:
   VL for layout/what-is-this, OCR for precise strings (error messages, code).
2. New tools for the agent: `read_screen_text()` (OCR), `describe_screen(question)` (existing
   VisionSkill), `get_active_window()` (via `pywin32`/`pygetwindow` — title + process tells the
   agent the user is in VS Code vs Chrome).
3. New `skills/code_skill.py`: `read_file`, `write_file` (diff-preview + spoken confirm),
   `list_project`, `run_command` (allowlisted, `CREATE_NO_WINDOW` — see the console-window bug
   fixed in `utils/preflight.py`, don't regress it). For "fix the error on my screen": OCR the
   error → find the file (FileSkill's index exists) → read it → cloud model proposes a patch →
   confirm → write.
4. Route: agent tool schemas make "fix/debug/error in my code" reach these tools; add regression
   tests for the utterances in the §2 table.

### W3 — Computer & browser control  *(fixes P3)*

Two separate tracks — do not conflate them:

- **Browser automation**: add **Playwright** (`playwright` + `playwright install chromium`).
  Drive a real Chrome/Chromium via CDP: `browser_navigate`, `browser_click(selector|text)`,
  `browser_type`, `browser_read_page`. Playwright can also **attach to the user's running Chrome**
  (`connect_over_cdp` with `--remote-debugging-port=9222`) so "do this in my Chrome" works with
  their sessions. Selenium is the fallback option; Playwright's auto-wait and accessibility-tree
  APIs are better for agent use.
- **Desktop automation**: `pyautogui` (simple, screenshot-coordinate based) plus
  `uiautomation` or `pywinauto` (Windows UI Automation tree — lets the agent click *named*
  buttons instead of pixels; far more reliable). Start with: focus window, send keys, click
  element by name, read window text.
- **Safety**: both are agent tools gated by the W1 confirmation policy + a global kill phrase
  ("Ultron, stop") that halts the loop; log every action.

### W4 — Connected accounts & cloud data  *(fixes P4)*

1. Public info: already done (`DeepResearchSkill`) — expose it as a tool in W1 and it inherits
   multi-step agency ("research X, then compare with Y").
2. **Connector framework**: `connectors/` package; each connector = OAuth flow + token storage
   (encrypt at rest — `keyring` package uses Windows Credential Manager) + typed methods exposed
   as agent tools.
3. **Instagram specifically**: Meta **Instagram Graph API** (requires a Business/Creator account
   linked to a Facebook app; personal accounts can use the Basic Display API for media/profile
   only — no insights). Tools: `instagram_profile_stats()`, `instagram_recent_posts_insights()`.
   Note honestly in the UI: follower counts/impressions need the Graph API + business account;
   scraping the private API (`instagrapi`) violates ToS and risks the account — offer it only
   with an explicit user opt-in, or not at all.
4. Same pattern later: Google Calendar, Gmail, Spotify Web API (MediaSkill currently drives the
   desktop app only).

### W5 — ULTRON polish  *(P5)*

- Implement the three stub intents: `clipboard` (pyperclip / `win32clipboard`), `notes`
  (append to a local markdown store; reuse `memory/store.py` patterns), `reminder`
  (persisted schedule + spoken alert; there is a scheduler-shaped gap in `core/` — check
  `docs/roadmap.md` first, some of this is sketched there).
- Proactive mode (later): on-startup brief (calendar + reminders + headlines via research skill),
  low-battery/meeting-soon interjections. Requires an event loop hook in `core/assistant.py` —
  the EventBus (`core/event_bus.py`) already exists for this.
- Long-term memory is already present (`memory/`, `MemorySkill`) — connect it to the agent loop
  so tools can recall user facts mid-task.

---

## 5. New dependencies (summary)

| Package | For | Notes |
|---|---|---|
| `playwright` | browser control (W3) | + `playwright install chromium`; can attach to user's Chrome via CDP |
| `rapidocr-onnxruntime` | screen OCR (W2) | pip-only, CPU-friendly; avoids system Tesseract |
| `pygetwindow` + `pywin32` | active-window info (W2) | tiny |
| `pywinauto` *or* `uiautomation` | desktop UI automation (W3) | prefer UIA tree over pyautogui pixels |
| `pyautogui` | raw input fallback (W3) | last resort clicking |
| `keyring` | token storage (W4) | Windows Credential Manager |
| `pyperclip` | clipboard skill (W5) | |
| *(no new LLM SDK)* | | `openai` + `ollama` packages already cover NIM and local tool calling |

---

## 6. Repo conventions the implementer MUST follow

1. **TDD is the house style.** Every recent fix in this repo lands with a failing test first;
   test files carry a docstring naming the bug they cover (see `tests/test_preflight.py`,
   `tests/test_no_console_windows.py`, `tests/test_web_search_parsing.py`). Do the same.
2. **No network in tests.** Everything is stubbed/monkeypatched (fixture HTML lives in
   `tests/fixtures/`).
3. **Windows spawn hygiene:** any `subprocess` call must pass
   `creationflags=CREATE_NO_WINDOW` (never OR'd with `DETACHED_PROCESS` — Windows ignores
   NO_WINDOW in that combination). This exact bug was just fixed; `tests/test_no_console_windows.py`
   enforces it — extend that file for new spawn sites.
4. **Voice-first outputs:** skills return short spoken sentences — no markdown, no lists
   (see `SYSTEM_PROMPT` in `vision_skill.py` for the tone).
5. **Budgets on everything** slow: rounds, wall clock, per-item caps (model:
   `research_skill.py`).
6. **Comment style:** the codebase explains *why*, at length, at decision points. Match it.
7. **Commits:** short label messages (`feat: agent loop`), small changes batched; **no
   Co-Authored-By trailers** — sole author `Golden-alt933`.
8. The app must keep working with **Ollama down** (degraded regex fallback) and **offline**
   (local provider). Never make cloud a hard dependency.
9. Entry points: `run.py` (terminal), `main_gui.py` (PyQt), `scripts/ultron_launcher.pyw`
   (autostart under `pythonw.exe` — no console exists; see convention 3).

---

## 7. Suggested milestones

| Milestone | Contents | Definition of done |
|---|---|---|
| M1 | W1 agent loop on NIM, 10 existing skills as tools, fallback intact | §4-W1 acceptance + full suite green |
| M2 | W2 OCR + active-window + code read/patch with confirm | "what does this error say" reads exact text; "fix it" patches after confirm |
| M3 | W3 Playwright browser tools + UIA basics | "open my Chrome and star the top repo on this page" works |
| M4 | W4 connectors (Instagram first) | spoken follower/engagement stats from Graph API |
| M5 | W5 stubs implemented + proactive brief | clipboard/notes/reminder real; morning brief on wake |

Each milestone ends with the full test suite green and a short demo script in `docs/`.

---

*Known pre-existing issue, do not chase it: `tests/test_autostart.py::TestRealKeyUntouched::test_real_registration_is_absent` fails on machines where autostart is genuinely enabled (it reads the live registry). Unrelated to all of the above.*
