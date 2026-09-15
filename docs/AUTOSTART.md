# Autostart — launching FRIDAY when you log in

By default you have to open the project folder and run a command every time you
boot. Autostart removes that step: FRIDAY launches itself when you log into
Windows, with no console window and no manual command.

This document covers only the **boot-time registration**. Waking on a spoken
name and hiding on "bye bye" are handled elsewhere in the app.

---

## Turn it on / off

From the repository root:

```powershell
# turn it on
.venv\Scripts\python.exe -m utils.autostart --enable

# check what is currently registered
.venv\Scripts\python.exe -m utils.autostart --status

# turn it off
.venv\Scripts\python.exe -m utils.autostart --disable
```

`--status` (also the default when you pass no flag) prints the registry key, the
exact command registered, and whether that command still matches this checkout.

From Python — this is the API the UI's tray menu should call:

```python
from utils import autostart

autostart.is_enabled()   # -> bool
autostart.enable()       # register (safe to call repeatedly)
autostart.disable()      # unregister (safe to call when already off)
autostart.status()       # -> dict, for rendering a checkbox + tooltip
```

Both `enable()` and `disable()` are idempotent, so a tray checkbox can call them
freely without tracking prior state. They raise `utils.autostart.AutostartError`
if the registry cannot be written.

---

## What it creates, and where

Exactly one registry value. Nothing else is written, and no file is copied
anywhere.

| | |
|---|---|
| **Key** | `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` |
| **Value name** | `FridayAssistant` |
| **Value type** | `REG_SZ` |
| **Value data** | `"<repo>\.venv\Scripts\pythonw.exe" "<repo>\scripts\friday_launcher.pyw"` |

On this machine `<repo>` is `C:\Users\HP\Desktop\friday-agent-main`, so the data
reads:

```
"C:\Users\HP\Desktop\friday-agent-main\.venv\Scripts\pythonw.exe" "C:\Users\HP\Desktop\friday-agent-main\scripts\friday_launcher.pyw"
```

### Why this mechanism

- **`HKEY_CURRENT_USER`, not `HKEY_LOCAL_MACHINE`.** No administrator rights are
  needed, and the app starts inside your interactive desktop session — which is
  what gives it the microphone, the speakers and the screen. A `SYSTEM`-level
  scheduled task or an `HKLM` entry would need elevation and would run in a
  session with no audio devices.
- **Registry, not a Startup-folder shortcut.** A Startup-folder entry must be a
  `.lnk`, and creating one needs COM via `pywin32`/`winshell`, which this project
  does not install. `winreg` is in the standard library. A registry value is also
  keyed by name, so re-registering overwrites the single entry instead of
  littering the folder with duplicate shortcuts.
- **`pythonw.exe`, not `python.exe`.** `python.exe` is a console-subsystem
  binary, so Windows would open a black terminal window on every boot. FRIDAY is
  a PyQt GUI app; `pythonw.exe` is the same interpreter built for the GUI
  subsystem and creates no console.
- **Absolute paths.** At login the working directory is `C:\Windows\system32`,
  not the repository, so both the interpreter and the script are stored as
  fully-qualified, individually quoted paths.

### Why the launcher script

`scripts/friday_launcher.pyw` is a thin shim in front of `main_gui.py`. It:

1. `chdir`s to the repository root, so relative paths inside the codebase resolve
   the way they do when you launch from a shell in the project. (The project has
   already been bitten by this class of bug once, with a relative memory path.)
2. Puts the repository on `sys.path` so the app's top-level packages import.
3. Writes any startup traceback to `logs/autostart_launcher.log` — because
   `pythonw.exe` has no console, an unhandled error would otherwise vanish and
   FRIDAY would simply appear not to start.

---

## If something goes wrong

**FRIDAY does not appear after login.** Check `logs/autostart_launcher.log`
first. To reproduce the boot path with output visible, run the launcher under the
console interpreter:

```powershell
.venv\Scripts\python.exe scripts\friday_launcher.pyw
```

**You moved the folder or rebuilt the venv.** The stored command still points at
the old location. `--status` reports this as `up to date : False`. Re-run
`--enable` to rewrite it with the current paths.

**Removing it manually.** If the CLI is unavailable — a broken venv, for
instance — any one of these removes the entry:

- **Registry Editor:** press `Win+R`, run `regedit`, navigate to
  `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`, right-click
  the `FridayAssistant` value and choose *Delete*.
- **PowerShell** (no admin rights required):

  ```powershell
  Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'FridayAssistant'
  ```

- **Task Manager:** open the *Startup apps* tab, find the FRIDAY entry and click
  *Disable*. This leaves the registry value in place but stops it running, and
  note that Windows remembers the disabled state — after doing this, re-running
  `--enable` will not necessarily make it start again until you re-enable it here
  too.

Deleting the value affects nothing else; every other program's entry under that
key is independent, and `disable()` likewise only ever touches the
`FridayAssistant` value.

---

## Testing

`tests/test_autostart.py` exercises enable/disable/idempotency against a
throwaway key, `HKCU\Software\FridayAgentTest\Run`, which is created and deleted
by a fixture. The real Run key is never opened for writing by the test suite, and
one test asserts that no `FridayAssistant` value is left behind on the developer's
machine.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_autostart.py -o addopts="" -q
```
