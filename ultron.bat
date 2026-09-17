@echo off
setlocal
:: ============================================================
:: ULTRON Windows Native CLI Launcher
:: Optimized for low-latency execution and UTF-8 console output
:: ============================================================

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0run.py" %*
) else if exist "%~dp0.venv\bin\python.exe" (
    "%~dp0.venv\bin\python.exe" "%~dp0run.py" %*
) else (
    python "%~dp0run.py" %*
)

endlocal
