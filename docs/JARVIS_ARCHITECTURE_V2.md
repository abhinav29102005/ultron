# FRIDAY/Jarvis — Architecture v2 (audited)

Date: 2026-09-01.
Supersedes the draft rebuild plan (`jarvis-architecture.md` from Downloads). Every claim in
that draft was checked against this repository and this machine; this document keeps what
survived, corrects what didn't, and records the model migration that was actually performed.

**Machine (verified, not assumed):**

| | measured |
|---|---|
| GPU | NVIDIA GeForce RTX 3050 Laptop, **4096 MiB VRAM**, driver 592.27, CUDA 13.1 (`nvidia-smi`) |
| RAM | 15.7 GB |
| Disk free | ~95 GB on C: before migration |
| Ollama | 0.32.14 at `http://localhost:11434` |

> The older `docs/JARVIS_PHASE2_SPEC.md` claims "Intel UHD (no CUDA)". That is stale — the
> RTX 3050 is present and the driver works. The Intel iGPU is the second adapter of a hybrid
> laptop, not the only one.

---

## 1. Audit of the draft plan — verdict table

| Draft section | Verdict | Reality in this repo |
|---|---|---|
| §0 Check 1: set `num_ctx` explicitly | **Correct, was a real gap** | `llm/qwen.py` sent only `temperature` + `num_predict`; Ollama's small default context silently truncated agent prompts from the front. **Fixed in this migration** — see §3. |
| §0 Check 2: log raw model output | Already done | `LLMResponse.raw` is always populated (`llm/qwen.py`, `llm/response.py`). |
| §0 Check 3: A/B the fine-tune | **Stale premise** | There is no fine-tune anywhere in this repo. The local model is a base model (now `qwen3:4b-instruct`). Nothing to A/B. |
| §1 swap to `qwen3:4b` | **Half right — tested and corrected** (§3: the *instruct* variant, not plain `qwen3:4b`) | The repo's own live tests agree with the draft: `qwen2.5:3b` scored **0/2 on the agent fix loop** and parroted `"LOOKING"` from its own system prompt 3/3 (`docs/JARVIS_PHASE2_SPEC.md`). |
| §1 keep `qwen2.5vl:3b` | Correct | Installed, preloaded at startup, `keep_alive=30m`, used only by `skills/vision_skill.py`. |
| §1 both models don't fit 4 GB together | Correct — see §6 | ~2.5 GB + ~3 GB > 4 GB. The repo currently preloads the **VLM** hot, which is the opposite of the draft's advice; §6 discusses the trade. |
| §1 NIM `mistralai/mistral-nemotron` | **Exists, but repo's pick is better-evidenced** | Verified live on the endpoint (83-model listing). The repo instead uses `nvidia/nemotron-3-super-120b-a12b`, chosen after the draft was written, with measured ~1.9 s tool-calling round trips and correct tool choice on every probe (`config/settings.py` comment). Keep it; mistral-nemotron is the fallback candidate. |
| §2 provider interface | Already built | `llm/base.py` (ABC), `llm/qwen.py`, `llm/nvidia.py`, `llm/switcher.py` (runtime switching with availability probes), `llm/mock.py`. |
| §3 router | **Built, but shaped differently** | See §4. There is no per-request model tiering; there is provider switching plus agent-mode-with-fallback. |
| §3 `/no_think` for the local model | **Wrong — does not work** | Tested three ways on `qwen3:4b`; none disables reasoning (§3). `llm/qwen.py` now asks Ollama per model whether to pass `think`. |
| §4 code-edit contract | **Almost fully built** | `edit_file` tool takes `old_text`/`new_text`; `skills/code_skill.py` enforces **exactly-once** match (0 → "quote it exactly", >1 → "make it unique"), writes a `.bak` backup, edits shadow copies via `copy_to_shadow`, verifies with `run_command` (allowlisted, 45 s cap), retries up to `agent_fix_max_iterations=4` with real error text fed back. |
| §5.1 CDP attach to real Chrome | Already built | `skills/browser_skill.py` uses `connect_over_cdp`; `browser_attach=True`, port 9222; `control_my_chrome` tool restarts Chrome with the debug flag on request. |
| §5.2 DOM filtering to interactive elements | **Not built** | `_read` does `page.inner_text("body")` — a raw text dump. No ref-ID element extraction. Biggest remaining gap for browser agency. |
| §5.3 Monaco/CodeMirror write path | **Not built** | No editor-API/clipboard/insert_text ladder, no write-then-read-back verification. |
| §6 lesson memory (layers 2–3) | **Not built** | `memory/` stores user facts (extractor/store/service), not lessons. Layer 1 (retry with real error text) exists inside the fix loop. |
| §7 eval harness | **Not built** | `tests/` is unit/integration tests (good ones, some against live Ollama), but there is no fixed-task eval set with pass rates. |
| §8 security | Partially built | Risky tools carry `confirm=True` (edits, browser clicks/typing); spoken confirmation with 25 s timeout. Page-content-as-instruction hardening is prompt-level only. |
| Open decision: hardware | **Resolved** | It's the 3050 laptop. The Mac branch of the draft is dead; ignore its model suggestions. |

---

## 2. Model roster (current state, after migration)

| Model | Where | Size | Job | Wired in |
|---|---|---|---|---|
| **`qwen3:4b-instruct`** | Ollama, local | 2.5 GB | intent detection, chat, arg extraction, agent-loop fallback when offline | `QWEN_MODEL` in `.env` → `config/settings.py` → `llm/qwen.py` |
| **`qwen2.5vl:3b`** | Ollama, local | 3.2 GB | screenshot Q&A, OCR, "what's on my screen" | `VISION_MODEL` → `skills/vision_skill.py`; preloaded at boot |
| **`nvidia/nemotron-3-super-120b-a12b`** | NVIDIA NIM (free tier) | — | agent mode: multi-step tool calling, code fixing, browser driving | `llm/nvidia.py`; active when `LLM_PROVIDER=nvidia` |
| `nvidia/nemotron-3-nano-30b-a3b` | NVIDIA NIM | — | "fast" variant — **currently dead code**: no caller passes `use_fast_model=True` | `llm/nvidia.py:246` only |
| faster-whisper `base` (int8, CPU) | local | — | speech → text | `speech/speechconfig.py` |
| Piper `en_US-lessac-medium` | local | 63 MB | text → speech | `speech/text_to_speech/` |
| openWakeWord `hey_jarvis` | local | — | wake word (Porcupine unused — no Picovoice key on this machine, see §7.3) | `speech/wake_word/detector.py` |

Removed in this migration: **`qwen2.5:3b`** (1.9 GB) and plain **`qwen3:4b`** (2.5 GB).
Rationale and evidence in §3.

---

## 3. The local-model migration (completed 2026-09-01)

### Why

- `qwen2.5:3b` could not drive the tool-calling agent loop: 0/2 on the verified fix loop,
  and 3/3 runs answered with the literal word `"LOOKING"` parroted from the system prompt
  (`docs/JARVIS_PHASE2_SPEC.md`). It also invents file paths (`docs/JARVIS_UPGRADE_SPEC.md`).
- `qwen3:4b-instruct` is a generation newer, markedly better at instruction following and
  structured output, still GPU-resident at Q4 on a 4 GB card, and supports tool calling.
- Plain `qwen3:4b` — what the draft actually recommended — was pulled, measured, and
  **rejected**; see the results table below.

### Procedure used (and to reuse for any future model swap)

The ordering is the point: **verify before deleting**. A model that is deleted before its
replacement is proven leaves FRIDAY with no local model at all.

```bash
# 1. Install
ollama pull qwen3:4b-instruct

# 2. Verify BEFORE deleting anything
ollama list                                # tag present
curl -s http://localhost:11434/api/tags    # "capabilities" must include "tools"

# 3. Point FRIDAY at it — one line in .env, everything else is already wired:
#      QWEN_MODEL=qwen3:4b-instruct

# 4. Prove the app path (from the repo root):
.venv/Scripts/python.exe -c "import asyncio; from config.settings import Settings; from llm.qwen import QwenLLM; s=Settings.load(); print(asyncio.run(QwenLLM(s).complete([{'role':'user','content':'Reply with exactly: PONG'}])).content)"

# 5. Only now reclaim the space
ollama rm qwen2.5:3b
```

A one-shot `ollama pull` may stall partway; the partial blob is preallocated to full size,
so **file size is not progress** — re-running the pull resumes it.

Step 4 is necessary but not sufficient: a trivial "PONG" prompt passed on plain `qwen3:4b`
while chat, streaming and latency were all broken. Exercise chat, tool calling, JSON mode
and streaming — the four paths the app actually uses — before trusting a model. That is what
§8.1's eval harness should automate.

### Files changed

| File | Change |
|---|---|
| `.env`, `.env.example` | `QWEN_MODEL=qwen3:4b-instruct` (original saved as `.env.bak-premigration`) |
| `config/settings.py` | default `qwen_model="qwen3:4b-instruct"`; new `qwen_num_ctx=8192` |
| `llm/qwen.py` | `options={"num_ctx": ...}` on all three call paths (complete / tools / stream) — closes the draft's Check 1. Silent front-truncation of the system prompt is exactly the "it did something different" failure mode. |
| `utils/model_picker.py` | "standard" tier now installs `qwen3:4b-instruct` (2.5 GB), so bootstrap can't recommend a deleted model |
| `tests/test_model_picker.py` | expectations updated; suite passes |
| `README.md` | default model table row |

Applied in the same pass, from §7 (independent of the model swap):

| File | Change |
|---|---|
| `utils/env.py` (new) | `load_env_file()` — copies `.env` into `os.environ` so the `os.getenv` readers finally see it (§7.1) |
| `main.py`, `run.py`, `main_gui.py` | call `load_env_file()` beside `force_utf8_output()` |
| `main_gui.py` | wake-word detector built on a worker thread *after* `window.show()`; `[FRIDAY] Starting…` banner (§7.2) |
| `ui/main_window.py` | new `set_wake_detector()`, mirroring `set_stt()`, starts the wake loop on arrival |
| `run.py` | "Loading wake-word engine…" notice before the slow import in wakeword mode |

### ✅ Outcome: migrated to `qwen3:4b-instruct` — plain `qwen3:4b` was rejected on evidence

**Final state:** `QWEN_MODEL=qwen3:4b-instruct`. Both `qwen2.5:3b` and plain `qwen3:4b` are
removed; ~4.4 GB reclaimed (91 → 97 GB free). Preflight reports ok, the full suite passes
(1024 passed, 1 pre-existing unrelated failure — §7.6).

The draft plan's recommendation of plain `qwen3:4b` was **tested and rejected**: it is a
hybrid reasoning model, and the reasoning cannot be turned off. `qwen3:4b-instruct` is the
same generation without the thinking mode, and it passes every path.

| Path | `qwen2.5:3b` (old) | `qwen3:4b` (rejected) | **`qwen3:4b-instruct` (now)** |
|---|---|---|---|
| Chat — capital of France | 4.9 s | 17 s | **1.5 s** |
| Chat — "How are you today?" | 0.9 s | ❌ **empty**, 30 s | **1.8 s** |
| Chat — fun fact about space | 1.2 s | 25 s | **2.2 s** |
| Chat — "What time is it?" | 1.1 s | 16 s | **1.7 s** |
| Tool call — open youtube.com | 1.1 s ✅ | 36 s ✅ | **2.1 s ✅** |
| JSON mode (intent detector) | 0.9 s ✅ | 1.6 s ✅ | **1.3 s ✅** |
| Streaming | 0.8 s ✅ | ❌ empty after 153 s | **1.0 s ✅** |

One correction to the record while we are here: `qwen2.5:3b` **can** make a simple one-shot
tool call (measured 1.1 s, correct). Its documented 0/2 was on the far harder multi-step fix
loop — a large tool set and a long system prompt — so "cannot call tools" was too strong.
The right statement is that it cannot *drive the agent loop*.

Measured on this machine, Ollama 0.32.14, `num_ctx=8192`:

| Path | `qwen3:4b` | `qwen2.5:3b` |
|---|---|---|
| Tool call — "Please open youtube.com" | ✅ `open_website{url: youtube.com}` — **36 s** | ❌ documented 0/2 on the fix loop |
| JSON mode (intent detector) | ✅ `{"intent":"open_website"}`, eval **7** tokens, fast | ✅ works |
| Chat — "What is the capital of France?" | ✅ 17 s, eval 290 | ✅ **6.8 s**, eval 8 |
| Chat — "How are you today?" | ❌ **empty**, 30 s, hit the 512-token ceiling | ✅ **1.0 s**, eval 24 |
| Chat — "Tell me a fun fact about space." | ✅ 25 s, eval 416 | ✅ **1.1 s**, eval 26 |
| Chat — "What time is it?" | ✅ 16 s, eval 278 | ✅ **1.0 s**, eval 19 |
| Streaming — "Say hello in exactly three words." | ❌ empty after **153 s**, eval 2048 (ceiling) | ✅ fast |

**Root cause: qwen3:4b's reasoning cannot be switched off, and it runs away.**

`qwen3:4b` is a hybrid reasoning model (`capabilities: ['completion','tools','thinking']`).
All three ways of disabling it were tested and none works on this build:

| Attempt | Result |
|---|---|
| `think=False` | Model reasons **anyway** — identical `eval_count` — and Ollama, told not to expect a trace, dumps it raw into `message.content` with a stray `</think>` |
| `think=True` | Content is clean, trace correctly separated into `message.thinking` — but the tokens are still spent |
| `/no_think` in a system message | No effect |

On open-ended prompts the trace consumes the entire `num_predict` budget (2048/2048
observed) and the answer never gets emitted — hence the empty replies. The one place it is
genuinely cheap is `format="json"`, which constrains decoding and suppresses reasoning
(eval 7) — which is why the intent detector is unaffected.

Since `agent_mode=True` sends **every** utterance through the tool-calling loop first, a
straight swap would put 16–36 s on the front of every interaction with a voice assistant,
with occasional empty answers. That is a worse assistant, not a better one, even though the
agent loop finally works.

**Recommendation: `qwen3:4b-instruct-2507`** — the non-hybrid Qwen3 instruct release. Same
generation and tool support, no thinking mode to fight. That should keep the tool-calling
win without the latency. Roughly 2.6 GB; 91 GB free, so disk is not a constraint.

Fallbacks if that disappoints: keep `qwen2.5:3b` for chat and route only agent turns to
a stronger model (the switcher already makes per-provider selection cheap), or use the
NVIDIA provider for agent work.

### Code changes this exposed (kept — they are model-agnostic)

| File | Change |
|---|---|
| `llm/qwen.py` | `_thinking_supported()` — asks Ollama `/api/show` once and caches whether the model needs `think=True`. Neither value is hardcodable: `think=True` is an outright HTTP 400 on `qwen2.5:3b` ("does not support thinking"), `think=False` corrupts qwen3 output |
| `llm/qwen.py` | `strip_leaked_reasoning()` backstop on `complete()` and `complete_with_tools()`, and a buffered guard in `stream()` so a leaked trace is never spoken or streamed to the UI |

### Already verified on this machine (2026-09-01, against the old model)

These establish the working baseline the new model must match or beat:

- Ollama serving at `:11434`; `qwen2.5:3b` round trip through `QwenLLM.complete` measured
  **11.7 s** cold for a one-word reply, ~0.8 s warm.
- `tests/test_model_picker.py` + `tests/test_llm_switcher.py`: **28/28 pass** with the
  updated tier table and defaults.
- NVIDIA endpoint listing fetched live: both configured nemotron models present, and
  `mistralai/mistral-nemotron` (the draft's pick) also present.

### Rollback

`ollama pull qwen2.5:3b`, set `QWEN_MODEL=qwen2.5:3b` in `.env`. Nothing else depends on the
model name at runtime, and `.env.bak-premigration` holds the original file. Do **not** roll
back to plain `qwen3:4b` — see the table above for why it was rejected.

---

## 4. Routing — how it actually works here

The draft's router (§3) proposed per-request model tiering. The repo converged on something
simpler that fits a spoken assistant; keep it and know what it is:

```
utterance
   │
   ├─ emotion detector (rule-based, fast)                    core/assistant.py
   │
   ├─ AGENT TURN — tool-calling loop, up to 12 steps         intelligence/agent_loop.py
   │    runs on the ACTIVE provider (qwen3:4b-instruct local, or
   │    nemotron-3-super when LLM_PROVIDER=nvidia).
   │    Returns None instead of failing when the provider
   │    can't call tools / is down → falls through.
   │
   └─ CLASSIFIER PIPELINE — intent detect → plan → skills    intelligence/intent_detector.py
        LLM classification (json_mode) with a regex/rules
        fallback when the LLM call fails.                    (~29 intents, regex entity extraction)
```

Two consequences worth stating plainly:

1. **The regex layer is a fallback, not a fast path.** The draft wanted regex *first* for
   sub-500 ms trivials ("open youtube"). Today those still cost one local LLM round trip.
   That is a legitimate, small, future optimization — promote the highest-frequency exact
   phrases above the LLM call.
2. **Provider choice is per-session, not per-request.** `llm/switcher.py` switches on
   command ("switch to nvidia"), with real availability probes (key present; Ollama
   responding). The draft's "escalate `code_task` to cloud automatically" is not built;
   agent mode simply uses whatever provider is active. On `qwen3:4b-instruct` a single
   tool call lands correctly in ~2 s, so the loop is now genuinely usable locally — re-run
   the multi-step fix-loop cases before deciding cloud escalation is still needed.

Structured output note: the intent detector uses Ollama's `format="json"` (via
`json_mode=True`). Ollama ≥0.5 also accepts a full JSON **schema** in `format=` — moving the
intent enum into a schema would make malformed classifications impossible rather than
parse-and-pray. Cheap win, not yet done.

---

## 5. Code editing and verified fixing (built — the draft's §4, confirmed)

The draft's core rule — *the model chooses, deterministic code edits* — is implemented:

- `edit_file(path, old_text, new_text)`: match must be **exactly once**; zero matches →
  the model is told to re-read and quote exactly; multiple → told to widen. Never guesses.
- Every edit writes `<name>.bak` first.
- `copy_to_shadow` gives the loop a scratch copy; the user's file is untouched until a fix
  is proven.
- `run_command` (allowlist: `python,py,pytest,node,npm,code`; 45 s cap) supplies ground
  truth; stderr is fed back verbatim; `agent_fix_max_iterations=4` bounds the loop.
- Budgets: 12 tool calls/turn, 120 s/turn, 2048 output tokens (reasoning models die at 256).

What §4 of the draft adds that is still worth taking: **syntax check → linter → tests as an
ordered ladder** after each patch (today it's "whatever run_command runs"), and escalating to
the user with a diff after the retry cap instead of a prose apology.

---

## 6. VRAM budget — the one real tension in the local roster

`qwen3:4b-instruct` (~2.5 GB resident) + `qwen2.5vl:3b` (~3 GB) **cannot share the 4 GB card**. One
of them is always cold or on CPU. Current repo behavior:

- boot preloads the **VLM** with `keep_alive=30m` (`vision_preload=True`) — the opposite of
  the draft, which says keep the *chat* model hot (it's on every request's path) and let the
  VLM load on demand.

The repo's choice was made when chat was a 1.9 GB model and vision cold-loads cost ~60 s on
the user's first screen question. It is defensible; so is the draft's. The honest position:

- If screen questions are frequent → keep today's behavior; chat pays a (small) reload tax.
- If screen questions are occasional → set `VISION_PRELOAD=false` and accept seconds of
  latency on the first one; chat/agent stays hot, which is the path every request touches.

Decide from usage, not theory — `ollama ps` during a normal day answers it. Do **not** try
to keep both warm; Ollama will thrash the card. And per the draft (correct): the VLM's click
coordinates are unreliable — never drive clicks from vision; browser control must come from
the DOM/accessibility side (§8).

---

## 7. Configuration bugs found during the audit

### 7.1 `.env` never reached `os.getenv` — **FIXED**

The root cause behind several symptoms below. FRIDAY reads config two ways, and they never
met:

- `config/settings.py` is a pydantic `BaseSettings` with `env_file=".env"`. **Pydantic parses
  the file privately and does not export it to `os.environ`.**
- `speech/speechconfig.py` and `speech/wake_word/detector.py` use plain `os.getenv`, which
  only sees the real process environment.

Nothing anywhere called `load_dotenv()`. Verified directly:

```
WAKEWORD_KEYWORD in os.environ: False
AUDIO_SAMPLE_RATE  in os.environ: False
```

So every `os.getenv` key documented in `.env.example` — `STT_MODEL`, `STT_BEAM_SIZE`,
`SILENCE_TIMEOUT`, `WAKEWORD_SENSITIVITY`, `PICOVOICE_ACCESS_KEY` — silently used its
hardcoded default regardless of `.env`. Nothing errored; the settings just had no effect.

**Fix:** new `utils/env.py` with `load_env_file()`, called next to `force_utf8_output()` in
all three entry points (`main.py`, `run.py`, `main_gui.py`). Real environment variables win
over the file, matching pydantic's own precedence so the two paths agree.

This changed no current behaviour — every `.env` key those modules read was either absent or
already equal to its default — but it means `.env` edits now actually take effect.

### 7.2 GUI startup stall (~80 s of silence) — **FIXED**

`main_gui.py` constructed the wake-word detector *before* `window.show()`. The
`openwakeword` → `sklearn` → `scipy` import chain measured **114 s cold / 66 s warm** on this
machine, so a healthy launch showed no window and printed nothing for over a minute —
indistinguishable from a hang. This is the bug behind "running `main_gui.py` does nothing".

**Fix:** build it in `asyncio.to_thread` *after* first paint (the import happens inside the
thread, since the import is the slow part), handed over by a new
`MainWindow.set_wake_detector()` that mirrors `set_stt()` and starts the wake-word loop on
arrival. Plus a `[FRIDAY] Starting…` line before anything slow, because `report()` stays
silent when preflight passes and everything else logs to file.

**Measured after the fix** (instrumented boot, same machine):

```
[FRIDAY] Starting…                      +0.0s
WINDOW SHOWN                            +7.3s
Wake word engine: openWakeWord          +10.7s   (loaded, not blocking)
```

Time to visible window: **~80 s → 7.3 s**. The wake word now arrives afterwards on its own
thread; on a cold file cache it takes the full 66–114 s but the window and typing are live
the whole time.

### 7.3 Porcupine is inert — **not a bug, correcting an earlier claim**

An earlier draft of this document said `.env` sets `WAKEWORD_KEY` and that renaming it to
`PICOVOICE_ACCESS_KEY` would activate Porcupine. **That was wrong** — an artifact of a
secret-redaction regex mangling the variable name while inspecting `.env`. There is no
Picovoice key on this machine at all.

The real state: `.env` has `WAKEWORD_KEYWORD=hey_jarvis`, `WAKEWORD_ENGINE=openwakeword`,
`WAKEWORD_SENSITIVITY=0.5`. Of those, `detector.py` reads only `WAKEWORD_SENSITIVITY` (and
`WAKEWORD_KEYWORDS`, *plural* — a different key, for Porcupine's built-in keyword list).
`WAKEWORD_KEYWORD` and `WAKEWORD_ENGINE` are read by nothing.

So openWakeWord `hey_jarvis` is the engine, correctly, because no Porcupine key exists.
To switch: get a key from the Picovoice console and set `PICOVOICE_ACCESS_KEY` in `.env` —
which now works, thanks to §7.1. That would also sidestep most of the import cost in §7.2,
since `openwakeword` is what pulls in scipy.

### 7.4 Duplicated STT config — still open (cosmetic)

`Settings.stt_model / stt_device / stt_compute_type / stt_beam_size` are never read;
`speech/speechconfig.py` reads the same env var names directly. Behaviour matches, but
editing the `Settings` defaults does nothing. Pick one source of truth — either delete the
pydantic fields or have `speechconfig` derive from `Settings`.

### 7.5 `nvidia_fast_model` unreachable — still open

No caller passes `use_fast_model=True`; `nvidia/nemotron-3-nano-30b-a3b` is reachable only
from inside `llm/nvidia.py`. Either wire it into the router for cheap turns (§4's regex/fast
path is the natural home) or delete the plumbing. Left alone deliberately — that's a design
choice, not a defect.

### 7.6 Unrelated pre-existing test failure

`tests/test_autostart.py::TestRealKeyUntouched::test_real_registration_is_absent` fails on
this machine because FRIDAY **is** registered in `HKCU\...\CurrentVersion\Run` (pointing at
`scripts/friday_launcher.pyw`). The test asserts the suite never leaves a real registration
behind; it is tripping over a registration the user made deliberately. Environment state,
not a code defect — but the test should probably skip when autostart was enabled outside the
suite.

---

## 8. What to build next (revised order, replacing the draft's §9)

The draft's steps 1, 2, 4, 5 are done or moot. What remains, in the order that pays:

1. **Eval harness** (draft §7 — unchanged, still the prerequisite for everything else).
   20–30 fixed tasks: `routing/` (utterance → expected intent), `code_edit/` (file +
   instruction → expected result), `browser/` (page + instruction → expected DOM state).
   First use: re-run the `qwen2.5:3b` agent-loop cases from `docs/JARVIS_PHASE2_SPEC.md`
   against `qwen3:4b-instruct` — the fix loop scored 0/2 before and is the number that
   justified this whole migration.
2. **Schema-enforced intent classification** — pass the intent JSON schema in `format=`,
   not just `format="json"`.
3. **Regex fast path** for the top exact-match utterances, above the LLM call.
4. **DOM filtering** (draft §5.2, verbatim — it's right): interactive elements only, stable
   ref IDs, model returns an index. This is the gate for any real browser agency; a raw
   `inner_text` dump is not a browser agent.
5. **Editor write path with read-back** (draft §5.3, verbatim): Monaco `setValue` →
   clipboard paste → `keyboard.insert_text`, then read back and diff. Fall through on
   mismatch.
6. **Lesson memory, scoped** (draft §6 layers 2–3): only after the eval harness exists,
   because unverified lessons are poison; gate writes on verified success, prune below 50%
   success after 5 uses, retrieve by scope (max 5), promote ≥5-time winners into code.
7. **Fine-tuning: don't.** There is no fine-tune today and the draft's own Check 3 logic
   says base + good harness wins until layers 1–3 are exhausted.

---

## 9. Security posture (draft §8 — endorsed, status noted)

- Page content is data, never instruction — currently enforced only by prompt convention.
  When DOM filtering (§8.4) is built, strip/flag imperative text in extracted labels.
- Irreversible actions already confirm: `edit_file`, `browser_click`, `browser_type` carry
  `confirm=True`; spoken yes/no with a 25 s timeout, silence = no. Keep every new
  side-effectful tool behind the same flag.
- Personal facts from memory stay local by default. The switcher makes "local by default,
  cloud on request" a one-line policy; keep it that way when auto-escalation is ever added.
