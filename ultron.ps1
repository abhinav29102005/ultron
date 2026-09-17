<#
.SYNOPSIS
    ULTRON Autonomous AI Desktop Assistant - Windows PowerShell Native CLI Launcher
.DESCRIPTION
    Launches ULTRON in Windows PowerShell with UTF-8 encoding, virtual environment auto-detection,
    and transparent argument forwarding.
.EXAMPLE
    .\ultron.ps1
    .\ultron.ps1 --mode text
    .\ultron.ps1 upgrade
    .\ultron.ps1 setup
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

# 1. Enforce UTF-8 Console I/O
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$RootDir = $PSScriptRoot
if (-not $RootDir) {
    $RootDir = (Get-Location).Path
}

# 2. Virtual Environment Discovery
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$RunScript = Join-Path $RootDir "run.py"

if (Test-Path $VenvPython) {
    & $VenvPython $RunScript @ScriptArgs
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run python $RunScript @ScriptArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python $RunScript @ScriptArgs
} else {
    Write-Error "Python or .venv not found. Please run scripts\install.ps1 first."
    exit 1
}

exit $LASTEXITCODE
