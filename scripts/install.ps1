# FRIDAY Agent - One-line Installer for Windows
# Run via: irm https://friday.mlsctiet.com/install | iex

$ErrorActionPreference = 'Stop'

# --- Configuration ---
$REPO_URL = 'https://github.com/MicrosoftStudentChapter/friday-agent.git'
$INSTALL_DIR = Join-Path $HOME '.friday-agent'
$PYTHON_MIN_VERSION = [version]'3.11'

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '                   FRIDAY AGENT INSTALLER                   ' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

# --- Prerequisites Check ---
Write-Host '[INFO] Checking prerequisites...' -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] git is not installed. Please install git and try again.' -ForegroundColor Red
    exit 1
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] python is not installed or not in PATH. FRIDAY requires Python 3.11+.' -ForegroundColor Red
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
Write-Host "[INFO] Installing FRIDAY to $INSTALL_DIR..." -ForegroundColor Cyan

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

# --- Add Alias ---
Write-Host "[INFO] Setting up 'friday' alias in PowerShell Profile..." -ForegroundColor Cyan

if (-not (Test-Path $PROFILE)) {
    New-Item -Type File -Path $PROFILE -Force | Out-Null
}

$alias_cmd = "function friday { Set-Location '$INSTALL_DIR'; uv run python main.py }"
$profile_content = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
if ($profile_content -notmatch 'function friday') {
    Add-Content $PROFILE "`n# FRIDAY Agent Alias"
    Add-Content $PROFILE $alias_cmd
    Write-Host "[OK] Added alias to $PROFILE" -ForegroundColor Green
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '               FRIDAY AGENT SUCCESSFULLY INSTALLED!         ' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Next Steps:'
Write-Host '1. Restart your terminal, or run: . $PROFILE'
Write-Host '2. Edit your configuration file to add API keys:'
Write-Host "   $INSTALL_DIR\.env"
Write-Host '3. Start the agent by typing:'
Write-Host '   friday' -ForegroundColor Cyan
Write-Host ''
