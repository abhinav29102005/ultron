# ULTRON Phase 2 — Code-Fixing Agent, Better Brain, Real Takeover

> **STATUS: IMPLEMENTED AND VERIFIED.** W6, W7 and W8 are built and tested;
> the fix loop passes its live acceptance 3/3 on the cloud model. Suite: **1024 passing**.
> Jump to [§8 Implementation results](#8-implementation-results-verified-live) for what
> actually happened, including four bugs found only by running it.

**Purpose:** a self-contained handoff for an AI model (or engineer) with no prior context.
Phase 1 (see `docs/ULTRON_UPGRADE_SPEC.md`) built the tool-calling agent loop, screen OCR,
file read/write, browser/desktop control, notes and reminders. This document covers the three
problems the user still hits, diagnoses each **with live evidence gathered on this machine**,
and specifies the fixes.

Repo: `ultron` (Windows 11, Python 3.13, venv at `.venv/`). Suite: **952 passing**
(`.venv/Scripts/python.exe -m pytest -q -o addopts=""`; the one failure,
`test_autostart.py::TestRealKeyUntouched`, is environmental and pre-existing — ignore it).

**The implementer MUST verify by running, not only by unit tests.** The user asked for this
explicitly. §5 documents the live harness used to gather the evidence below; reuse it.

---

## 0. Live diagnosis (evidence, gathered 2026-08-31 on the user's machine)

| Probe | Result |
|---|---|
| Agent loop, `"fix the bug in <full path to buggy.py>"`, qwen2.5:3b, 3 runs | **3/3 failed identically**: zero tool calls, final answer was the literal word `"LOOKING"` — parroted from the system prompt's "answered by LOOKING" line |
| Same utterance, simplified system prompt, 3 runs | 3/3 now call a tool — but the **wrong** one (`get_active_window`, despite being handed the full path) |
| NVIDIA NIM fallback (`meta/llama-3.1-8b-instruct`, the configured default) | **HTTP 410 Gone — the model has been retired.** The cloud fallback is silently dead |
| Live NIM model list (with the user's key) | 83 models alive; `meta/llama-3.1-*` absent; strong tool-capable options present (see §3) |
| `curl localhost:9222/json/version` while the user's Chrome runs | **Nothing listening.** A normally-started Chrome exposes no CDP; attach is impossible |
| Tool registry / code_skill grep | **No `run_command` and no `edit_file` exist.** The model literally cannot run code or make a targeted edit — whole-file `write_file` is its only mutation |
| Machine | 15.7 GB RAM, Intel UHD (no CUDA), Ollama serving only `qwen2.5:3b` + `qwen2.5vl:3b` |

Read these together and the user's three complaints stop being mysterious:

1. "Takes a lot of tries, then pastes code in chat" → the 3B model can't drive the current
   prompt (parrots it 3/3), and even on track it has **no tool to run code and no tool to make
   a targeted edit**, so pasting into chat is all it can do.
2. "Can't open folders unless I'm very specific" → mostly model quality (see the wrong-tool
   probe above); the folder skills themselves work when called with sane arguments.
3. "Can't take control of my already-open browser" → correct diagnosis by the user: CDP is not
   exposed on a normally-started Chrome, and ULTRON has no flow to fix that.

---

## 1. W6 — The code-fixing agent (issue 1, the big one)

**Goal:** "fix the error on my screen" ends with the file *changed on disk, verified by
running it*, visible immediately in VS Code — not with code pasted into chat.

### 1.1 Why chat-pasting is currently forced

- `write_file` (the only mutation) demands the **complete new file contents**. A small model
  will not faithfully reproduce a 200-line file to change one line, and it knows it — so it
  outputs a snippet in prose instead.
- There is **no way to run anything**. The user's requested loop — *run the candidate fix until
  the outcome is right, then apply* — is unimplementable today.
- The agent system prompt (`intelligence/agent_loop.py`, `SYSTEM_PROMPT`) is tuned for
  1–3 spoken sentences and its "LOOKING" phrasing is toxic to the 3B model (evidence above).
- `agent_max_steps = 6` (config/settings.py) cannot hold a read→edit→run→check→re-edit→confirm
  chain.

### 1.2 New tool: `edit_file` (targeted replace — the Claude Code model)

Add to `skills/code_skill.py` + `intelligence/tool_registry.py` + router intent `edit_file`.

- Arguments: `path`, `old_text`, `new_text`. Replace **exactly one occurrence**; refuse
  (with a readable message the model can act on) when `old_text` is not found or matches more
  than once — ambiguity must bounce back to the model, never guess.
- Keep the `.ultron-bak` backup behaviour from `_write` (see `BACKUP_SUFFIX`).
- `confirm: False` **when part of a verified fix loop** (§1.4 applies the confirmed gate at the
  loop level instead); standalone `edit_file` keeps `confirm: True`. Simplest correct
  implementation: keep `confirm: True` on the tool and let the fix-loop tool (§1.4) be the
  unconfirmed path, since the loop confirms once at the end.
- Why this beats whole-file writes for a voice agent: the model only has to produce the
  changed lines, which even a 4B model can do reliably; the diff is small enough to *speak*
  ("I changed line 5 to guard against an empty list — apply it?").

### 1.3 New tool: `run_command` (the verify half)

- Arguments: `command` (string), optional `cwd`, optional `timeout_seconds` (cap ≤ 60).
- **Allowlist, not free shell.** First word must be one of:
  `python`, `py`, `pytest`, `node`, `npm` (extendable in settings as
  `AGENT_RUN_ALLOWLIST`). Refuse anything else with a message, the same fail-soft style as
  `DesktopSkill._normalise` — that allowlist pattern and its tests are the template.
- Run via `asyncio.create_subprocess_exec` (never shell=True), capture stdout+stderr,
  truncate to ~4000 chars, always pass
  `creationflags=CREATE_NO_WINDOW` — **console-window hygiene is enforced by
  `tests/test_no_console_windows.py`; extend that file for this spawn site** (never OR with
  `DETACHED_PROCESS`; that combination is documented-ignored and was a real shipped bug).
- Return exit code + output as text. Non-zero exit is a *result*, not an error — the model
  reads it and iterates.
- `confirm: False` for allowlisted interpreters running a file that exists; this is the
  read-side of the loop. (A wrong `python evil.py` still only runs what is already on disk.)

### 1.4 The fix loop (shadow-copy protocol)

The user's requested flow, made safe. Implement as *prompt protocol + one helper tool*, not a
hard-coded pipeline — the agent loop already supports chains:

1. `read_screen_text` / `clipboard` → get the exact error. `get_active_window` → often names
   the file and project directly (VS Code titles are "file - folder - Visual Studio Code").
2. `read_file` the real file.
3. **`copy_to_shadow(path)`** (new, tiny, on CodeSkill): copies the file to
   `<scratch>/ultron-fix/<name>`; returns the shadow path. All candidate edits and runs happen
   on the shadow, so nothing the user has open changes until verified.
4. `edit_file` on the shadow → `run_command("python <shadow>")` → read output → repeat until
   the error is gone / expected output appears (the model judges; the transcript holds both).
5. One spoken confirmation: *"Fixed — the average function now returns 0 for an empty list.
   Apply the change to buggy.py?"* → on yes, apply the same `old_text/new_text` edit to the
   real file (`edit_file`, its confirm satisfied by this exchange).
6. VS Code integration, the cheap and correct way: **editing the file on disk IS controlling
   VS Code** — it auto-reloads unmodified open files. Additionally call
   `code --goto <path>:<line>` via `run_command` (add `code` to the allowlist) so the fixed
   line is on the user's screen. Do NOT attempt UIA/keystroke editing of the VS Code buffer;
   it's strictly worse than disk edits.

### 1.5 Loop budgets

- Raise `agent_max_steps` default to **12** (config + `DEFAULT_MAX_STEPS`); the fix loop needs
  read + shadow + (edit+run)×3 + apply ≈ 10. Keep the wall-clock at 120s.
- Add `AGENT_FIX_MAX_ITERATIONS` (default 4) mentioned in the prompt: after 4 failed
  edit→run rounds, stop and tell the user what was tried. Prevents a weak model burning the
  whole budget re-trying one wrong idea.

### 1.6 Prompt rewrite (do this regardless of model)

Evidence: the current prompt makes qwen2.5:3b answer `"LOOKING"` 3/3; a simplified prompt got
tools called 3/3. Rules for the rewrite of `SYSTEM_PROMPT` in `intelligence/agent_loop.py`:

- No metaphors, no emphatic capitalised words (the model quotes them back).
- State the fix protocol as a numbered recipe ("To fix a bug: 1. read_file … 2. …").
- Explicit negative: "Never paste code into your answer. Changes go through edit_file."
- Keep the speech-style rules (short sentences, no markdown) — they work.
- Keep prompts per-capability short; a 3B model follows the *first* instruction it matches.

---

## 2. W7 — Folder opening + argument quality (issue 2)

Live probes show the folder machinery itself is fine through the agent path
(`"open my downloads folder"` → `open_folder` → opened, first try). The pain is the model:
vaguer phrasings pick wrong tools or wrong arguments (`get_active_window` for a fix request
3/3 with the simple prompt). Two fixes:

### 2.1 Widen `FolderSkill` resolution (small, do it anyway)

`skills/System.py` `KNOWN_FOLDERS` + `_resolve_path`: add fuzzy matching — case-insensitive,
singular/plural ("download" vs "downloads"), and a recursive one-level scan of `~/Desktop` and
`~` for a folder whose name contains the spoken words (reuse the scoring approach of
`ApplicationSkill._find_start_menu_shortcut`, which solved the identical problem for apps).
Tests first, in the existing `tests/test_system_skills.py` style.

### 2.2 The model recommendation (this is the real fix)

**Do NOT use Gemma.** The user suggested "gemma 8B"; Gemma models in Ollama do not support
function calling (`ollama` raises "does not support tools", which our `QwenLLM` correctly
surfaces as `ToolsUnsupportedError` → silent fallback to the old classifier — the agent would
just turn itself off). Verify with one `complete_with_tools` probe before dismissing, but as
of knowledge cutoff Gemma-family = no tools in Ollama.

With 15.7 GB RAM, CPU-only:

| Option | Why / why not |
|---|---|
| `qwen3:4b` (local) | Tool-capable, ~2.6 GB, noticeably better instruction-following than 2.5-3b at similar latency. **First choice for local.** |
| `qwen3:8b` / `llama3.1:8b` (local) | Materially smarter, ~5 GB, but CPU-only decode will feel slow in conversation. Offer via `utils/model_picker.py` (exists, already tiers by RAM/VRAM). |
| **Fix the dead NIM default (mandatory)** | `NVIDIA_MODEL` defaults to `meta/llama-3.1-8b-instruct`, which now returns **410 Gone**. Change the default in `config/settings.py` (both `nvidia_model` and `nvidia_fast_model`) to a live, tool-capable NIM model — candidates confirmed alive with the user's key: `mistralai/mistral-large-2-instruct`, `nvidia/llama-3.1-nemotron-70b-instruct`, `mistralai/mistral-7b-instruct-v0.3`. **Probe tool-calling live before committing to one** (one `complete_with_tools` call, pattern in §5), then also verify `is_available`/preflight paths. |
| Hybrid (recommended end state) | `LLM_PROVIDER=nvidia` for the agent brain — cloud latency ≈ 1–2 s beats 8B-on-CPU — with qwen local as the offline fallback the switcher already provides. |

Also add a startup preflight check for NIM: `utils/preflight.py` deliberately skips the network
probe for NVIDIA ("a bad key surfaces on the first message") — but a **retired model** is
exactly the failure that deserves one cheap probe at boot, because it otherwise looks like
ULTRON misbehaving. Add a single `models` list call when `LLM_PROVIDER=nvidia`, warn-only.

### 2.3 Ship `pull` instructions

`scripts/bootstrap.py` already pulls models; extend it (and the README) with the chosen local
model. One command for the user: `ollama pull qwen3:4b`, then `QWEN_MODEL=qwen3:4b` in `.env`.

---

## 3. W8 — Taking over the already-open browser (issue 3)

**Diagnosis, confirmed live:** the user's Chrome is running (2 processes) with **nothing on
port 9222**. Chrome only exposes CDP when *started* with `--remote-debugging-port`; there is no
way to attach to one started normally. `BROWSER_ATTACH=true` therefore fails today with the
hint message in `skills/browser_skill.py::_ATTACH_HINT`, and ULTRON falls back to its own
logged-into-nothing Chromium — which is the "it can't take control" experience.

### 3.1 The relaunch flow (main fix)

New behaviour in `BrowserSession._connect` when `attach=True` and the CDP connect fails:

1. Detect whether Chrome is running (`tasklist /FI "IMAGENAME eq chrome.exe"` — with
   `CREATE_NO_WINDOW`, see the `media_skill.py::_spotify_window_title` pattern).
2. If yes: this is a **confirmed** action (it closes the user's windows for a few seconds):
   speak *"To control your Chrome I need to restart it with remote control enabled — your tabs
   will come back. Do it?"* Route through the same confirm channel the agent loop already has
   (`AgentLoop._ask`); mechanically this means the connect path returns a structured
   "needs-relaunch" signal that the skill turns into a confirmed `chrome_enable_control` tool
   call, rather than the session doing side-effects behind the tools' back.
3. On yes: `taskkill /IM chrome.exe` (graceful first: try `--` window close via pywinauto,
   then /F after a grace period), then relaunch the user's real Chrome —
   `%ProgramFiles%\Google\Chrome\Application\chrome.exe` —
   with `--remote-debugging-port=9222 --restore-last-session` and their default profile.
   `--restore-last-session` brings their tabs back; their cookies/logins are in the profile and
   survive untouched.
4. Poll `http://localhost:9222/json/version` (≤10 s) then `connect_over_cdp` as now.
5. Never do any of this when Chrome is *not* running — just launch it with the flag directly
   (no confirmation needed beyond the tool's own).

### 3.2 Flip the experience

- Once 3.1 exists, change `browser_attach` default to **True**: "control the browser" should
  mean *the user's* browser. Owned-Chromium stays as the fallback when the user declines the
  relaunch.
- Add `browser_screenshot` (page.screenshot → temp PNG → reuse OCR if needed) — cheap and
  makes the agent's read-act loop on real pages far more robust than `inner_text` alone.
- The UIA path (`focus_window` + `press_keys`) already covers "scroll down / press enter in
  whatever is open" without CDP; mention it in the agent prompt as the fallback for
  non-browser windows, not a browser strategy.

### 3.3 Honest limitation to state in the prompt

ULTRON must *say* when it is in owned-Chromium (logged into nothing) vs the user's Chrome.
A silent wrong-browser action ("I posted it" — into a logged-out browser) is worse than
asking. One sentence in the system prompt + the `browser_open` result naming which mode.

---

## 4. Registry/loop touch-list (so nothing is missed)

- `intelligence/tool_registry.py`: add `edit_file`, `run_command`, `copy_to_shadow`,
  `chrome_enable_control`, `browser_screenshot`. Router intents for each
  (`intelligence/router.py` — the "Agent-only intents" block is where they belong; keep them
  OUT of `IntentDetector.VALID_INTENTS`, same reasoning as the existing comment there).
- `tests/test_agent_tools.py::test_the_core_capabilities_are_all_exposed` — extend the list;
  `test_destructive_tools_require_confirmation` — `chrome_enable_control: confirm=True`,
  `edit_file: confirm=True` (standalone), `run_command`/`copy_to_shadow`/`browser_screenshot`
  unconfirmed.
- `ToolDispatcher` needs no changes (tools→Task is generic); `fixed=`/`aliases=` cover naming.
- `config/settings.py`: `agent_max_steps` 6→12, `AGENT_RUN_ALLOWLIST`, `AGENT_FIX_MAX_ITERATIONS`,
  new NIM default model.

---

## 5. Verify-by-running is mandatory (the user asked for exactly this)

Unit tests alone repeatedly lied this session; every real bug below was found only live:
the `.or_()` DOM-order bug, the Ollama dict-vs-string transcript crash, the dead NIM model,
the "LOOKING" parrot. **After each workstream, run the real loop against real Ollama.**

Harness pattern (used for all evidence in §0; adapt paths):

```python
# scratchpad/live_harness.py — real router+executor+skills, no audio/GUI
import asyncio, sys; sys.path.insert(0, r"C:\Users\HP\Desktop\ultron-main")
from config.settings import Settings
from intelligence.agent_loop import AgentLoop
from intelligence.tool_dispatcher import ToolDispatcher
from intelligence.router import TaskRouter
from intelligence.executor import Executor
class C:
    def __init__(s_, s, llm):
        s_.settings=s; s_.llm=llm; s_.router=TaskRouter(container=s_)
        s_.executor=Executor(s_); s_.web_skill=None; s_.chat_skill=None; s_.state=None
async def main():
    s = Settings.load()
    from llm.qwen import QwenLLM   # or llm.nvidia import NvidiaLLM
    llm = QwenLLM(s)
    async def confirm(p): print("CONFIRM:", p); return True
    loop = AgentLoop(llm=llm, dispatcher=ToolDispatcher(C(s, llm)), confirm=confirm, max_steps=12)
    r = await loop.run(sys.argv[1])
    print("tools:", r.tools_used, "| steps:", r.steps, "| budget:", r.hit_budget)
    print("ANSWER:", r.text)
asyncio.run(main())
```

Definition of done for W6, run at least 3 times each on the chosen model:

- Seed file `buggy.py` (`return total / len(numbers)` on `[]` → ZeroDivisionError, print at
  module level). Utterance: `fix the bug in <path>`.
- PASS = the loop **ran** the shadow at least once, the final file on disk handles the empty
  list, a `.ultron-bak` exists, the fix was confirmed once, and **no code appears in the spoken
  answer**.
- Repeat with the error on screen instead of a path given: open the traceback in a window,
  utterance "fix the error on my screen" → must go read_screen_text/get_active_window first.
- W8 PASS = with the user's Chrome open normally, "open youtube in my browser" ends with
  YouTube in *their* Chrome after one spoken relaunch confirmation; second run needs no
  relaunch (CDP already up).

Notes for the harness: run scratch scripts from the session scratchpad, never the repo;
`data/notes.json`/`data/reminders.json` created by live runs must be deleted afterwards
(gitignored but keep the tree clean); a stray `h2.py` in `%TEMP%` shadows the real `h2`
package — put scripts in a clean subfolder.

---

## 6. House rules (unchanged, abbreviated — full version in Phase 1 spec §6)

TDD with failing-test-first, bug-docstrings on test files; no network in tests; every Windows
spawn gets `CREATE_NO_WINDOW` (extend `tests/test_no_console_windows.py`); spoken outputs are
1–3 plain sentences; budgets on everything; commits are short labels, batched, **no
Co-Authored-By trailers** (sole author `Golden-alt933`); ULTRON must keep working with Ollama
down and offline; mutation-test any safety property you add (allowlists, confirm gates) —
pattern: `tests/test_control_skills.py` + the mutation run in the Phase 1 history.

## 7. Milestones

| # | Contents | Done when |
|---|---|---|
| M1 | Prompt rewrite + max_steps 12 + NIM default fixed (+ NIM boot probe) | "fix the bug in <path>" calls read_file ≥2/3 on local; NIM answers again |
| M2 | `edit_file`, `run_command`, `copy_to_shadow` + registry/tests | unit green + both W6 live PASS criteria |
| M3 | Model story: qwen3:4b pulled & defaulted (or hybrid NIM), bootstrap/README updated | probes ≥2/3 across 3 fix-loop runs without manual retries |
| M4 | Chrome relaunch flow + attach default + browser_screenshot | W8 live PASS |
| M5 | FolderSkill fuzzy matching | "open my project folder", "open download" both work live |

Suite must stay green throughout (952 + whatever you add).

---

## 8. Implementation results (verified live)

Everything below was run on this machine against real Ollama, real NVIDIA NIM and a real
Chromium. Unit tests alone are not evidence — four of the bugs here were invisible to them.

### What shipped

| Workstream | Files | Tests |
|---|---|---|
| W6 `edit_file`, `run_command`, `copy_to_shadow` | [skills/code_skill.py](../skills/code_skill.py) | `tests/test_fix_loop_tools.py` (25) |
| W6 prompt rewrite, step budget 6→12, repeat guard | [intelligence/agent_loop.py](../intelligence/agent_loop.py) | `tests/test_agent_loop.py` |
| W6 agent token budget + NIM retry | [llm/nvidia.py](../llm/nvidia.py) | `tests/test_llm_tool_calling.py` |
| W7 folder resolution | [skills/System.py](../skills/System.py) | `tests/test_folder_resolution.py` (21) |
| W7 NIM model swap + boot probe | [config/settings.py](../config/settings.py), [utils/preflight.py](../utils/preflight.py) | `tests/test_preflight.py` |
| W8 Chrome takeover | [skills/chrome_takeover.py](../skills/chrome_takeover.py), [skills/chrome_control_skill.py](../skills/chrome_control_skill.py) | `tests/test_chrome_takeover.py` (12) |
| W8 `browser_screenshot`, attach on by default | [skills/browser_skill.py](../skills/browser_skill.py) | `tests/test_control_skills.py` |

### W6 live acceptance — the fix loop

Seeded `buggy.py` (`total / len(numbers)` on `[]`), utterance `fix the bug in <path>`.
PASS requires all of: ran the shadow, changed the real file, the changed file executes
cleanly, a `.ultron-bak` exists, and no code in the spoken answer.

| Model | Result |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | **3/3 PASS** — 32–52 s, 7–8 tool calls each |
| `qwen2.5:3b` | 0/2 — cannot drive the loop (see below) |

A passing transcript: `read_file → copy_to_shadow → read_file → edit_file → run_command →
read_file → edit_file`. It edits the copy, runs it, reads the traceback, fixes it, then applies
the change to the real file. Spoken answer: *"I fixed the bug by adding a check for an empty
list… Now it returns 0 instead of causing a division by zero error."* — no code, as required.

### Bugs found only by running it

1. **`"LOOKING"`** — the old prompt's capitalised emphasis was quoted back verbatim by
   qwen2.5:3b, 3/3, with zero tool calls. Prompts for small models cannot contain shouted
   words. Rewritten as a numbered recipe.
2. **Truncation mid-thought** — `llm_max_tokens=256` is tuned for a spoken sentence. A
   reasoning model spends that budget thinking and gets cut off; the loop returned the
   half-finished reasoning as its final answer, indistinguishable from a model choosing to
   stop. Added `AGENT_MAX_TOKENS=2048`.
3. **Six identical `list_directory` calls** — a model that repeats a call verbatim is stuck,
   and every repeat returns the same result, so nothing pushes it to change course. It burned
   all 12 steps and delivered nothing. Added a repeat guard: after two identical consecutive
   calls the loop answers with a nudge instead of running the tool again.
4. **NIM 500s** — three identical runs, two died on transient `Internal server error`. Added a
   bounded retry (3 attempts) for 5xx only; 410 and 404 are permanent and are not retried.

### The model story (§2.2 corrected by evidence)

The spec's suggested replacements were wrong — **all of them 404**. A sweep of all 83 listed
models with the user's key found only **14 invocable**; the rest return
`404 Function not found` (not provisioned for this key) or `410 Gone` (retired).

Of the 14, five do tool calling correctly. Measured, 3 utterances each:

| Model | Avg latency | Tool choice |
|---|---|---|
| **`nvidia/nemotron-3-super-120b-a12b`** | **1.94 s** | 3/3 correct |
| `openai/gpt-oss-120b` | 1.92 s | 3/3 correct |
| `nvidia/nemotron-3-nano-30b-a3b` | 2.58 s | 3/3 correct |
| `openai/gpt-oss-20b` | 2.77 s | 3/3 correct |

`nemotron-3-super` is now the default (`nvidia/nemotron-3-nano-30b-a3b` for the fast path).
Preflight now checks at boot that the configured model still exists — the exact failure that
had gone unnoticed.

**Gemma was correctly ruled out**: no function calling in Ollama, so the agent would silently
disable itself. **qwen2.5:3b cannot do this work** — confirmed 0/2 on the fix loop even after
the prompt rewrite. The recommendation is `LLM_PROVIDER=nvidia`.

### W7 live results

| Phrase | Before | After |
|---|---|---|
| `download` | `~/download` (missing) | `~/Downloads` |
| `my downloads folder` | `~/my downloads folder` | `~/Downloads` |
| `ultron agent` | `~/ultron agent` (empty stub) | `~/Desktop/ultron-main` |

The last one needed a second fix: the user has an empty leftover `~/ultron agent` that beat the
real project on an exact-name match. Emptiness now outweighs one grade of name match — a folder
with nothing in it is not the project someone means. A *populated* exact match still wins.

### W8 live results

Confirmed the diagnosis on the running system: Chrome up, **nothing on port 9222**, so attach
could never have worked. The takeover now detects that, finds the real Chrome, and **asks**:
*"To control your Chrome I need to restart it with remote control switched on. Your tabs will
come back. Shall I?"* — verified live that it does **not** touch the browser without approval.

The restart itself was **not executed live**, deliberately: it closes the user's open tabs, and
nobody asked for that during this session. The kill/launch mechanism is covered by unit tests
with injected fakes. First real use will exercise it.

### Still open

- **`qwen3:4b`** — pulling at the time of writing (2.4 GB, slow link). Once present, set
  `QWEN_MODEL=qwen3:4b` for a better offline fallback. NIM is the recommended path regardless.
- **The live restart path** (above).
- **W4 connectors / Instagram** — unchanged from Phase 1; still needs a Meta app and OAuth.
