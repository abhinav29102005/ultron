@echo off
setlocal

title ULTRON

cd /d "%~dp0"

echo ============================================================
echo                    ULTRON
echo ============================================================
echo.

if not exist ".ultron\install.json" (
    echo [ERROR] ULTRON is not installed.
    echo.
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

set "UV_PATH=%USERPROFILE%\.local\bin"

if exist "%UV_PATH%\uv.exe" (
    set "PATH=%UV_PATH%;%PATH%"
)

where uv >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] uv could not be found.
    echo.
    echo Please run setup.bat again.
    echo.
    pause
    exit /b 1
)

echo [INFO] Starting ULTRON...
echo.

uv run python main_gui.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo [ERROR] ULTRON exited with an error.
    echo ============================================================
    echo.
    pause
)

endlocal

