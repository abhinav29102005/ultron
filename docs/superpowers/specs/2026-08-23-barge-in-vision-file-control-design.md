# Barge-in stability, screen vision, and file/app control

Date: 2026-08-23
Status: approved

Three independent changes to FRIDAY, sharing one release.

1. Interrupting speech must not crash or lag the assistant.
2. FRIDAY can look at the screen on request, and its own window is invisible to screen sharing.
3. FRIDAY can open applications, files and folders, and find files by name.

---

## 1. Barge-in stability

### Symptom

Interrupting FRIDAY mid-sentence prints a PortAudio *input overflow*, the app
lags for several seconds, and then dies.

### Root causes

Five defects on one failure path.

**C1 — cross-thread stream close.** `Player.play()` blocks inside
`stream.write()` on a worker thread. `stop_audio()` runs on the Qt thread and
calls `Player.stop()`, which calls `stream.stop()` and `stream.close()` on the
stream the worker is still writing to. Closing a PortAudio stream while another
thread is inside a blocking write is undefined behaviour, and is the hard crash.

**C2 — global player swap.** `play_audio()` and `stop_audio()` both rebind the
module-global `_player`. After an interrupt the previous worker still holds a
reference to the old `Player` and keeps writing into a stream that nothing owns.

**C3 — unbounded capture queue.** `Recorder.audio_queue` is an unbounded
`queue.Queue` filled by the PortAudio callback. Only `Recorder.listen()` drains
it. While FRIDAY is thinking or speaking nobody drains it, so it grows at
roughly sixteen blocks a second. The next `listen()` then runs the Silero VAD
once per stale block before reaching live audio. That is the lag.

**C4 — non-idempotent recorder.** `Recorder.start()` does not check for an
existing stream, so a second call opens a second input stream on the same
device. `Recorder.stop()` never sets `self.stream = None`, so a second call
closes an already-closed stream.

**C5 — fake wake-word handshake.** `MainWindow._pause_wake_word()` calls
`WakeWordDetector.stop()`, which only sets a `threading.Event`, and then returns
immediately. The detector's stream is closed later, in the `finally` of
`_detect_porcupine`, on another thread. The recorder therefore opens its input
stream while the detector's is still open. Two input streams on one device is
what PortAudio reports as an input overflow.

### Design

**`speech/audio_bus.py` (new).** Owns microphone arbitration.

- `MicLock` — a re-entrant lock plus a `closed` event. Any component that opens
  an input stream acquires it and sets `closed` only after its stream is
  actually closed.
- `acquire_mic(timeout)` context manager. Raises `MicBusy` on timeout rather
  than opening a second stream.
- Single process-wide instance, `MIC`.

**`WakeWordDetector`.** `stop()` keeps setting the stop event, and gains
`wait_closed(timeout)` which blocks until the detect loop's `finally` has run.
The stream open/close is wrapped in `MIC`.

**`Player`.** Gains `_lock` and `_epoch`.

- `play()` snapshots the epoch on entry and checks it every chunk. It owns its
  stream for the whole call and closes it itself, in its own `finally`.
- `stop()` takes the lock, increments `_epoch`, sets `is_playing = False`, and
  calls `stream.abort()` to drop the buffered tail so the interrupt is audible
  at once. It never calls `close()`.
- Result: a stream is only ever closed by the thread that opened it. C1 and C2
  are structurally impossible, not merely unlikely.

**`tts_pipeline`.** One process-lifetime `Player`. `play_audio()` and
`stop_audio()` both act on it; neither rebinds it.

**`Recorder`.**

- `audio_queue` becomes `maxsize=64`. The callback drops the oldest block when
  full, so the queue cannot grow without bound (C3).
- `flush()` drains the queue and clears both buffers. `listen()` calls it on
  entry, so a listen always begins on live audio.
- `start()` returns early if a stream is already open; `stop()` sets
  `self.stream = None` and tolerates repeat calls (C4).
- The stream lifetime is wrapped in `MIC`.

**`MainWindow`.** `_pause_wake_word()` calls `stop()` then
`wait_closed(timeout=2.0)`, so the handshake is real (C5).

**Turn cancellation.** `Assistant` keeps a reference to the task running
`_handle_user_input`. `interrupt()` cancels it, so an interrupted question does
not deliver its answer several seconds later. Mic click and wake word both call
it before starting a new capture.

### Testing

`tests/test_barge_in.py`, with fakes for `sounddevice`:

- `stop()` during a `play()` never closes the stream from the calling thread.
- `play()` after `stop()` exits within one chunk.
- A full queue drops the oldest block and keeps `qsize()` at the cap.
- `start()` twice opens one stream; `stop()` twice raises nothing.
- `wait_closed()` returns only after the detect loop's `finally`.
- A hundred interleaved play/stop cycles across threads leave no stream open.

---

## 2. Screen vision, hidden from screen share

### Capture

`vision/screen_capture.py`. `mss` grabs the monitor under the cursor,
downscales the long edge to at most 1280px, and encodes JPEG at quality 75.
A 3B vision model gains nothing from a raw 4K PNG, and the smaller payload
keeps latency usable on CPU.

### Hiding

`vision/screen_hider.py`. `SetWindowDisplayAffinity(hwnd,
WDA_EXCLUDEFROMCAPTURE)` where the affinity constant is `0x00000011`, available
from Windows 10 2004 onwards.

The window stays fully visible on the physical display and is removed from
every capture path: Google Meet, Zoom, Teams, OBS, BitBlt, and DWM duplication.
This also means FRIDAY's own capture never contains FRIDAY.

Applied to the orb window and each child popup. Re-applied from `showEvent`
because Qt can recreate a native handle when window flags change. On any
platform other than Windows, and on Windows builds older than 2004, the call
is skipped and logged once — vision still works, the window is merely visible
to a screen share.

### Query

`skills/vision_skill.py`, routed from two new intents.

- `screen_query` — "what's on my screen", "help me with this", "what does this
  error mean".
- `screen_read` — "read this", "what does that say".

Capture, then `ollama.chat(model=VISION_MODEL, messages=[{role, content,
images:[jpeg]}])`, then speak the answer.

`VISION_MODEL` is a new setting, default `qwen2.5vl:3b`, deliberately separate
from `QWEN_MODEL` so the text path is unaffected. When the model is not
present the skill returns the exact `ollama pull` command instead of raising.

Capture happens only when an utterance routes to this skill. There is no
background sampling.

### Testing

`tests/test_vision.py`: capture returns non-empty JPEG bytes and respects the
size cap; the skill's prompt carries the image; a missing model produces the
pull instruction rather than an exception; `screen_hider` is a no-op that logs
rather than raising off-Windows.

---

## 3. File and application control

Extends the existing `ApplicationSkill` and `FolderSkill`. A full computer-use
driver was considered and rejected: a much larger and less reliable surface
than the request needs.

`skills/file_skill.py` supports three actions.

- `open` — an application, a file, or a folder, by path or by name.
- `find` — locate a file by fuzzy name match.
- `create` — make a folder.

Search covers Desktop, Documents, Downloads, Pictures, Videos and Music, to a
depth of four, skipping `AppData`, `node_modules`, `.git`, `__pycache__`,
`.venv` and hidden directories. Matching is `difflib` ratio on the stem, with
substring hits ranked first. The best match is opened; near-ties are reported
so the user can choose.

Deletion, moving and renaming are out of scope. A misheard word must not be
able to destroy data on a voice-triggered path.

Relative paths resolve under the user's home directory, never the working
directory. Absolute paths are permitted; a resolved path that escapes the home
directory without having been given as absolute is refused.

`ApplicationSkill.APP_ALIASES` gains `claude`. Unknown application names fall
back to a Start Menu `.lnk` scan of both the per-user and machine-wide
Programs folders, so an app is launchable before anyone adds an alias for it.

### Testing

`tests/test_file_skill.py` against a temporary tree: exact and fuzzy find;
excluded directories are never walked; depth cap holds; escaping the home
directory is refused; open dispatches per platform; create is idempotent.

---

## Hardening pass

Three adversarial reviews ran against the implementation. What they found, and
what changed as a result. Regressions are in `tests/test_*_hardening.py`.

### Audio

The first implementation fixed the crash but left the handover racy, and two
of its own changes were regressions.

- `Player.stop()` aborted a stream while the playing thread was closing it.
  sounddevice's `close()` calls `Pa_CloseStream` and only afterwards nulls its
  pointer, so the abort landed on freed memory — no exception, silent
  corruption. The stream is now unpublished under the lock *before* it is
  closed, and the abort happens under the same lock.
- `detect()` cleared the stop flag on entry, erasing a stop that had already
  arrived. The stop is now sticky until `resume()` lifts it.
- `SpeechPipeline.__init__` opened the recorder, so it held the microphone for
  the process lifetime and `run.py --mode wakeword` could never hear anything.
  The stream is now opened per capture. *(Introduced by the mic lock.)*
- `Recorder.start()` marked the microphone held before the stream existed, so a
  concurrent `stop()` released it while leaving the stream open. Both are now
  under one lock. *(Introduced by the mic lock.)*
- `listen()` waited for ever. A wake-word false positive left the assistant
  permanently deaf with the orb stuck on LISTENING. It now times out and
  returns None.
- `interrupt()` did not cancel speech already dispatched, and `play_audio`
  sampled the epoch *after* synthesis — so an interrupt arriving during
  piper's work was ignored. Both closed.
- `MicLock.release()` honoured a release from anything that called it.
  Releases now present the token `acquire()` returned.
- A superseded turn published IDLE over the successor's THINKING.
- Nothing ever entered SPEAKING, which silently broke the orb's speaking form
  and the voice dismissal's wait-for-farewell.

### Vision

- The tray context menu was not excluded from capture — and it is the menu
  that actually appears, since the orb's own fallback menu is only wired up
  when there is no tray at all.
- Tooltips render in their own native windows and do not inherit the
  exclusion, so "FRIDAY — Listening" hovered over an invisible orb. The orb's
  tooltip is now blank while hidden; the tray's is stateless, because a tray
  tooltip is drawn by the shell and cannot be excluded at all.
- `QCursor.pos()` is in logical pixels and `mss` reports monitors in physical
  ones. At 125% scaling the mismatch selected the wrong monitor. Win32
  `GetCursorPos` is used instead, with a device-pixel-ratio fallback.
- `QCursor.pos()` without a QApplication returns a sentinel rather than
  raising, so the guard never fired on the headless path.

Confirmed working, empirically, against `mss`, `PIL.ImageGrab` and Win32
`PrintWindow`: 171,875 captured pixels before the exclusion, 0 after, with the
window still visible on the physical display.

### Files

- `os.startfile` runs whatever it is given. "open setup" scored an exact 1.0
  against `setup.bat` and executed it; a `.reg` match would have been offered
  for merge into the registry. Executable and script types are no longer
  launched from a guessed match.
- Substring and fuzzy score bands overlapped, so a file whose letters merely
  coincided could outrank the one the user named — `windows.media.speech`
  `synthesis.h` was the real top hit for "thesis". The bands are now disjoint.
- Containment was escapable four ways: `%VARS%` expanding to an absolute path,
  `~/../..`, UNC paths, and junctions (which `islink` reports as False on
  Windows). The check now runs on the fully resolved `realpath`.
- `commonpath` raises across drives; the user heard "Paths don't have the same
  drive".
- `create` made a *folder* named `notes.txt` for a file-shaped name, poisoning
  every later "open notes".
- The search ran on the event loop, freezing audio and barge-in for its whole
  duration — on the very path the barge-in work exists to keep responsive.
- The Start menu fallback matched "obs studio" to Roblox Studio and "x" to
  Excel; and it threw away the resolved alias, so "open claude desktop" could
  never have worked even with Claude installed.

### Intent routing

Both the file and vision reviews found the same gap independently: the
rule-based fallback had never heard of the new intents. With the LLM down,
"what's on my screen" reached ChatSkill, which answered confidently about a
screen it cannot see, and "open my budget spreadsheet" matched the generic
`open <word>` rule and launched whatever Start menu entry best matched "my".

The fallback now handles all three intents and extracts their entities. The
screen patterns are shared with a correction pass over the LLM's output, so
the two paths cannot classify the same sentence differently depending on
whether Ollama is up — the live model was sending "what does this error mean"
to a web search.

## Dependencies

`mss` for capture. One model pull, `ollama pull qwen2.5vl:3b`. Both optional at
import time: their absence degrades one feature and leaves the rest working.
