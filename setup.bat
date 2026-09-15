@echo off
setlocal EnableDelayedExpansion

title JARVIS Setup

cd /d "%~dp0"

echo ============================================================
echo                 JARVIS SETUP
echo ============================================================
echo.

echo [INFO] Checking for Python 3.13...

py -3.13 --version >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [OK] Python 3.13 detected.
    goto RUN_BOOTSTRAPPER
)

echo [INFO] Python 3.13 was not found.
echo [INFO] Installing Python 3.13...
echo.

set "PYTHON_INSTALLER=%TEMP%\jarvis_python_installer.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$url = 'https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe';" ^
    "Invoke-WebRequest -Uri $url -OutFile '%PYTHON_INSTALLER%'"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to download Python 3.13.
    pause
    exit /b 1
)

echo [OK] Python installer downloaded.
echo [INFO] Installing Python 3.13...

"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Python installation failed.
    pause
    exit /b 1
)

del "%PYTHON_INSTALLER%" >nul 2>&1

echo [OK] Python installation completed.
echo.

REM Refresh PATH for this script
set "LOCAL_PYTHON=%LocalAppData%\Programs\Python\Python313"
set "PATH=%LOCAL_PYTHON%;%LOCAL_PYTHON%\Scripts;%PATH%"

py -3.13 --version >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3.13 was installed but could not be detected.
    echo [INFO] Please restart Windows and run setup.bat again.
    pause
    exit /b 1
)

echo [OK] Python 3.13 is ready.
echo.


:RUN_BOOTSTRAPPER

echo [INFO] Starting JARVIS bootstrapper...
echo.

py -3.13 bootstrap\bootstrap.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo [ERROR] JARVIS setup failed.
    echo ============================================================
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo [OK] JARVIS setup completed successfully.
echo ============================================================
echo.

pause
endlocal