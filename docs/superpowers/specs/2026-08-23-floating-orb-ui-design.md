# Floating Orb UI — Design

**Date:** 2026-08-23
**Status:** Approved, ready for implementation plan
**Scope:** Replaces `ui/main_window.py`. No changes to `intelligence/`, `skills/`, `core/`, `llm/`, or `memory/`.

## Problem

The current UI is a conventional 520×640 window with a status row, a log pane, and an input row. Two things are wrong with it:

1. It looks like a utility window, not an ambient assistant. The user wants a small floating presence that mostly just talks, and shows chat history only on demand.
2. It takes roughly 90 seconds to appear. `main_gui.py` constructs `container.stt` (a Whisper `Transcriber`) on line 59, *before* `window.show()` on line 60, so the app looks dead through the entire model load. This becomes far worse once the app runs on laptop startup.

## Decisions taken

| Question | Decision |
|---|---|
| Resting form | Morphing: small orb at rest, stretches to a pill with a live waveform when listening or speaking |
| Expanded form | The orb itself grows into a card. One object, never two |
| Collapse | A `▾` control in the card header returns it to the orb. Clicking away also collapses it, via `focusOutEvent`; if that proves unreliable for a `Qt.Tool` window on Windows, the `▾` remains the guaranteed path and click-away is dropped |
| Text input | Retained. History **and** a text box |
| Quitting | System tray icon with Show / Hide / Quit |
| Old UI | Replaced outright. No `--classic` fallback |
| STT load | Fixed as part of this work |

The "replace outright" decision was taken knowingly: the existing window was written by Manas (`6c9ec2b`) and modified by Maatrik (`1a34bf3`), and there will be no fallback if the orb misbehaves.

## Architecture

`MainWindow` becomes a frameless always-on-top widget with two visual modes and one animated transition between them.

Window flags: `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`. `Qt.Tool` keeps it out of the taskbar and Alt-Tab, which is correct for an ambient widget. `WA_TranslucentBackground` is required for genuinely rounded corners rather than rounded artwork on a square window.

### Components

Four units, each independently understandable. Splitting them is deliberate — a single class covering painting, animation, chat, dragging, and tray would be the same unmaintainable blob in a new shape.

**`OrbWidget`** — Paints the circle and the pill. Owns the state colour and the waveform animation. Knows nothing about chat or the event bus.
*Interface:* `set_state(name: str)`, `set_amplitude(level: float)`. *Depends on:* `STATE_COLORS` only.

**`ChatPanel`** — History list, text input, mic button, model-switch control. Emits Qt signals; does not publish to the event bus itself.
*Interface:* `append(role, text)`, signals `message_submitted(str)`, `mic_clicked()`, `model_toggle_requested()`. *Depends on:* nothing outside Qt.

**`MainWindow`** — Mode switching and geometry animation, dragging, position persistence, and all event-bus wiring. The only unit that knows the container exists.
*Interface:* the constructor keeps its existing parameter order — `MainWindow(event_bus, recorder, stt, wake_detector, container=None)` — but `stt` becomes optional (`stt=None`). `main_gui.py` **does** change, to pass `stt=None` and call `show()` before resolving `container.stt`; see the STT startup fix below. That file and `ui/main_window.py` are the only two files this work touches.

**`TrayController`** — `QSystemTrayIcon` plus its menu. Emits `show_requested`, `hide_requested`, `quit_requested`.

### Geometry and modes

| Mode | Size | Trigger |
|---|---|---|
| Orb | 44 × 44 | Idle |
| Pill | ~200 × 48 | State is LISTENING or SPEAKING |
| Card | ~310 × 340 | User clicks the orb |

Transitions animate `geometry` via `QPropertyAnimation`, 180 ms, `OutCubic`. The widget is one object throughout; no second window is ever created.

## Data flow

Unchanged, and deliberately so. The UI stays a pure view over the existing event bus.

```
user types / mic ──> UserInputEvent ──> (existing pipeline)
StateChangedEvent ──> OrbWidget.set_state()  ──> colour + mode
ResponseReadyEvent ─> ChatPanel.append()     ──> history bubble
```

`STATE_COLORS` is reused as-is, so state handling is not reinvented. The existing `_wake_word_loop`, `_do_listen`, and `shutdown` logic is carried over intact — it works and is not what the user asked to change.

**Model switching is preserved.** The current `_toggle_model` (NVIDIA ↔ Qwen, from Maatrik's dual-LLM work) moves into the card header as a compact control. Dropping it would silently remove a working feature.

### Position persistence

Saved to `QSettings("ULTRON", "orb")` on move. On restore, the position is clamped to the current `availableGeometry()` of the screens, so a monitor change or resolution change cannot strand the orb off-screen. Default on first run: bottom-right, inset 24 px.

## The STT startup fix

Today, `main_gui.py`:

```
line 57  wake_detector = WakeWordDetector()
line 59  window = MainWindow(..., container.stt, ...)   # blocks ~90s on Whisper
line 60  window.show()
```

`container.stt` is a lazy property that builds a `Transcriber`. Touching it in the constructor call blocks the Qt event loop before the first paint.

**Fix:** show the window first, resolve STT after.

1. `MainWindow` accepts `stt=None` and starts in the `STARTING` colour with the mic disabled.
2. `main_gui.py` calls `window.show()` before touching `container.stt`.
3. STT is built on a worker thread (`asyncio.to_thread`); on completion `window.set_stt(transcriber)` enables the mic and moves the orb to `IDLE`.

The orb becomes visible in well under a second. The mic is genuinely unavailable until STT loads, and the UI says so rather than silently failing — the amber `STARTING` colour is the existing vocabulary for exactly this.

## Error handling

- **Tray unavailable.** `QSystemTrayIcon.isSystemTrayAvailable()` can be false. If so, fall back to a right-click Quit menu on the orb and log a warning. Without this the app would be unquittable.
- **STT fails to load.** Orb goes to `IDLE` with the mic disabled and a one-line note in the card. Typing still works; a broken microphone must not cost the user text input.
- **Off-screen restore.** Covered by clamping above.
- **Wake-word engine absent.** Already handled by `WakeWordDetector` (prints `NO ENGINE AVAILABLE`). The UI shows the mic as click-to-talk only; it must not imply a wake word is listening when none is.

## Testing

Qt rendering is not meaningfully unit-testable headless, so tests target logic, not pixels:

- state name → colour mapping
- mode selection from state (idle → orb, listening/speaking → pill)
- position clamping against a simulated screen smaller than the saved position
- `ChatPanel.message_submitted` fires on Enter and on Send
- STT-pending → mic disabled; after `set_stt()` → mic enabled

Uses `pytest-qt` with `QT_QPA_PLATFORM=offscreen`. **`pytest-qt` is not currently installed** and must be added to the `dev` extra.

The existing 60 tests must continue to pass unchanged. Nothing outside `ui/` is touched, so any failure there is a real regression.

## Out of scope

Deliberately excluded — these are the other three subsystems from the same request and each needs its own spec:

- Barge-in ("stop" while speaking)
- Spotify playback and Chrome-tab web search
- Autostart on boot, always-on wake word, "bye bye" to dismiss

The tray icon and the collapse/hide path are built here in a way that the autostart work can reuse.

## Risks

1. **No fallback UI.** Replacing outright means a broken orb leaves no working window. Mitigated by keeping the pipeline untouched — `run.py --mode text` remains fully functional.
2. **Translucent frameless windows are platform-sensitive.** Behaviour under Windows compositing (and with multiple DPI scales) needs checking on the real machine, not assumed.
3. **Teammate conflict.** `ui/main_window.py` was last modified by Maatrik. A full rewrite will conflict hard with any in-flight work on that file.
