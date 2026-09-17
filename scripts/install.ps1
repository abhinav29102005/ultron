# ULTRON Agent - One-line Installer for Windows
# Run via: irm https://ultron.mlsctiet.com/install | iex

$ErrorActionPreference = 'Stop'

# --- Configuration ---
$REPO_URL = 'https://github.com/abhinav29102005/ultron.git'
$INSTALL_DIR = Join-Path $HOME '.ultron'
$PYTHON_MIN_VERSION = [version]'3.11'

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '                   ULTRON AGENT INSTALLER                   ' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

# --- Prerequisites Check ---
Write-Host '[INFO] Checking prerequisites...' -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] git is not installed. Please install git and try again.' -ForegroundColor Red
    exit 1
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] python is not installed or not in PATH. ULTRON requires Python 3.11+.' -ForegroundColor Red
    exit 1
}

# Version check
$py_version_str = python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'
$py_version = [version]$py_version_str
if ($py_version -lt $PYTHON_MIN_VERSION) {
    Write-Host "[ERROR] Python $PYTHON_MIN_VERSION or higher is required. Found $py_version." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python $py_version detected." -ForegroundColor Green

# --- Install uv if needed ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host '[INFO] uv not found. Installing uv...' -ForegroundColor Cyan
    Invoke-WebRequest -Uri https://astral.sh/uv/install.ps1 -OutFile install_uv.ps1
    powershell -ExecutionPolicy ByPass -File install_uv.ps1
    Remove-Item install_uv.ps1
    
    # Reload PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
    
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host '[ERROR] Failed to install uv or add it to PATH.' -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host '[OK] uv detected.' -ForegroundColor Green
}

# --- Clone Repository ---
Write-Host "[INFO] Installing ULTRON to $INSTALL_DIR..." -ForegroundColor Cyan

if (Test-Path $INSTALL_DIR) {
    Write-Host '[INFO] Existing installation found. Updating...' -ForegroundColor Cyan
    Set-Location $INSTALL_DIR
    git pull origin main
} else {
    git clone $REPO_URL $INSTALL_DIR
    Set-Location $INSTALL_DIR
}

# --- Setup Environment ---
Write-Host '[INFO] Setting up Python environment and dependencies...' -ForegroundColor Cyan
$env:UV_PYTHON_DOWNLOADS = 'auto'
uv sync

if (-not (Test-Path '.env')) {
    Write-Host '[INFO] Creating default .env file...' -ForegroundColor Cyan
    Copy-Item '.env.example' -Destination '.env'
}

# --- Add Function to Profile ---
Write-Host "[INFO] Setting up 'ultron' command in PowerShell Profile..." -ForegroundColor Cyan

$ProfileDir = Split-Path $PROFILE -Parent
if ($ProfileDir -and -not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}

$ultron_cmd = "function ultron { Set-Location '$INSTALL_DIR'; if (Test-Path '.\ultron.ps1') { .\ultron.ps1 @args } else { uv run python run.py @args } }"
$profile_content = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
if ($profile_content -notmatch 'function ultron') {
    Add-Content $PROFILE "`n# ULTRON Agent Function"
    Add-Content $PROFILE $ultron_cmd
    Write-Host "[OK] Added 'ultron' command to $PROFILE" -ForegroundColor Green
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '               ULTRON AGENT SUCCESSFULLY INSTALLED!         ' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Next Steps:'
Write-Host '1. Restart your terminal, or run: . $PROFILE'
Write-Host '2. Get free cloud LLM keys from developer panels:'
Write-Host '   - NVIDIA NIM (1,000 Free Credits): https://build.nvidia.com/'
Write-Host '   - Groq Cloud (Free High-Speed):   https://console.groq.com/keys'
Write-Host '   - OpenRouter (100+ Models):       https://openrouter.ai/keys'
Write-Host '   - Or run 100% offline with local Ollama (zero keys needed)'
Write-Host '3. Start the agent by typing:'
Write-Host '   ultron' -ForegroundColor Cyan
Write-Host '   (Ultron will interactively guide you to paste keys or configure settings)'
Write-Host ''
