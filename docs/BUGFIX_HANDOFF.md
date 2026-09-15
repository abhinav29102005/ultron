# Bugfix handoff — double tabs, no web, two voices (2026-09-01)

Three user-reported bugs, investigated with evidence. Two share one root cause. State of
each is below. **All three are now closed** — see §3. Suite baseline before this session: 1125
passed + 1 known-irrelevant failure (`test_autostart` — trips over the user's real Run-key
registration; never fix, never count).

Run tests with `-o addopts=""` always:

```
.venv/Scripts/python.exe -m pytest tests/ -q -o addopts=""
```

---

## 1. "Can't reach the web" — ✅ FIXED AND VERIFIED

**Root cause (proven from logs/friday.log):** every agent turn since agent mode shipped
died with `'CachedLLM' object has no attribute 'complete_with_tools'`. The container wraps
every LLM in `CachedLLM` (`core/container.py:131`), and the wrapper proxied
`complete`/`stream` but not `complete_with_tools` — so agent mode **never ran once**, every
turn silently fell back to the classifier, and web questions were answered by the chat
model's own "I can't browse" disclaimer. The search stack itself was healthy (verified:
`WebSkill.search` returned 5 good results standalone).

**Fix (in tree):** `utils/cache.py` — explicit `complete_with_tools` pass-through
(deliberately never cached: a tool call is a decision to act, and a replayed decision acts
on a world that moved on) plus `__getattr__` delegation so the next method the switcher
grows cannot silently vanish behind the wrapper again.

**Verified:** `tests/test_cached_llm.py` (new, 5 tests — 3 were written first and failed on
the unfixed wrapper), and a live round trip through the *container's* wrapped LLM produced
a correct `open_website{url: https://www.youtube.com}` tool call on qwen3:4b-instruct.

## 2. "Opens tabs twice" + "two voices" — ✅ FIXED AND VERIFIED

One cause, two symptoms: **more than one copy of `main_gui.py` was running at once** (verified
via `Get-CimInstance Win32_Process`; the log also shows paired "Agent turn failed" lines
0.1–2 s apart — two processes answering the same utterance). Closing the orb hides it to
the tray rather than quitting, so every relaunch stacked another instance; each one heard
every wake word, opened its own tab, and spoke its own reply.

**Remediated:** all duplicate processes were killed (PIDs 24540, 20144, 20432, 21756 —
which §3.2 later established was *two* real instances plus their launcher stubs). Zero
FRIDAY processes were left running.

**Fix (wired in §3.1, verified live in §3.2):** `utils/single_instance.py` — a named Windows
kernel mutex (`Local\friday-agent-gui`). Kernel object, not a lockfile, on purpose: the
duplicates were killed with Stop-Process, and a lockfile survives its holder's death and
locks the user out; the OS releases a mutex however the holder dies. Fails open (guards
nothing, logs a warning) if the mutex cannot even be created. Off-Windows it degrades to
always-acquired. `tests/test_single_instance.py`: 6 passed, including the
dead-holder-does-not-wedge case via a subprocess that exits without releasing.

---

## 3. COMPLETED — all three bugs closed (2026-09-01)

### 3.1 Guard wired into `main_gui.py` — done

`SingleInstance` is acquired in `main()` after `QApplication` exists (so the dialog can
show) and held in a **module-level** `_instance_lock`. Both traps the handoff named are
observed: a local would be collected on the way out of `main()` and end the guard while
FRIDAY still ran, and nothing calls `release()` because `run()` ends in `os._exit(0)` —
the OS drops the mutex however the process dies.

A refused launch prints to stdout *and* shows a `QMessageBox`, because the autostart
launcher runs under `pythonw` with no console at all — a print alone is invisible, which
is how the duplicates went unnoticed.

### 3.2 Live verification — PASS, all three steps

Driven as real subprocesses (`scratchpad/live_guard_test.py`):

```
1. instance A started (1 real instance)
2. instance B while A holds the mutex:
     exit code 0
     "[FRIDAY] Already running - look for the orb or the tray icon."
     still 1 real instance
3. A killed -> instance C started normally (mutex not wedged)
   leftover processes: 0
VERDICT: PASS
```

**Counting correction, and it matters.** `.venv\Scripts\python.exe` is a launcher
trampoline: every launch produces **two** OS processes with identical command lines — a
4 MB / 1-thread stub and the real 589 MB / 48-thread interpreter as its child. Counting raw
processes doubles every instance. So the "four copies" in §2 was **two real instances**, not
four — which is exactly "tabs open twice" and "two voices", and fits the symptoms better
than four would have. Any future process count must exclude processes that are the parent
of another matching process.

### 3.3 Full suite — 1136 passed

Exactly the predicted number, plus the one known `test_autostart` failure. No regressions.

### 3.4 Original symptoms re-tested — all three resolved

**Tabs no longer double, and the routing was never at fault.** Inspected (not executed)
what each utterance plans, through both paths:

| Utterance | Classifier | Agent |
|---|---|---|
| "open youtube" | 1 × `open_website` | 1 × `open_website` |
| "open youtube and search for mkbhd" | 1 × `open_website` (not split) | 1 × `open_website` |
| "what are today's top news stories" | `web_lookup` | `research` |

Exactly one site-opening action per utterance from either path, and only one path runs per
turn (`try_agent_turn` returns None to fall back, never both). The doubling was purely the
duplicate instances. The suspects the handoff listed — a classifier split, or the agent
acting *and* answering — are both ruled out by measurement.

**Web works.** A real agent turn on the live container:

```
agent turn returned: AgentResult(text='The time is 12:05 PM.',
                                 tools_used=['get_time'], steps=1, hit_budget=False)
new CachedLLM errors in the log: 0
new "Agent turn failed" lines:   0
```

This is the first time agent mode has actually run in this app. The news query above
reaching the `research` tool is the same fix visible from the other side.

**Two voices cannot recur within one instance** — and this needed no code change.
`speech/text_to_speech/tts_pipeline.play_audio` already calls `_player.stop()` before
synthesising and guards the result with an epoch, so a new utterance supersedes an
in-flight one rather than layering under it. The reminder scheduler (the handoff's untested
suspect) speaks through that same path, so it cannot overlap a reply. Two voices required
two processes with two independent audio players — which is what was happening.

### 3.5 Optional hardening — deliberately NOT done

`run.py` and `main.py` still have no guard. Following the handoff's own scoping: the
collision that actually bit was GUI-vs-GUI (autostart plus a manual launch), and a shared
mutex across every entry point would break a legitimate workflow — running
`run.py --mode text` to test something while the GUI is up. Worth revisiting only if
terminal-mode duplicates turn out to bite in practice.

## 4. Not committed

Everything above is uncommitted working-tree state, ON TOP of the also-uncommitted
three-feature batch (document/excel/screenshot skills + review fixes — see
`docs/JARVIS_FEATURES_V2.md` §4b). The user's commit style: short label message, one
commit, no Co-Authored-By trailer, ask before naming. Suggested when everything is green:

```
feat: document, excel and screenshot skills; fix agent tools passthrough and single instance
```

(or split in two: features / fixes — ask the user.)
