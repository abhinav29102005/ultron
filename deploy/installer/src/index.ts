/**
 * Cloudflare Worker: ULTRON Agent Installation Gateway & Landing Portal
 * Serves dynamic installer scripts and high-aesthetic UI.
 */

interface Env {}

const GITHUB_RAW_BASE = "https://raw.githubusercontent.com/abhinav29102005/ultron/main";

// Embedded Fallback Scripts
const FALLBACK_SH = "#!/usr/bin/env bash\n# ULTRON Agent - One-line Installer\n# Run via: curl -fsSL https://ultron.mlsctiet.com/install | bash\n\nset -e\n\n# --- Configuration ---\nREPO_URL=\"https://github.com/abhinav29102005/ultron.git\"\nINSTALL_DIR=\"$HOME/.ultron\"\nPYTHON_MIN_VERSION=\"3.11\"\n\n# --- Colors ---\nRED='\\033[0;31m'\nGREEN='\\033[0;32m'\nBLUE='\\033[0;34m'\nNC='\\033[0m' # No Color\n\necho -e \"${BLUE}\"\necho \"============================================================\"\necho \"                   ULTRON AGENT INSTALLER                   \"\necho \"============================================================\"\necho -e \"${NC}\"\n\n# --- Prerequisites Check ---\n\necho -e \"${BLUE}[INFO]${NC} Checking prerequisites...\"\n\nif ! command -v git &> /dev/null; then\n    echo -e \"${RED}[ERROR]${NC} git is not installed. Please install git and try again.\"\n    exit 1\nfi\n\nif ! command -v python3 &> /dev/null; then\n    echo -e \"${RED}[ERROR]${NC} python3 is not installed. ULTRON requires Python $PYTHON_MIN_VERSION+.\"\n    exit 1\nfi\n\n# Basic version check (crude but usually sufficient for major.minor)\npy_version=$(python3 -c 'import sys; print(\".\".join(map(str, sys.version_info[:2])))')\nif awk \"BEGIN {exit !($py_version < $PYTHON_MIN_VERSION)}\"; then\n     echo -e \"${RED}[ERROR]${NC} Python $PYTHON_MIN_VERSION or higher is required. Found $py_version.\"\n     exit 1\nfi\necho -e \"${GREEN}[OK]${NC} Python $py_version detected.\"\n\n# --- System Dependencies ---\necho -e \"${BLUE}[INFO]${NC} Checking for missing system dependencies (C-compilers, Audio headers)...\"\n\nif [[ \"$OSTYPE\" == \"linux-gnu\"* ]]; then\n    if command -v apt-get &> /dev/null; then\n        echo -e \"${BLUE}[INFO]${NC} Detected Debian/Ubuntu (apt-get). Installing dependencies...\"\n        sudo apt-get update\n        sudo apt-get install -y build-essential python3-dev python3.11-dev portaudio19-dev libasound2-dev\n    elif command -v dnf &> /dev/null; then\n        echo -e \"${BLUE}[INFO]${NC} Detected Fedora/RHEL (dnf). Installing dependencies...\"\n        sudo dnf install -y gcc gcc-c++ python3-devel python3.11-devel portaudio-devel alsa-lib-devel\n    elif command -v pacman &> /dev/null; then\n        echo -e \"${BLUE}[INFO]${NC} Detected Arch Linux (pacman). Installing dependencies...\"\n        sudo pacman -Sy --needed --noconfirm base-devel python portaudio alsa-lib\n    else\n        echo -e \"${RED}[WARNING]${NC} Unsupported Linux package manager. You may need to manually install C compilers, python-dev, and portaudio.\"\n    fi\nelif [[ \"$OSTYPE\" == \"darwin\"* ]]; then\n    if command -v brew &> /dev/null; then\n        echo -e \"${BLUE}[INFO]${NC} Detected macOS (Homebrew). Installing dependencies...\"\n        brew install portaudio\n    else\n        echo -e \"${RED}[WARNING]${NC} Homebrew not found. You may need to manually install portaudio.\"\n    fi\nfi\n\n# --- Install uv if needed ---\nif ! command -v uv &> /dev/null; then\n    echo -e \"${BLUE}[INFO]${NC} uv not found. Installing uv...\"\n    curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL=\"/usr/local/bin\" sh || curl -LsSf https://astral.sh/uv/install.sh | sh\n    \n    # Ensure uv is in PATH for this session if installed locally\n    export PATH=\"$HOME/.local/bin:$PATH\"\n    \n    if ! command -v uv &> /dev/null; then\n        echo -e \"${RED}[ERROR]${NC} Failed to install uv or add it to PATH.\"\n        exit 1\n    fi\nelse\n    echo -e \"${GREEN}[OK]${NC} uv detected.\"\nfi\n\n# --- Clone Repository ---\necho -e \"${BLUE}[INFO]${NC} Installing ULTRON to $INSTALL_DIR...\"\n\nif [ -d \"$INSTALL_DIR\" ]; then\n    echo -e \"${BLUE}[INFO]${NC} Existing installation found. Updating...\"\n    cd \"$INSTALL_DIR\"\n    git pull origin main\nelse\n    git clone \"$REPO_URL\" \"$INSTALL_DIR\"\n    cd \"$INSTALL_DIR\"\nfi\n\n# --- Setup Environment ---\necho -e \"${BLUE}[INFO]${NC} Setting up Python environment and dependencies...\"\nUV_PYTHON_DOWNLOADS=auto uv sync\n\nif [ ! -f \".env\" ]; then\n    echo -e \"${BLUE}[INFO]${NC} Creating default .env file...\"\n    cp .env.example .env\nfi\n\n# --- Add Alias ---\necho -e \"${BLUE}[INFO]${NC} Setting up 'ultron' & 'ultron' aliases...\"\n\nadd_alias_if_needed() {\n    local rc_file=\"$1\"\n    local ultron_cmd=\"alias ultron='cd $INSTALL_DIR && uv run python run.py'\"\n    local friday_cmd=\"alias friday='cd $INSTALL_DIR && uv run python run.py'\"\n    \n    if [ -f \"$rc_file\" ]; then\n        if ! grep -q \"alias ultron=\" \"$rc_file\"; then\n            echo -e \"\n# ULTRON Agent Aliases\" >> \"$rc_file\"\n            echo \"$ultron_cmd\" >> \"$rc_file\"\n            echo \"$friday_cmd\" >> \"$rc_file\"\n            echo -e \"${GREEN}[OK]${NC} Added aliases (ultron, friday) to $rc_file\"\n        fi\n    fi\n}\n\nadd_alias_if_needed \"$HOME/.bashrc\"\nadd_alias_if_needed \"$HOME/.zshrc\"\n\necho -e \"${GREEN}============================================================${NC}\"\necho -e \"${GREEN}               ULTRON AGENT SUCCESSFULLY INSTALLED!         ${NC}\"\necho -e \"${GREEN}============================================================${NC}\"\necho \"\"\necho \"Next Steps:\"\necho \"1. Restart your terminal, or run: source ~/.bashrc (or ~/.zshrc)\"\necho \"2. Edit your configuration file to add API keys:\"\necho \"   $INSTALL_DIR/.env\"\necho \"3. Start the agent by typing:\"\necho -e \"${BLUE}   ultron${NC}\"\necho \"\"\n";
const FALLBACK_PS1 = "# ULTRON Agent - One-line Installer for Windows\n# Run via: irm https://friday.mlsctiet.com/install | iex\n\n$ErrorActionPreference = 'Stop'\n\n# --- Configuration ---\n$REPO_URL = 'https://github.com/abhinav29102005/ultron.git'\n$INSTALL_DIR = Join-Path $HOME '.ultron'\n$PYTHON_MIN_VERSION = [version]'3.11'\n\nWrite-Host ''\nWrite-Host '============================================================' -ForegroundColor Cyan\nWrite-Host '                   ULTRON AGENT INSTALLER                   ' -ForegroundColor Cyan\nWrite-Host '============================================================' -ForegroundColor Cyan\nWrite-Host ''\n\n# --- Prerequisites Check ---\nWrite-Host '[INFO] Checking prerequisites...' -ForegroundColor Cyan\n\nif (-not (Get-Command git -ErrorAction SilentlyContinue)) {\n    Write-Host '[ERROR] git is not installed. Please install git and try again.' -ForegroundColor Red\n    exit 1\n}\n\nif (-not (Get-Command python -ErrorAction SilentlyContinue)) {\n    Write-Host '[ERROR] python is not installed or not in PATH. ULTRON requires Python 3.11+.' -ForegroundColor Red\n    exit 1\n}\n\n# Version check\n$py_version_str = python -c 'import sys; print(\".\".join(map(str, sys.version_info[:2])))'\n$py_version = [version]$py_version_str\nif ($py_version -lt $PYTHON_MIN_VERSION) {\n    Write-Host \"[ERROR] Python $PYTHON_MIN_VERSION or higher is required. Found $py_version.\" -ForegroundColor Red\n    exit 1\n}\nWrite-Host \"[OK] Python $py_version detected.\" -ForegroundColor Green\n\n# --- Install uv if needed ---\nif (-not (Get-Command uv -ErrorAction SilentlyContinue)) {\n    Write-Host '[INFO] uv not found. Installing uv...' -ForegroundColor Cyan\n    Invoke-WebRequest -Uri https://astral.sh/uv/install.ps1 -OutFile install_uv.ps1\n    powershell -ExecutionPolicy ByPass -File install_uv.ps1\n    Remove-Item install_uv.ps1\n    \n    # Reload PATH\n    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')\n    \n    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {\n        Write-Host '[ERROR] Failed to install uv or add it to PATH.' -ForegroundColor Red\n        exit 1\n    }\n} else {\n    Write-Host '[OK] uv detected.' -ForegroundColor Green\n}\n\n# --- Clone Repository ---\nWrite-Host \"[INFO] Installing ULTRON to $INSTALL_DIR...\" -ForegroundColor Cyan\n\nif (Test-Path $INSTALL_DIR) {\n    Write-Host '[INFO] Existing installation found. Updating...' -ForegroundColor Cyan\n    Set-Location $INSTALL_DIR\n    git pull origin main\n} else {\n    git clone $REPO_URL $INSTALL_DIR\n    Set-Location $INSTALL_DIR\n}\n\n# --- Setup Environment ---\nWrite-Host '[INFO] Setting up Python environment and dependencies...' -ForegroundColor Cyan\n$env:UV_PYTHON_DOWNLOADS = 'auto'\nuv sync\n\nif (-not (Test-Path '.env')) {\n    Write-Host '[INFO] Creating default .env file...' -ForegroundColor Cyan\n    Copy-Item '.env.example' -Destination '.env'\n}\n\n# --- Add Alias ---\nWrite-Host \"[INFO] Setting up 'ultron' & 'friday' aliases in PowerShell Profile...\" -ForegroundColor Cyan\n\nif (-not (Test-Path $PROFILE)) {\n    New-Item -Type File -Path $PROFILE -Force | Out-Null\n}\n\n$alias_ultron = \"function ultron { Set-Location '$INSTALL_DIR'; uv run python run.py }\"\n$alias_friday = \"function friday { Set-Location '$INSTALL_DIR'; uv run python run.py }\"\n$profile_content = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue\nif ($profile_content -notmatch 'function ultron') {\n    Add-Content $PROFILE \"`n# ULTRON Agent Aliases\"\n    Add-Content $PROFILE $alias_ultron\n    Add-Content $PROFILE $alias_friday\n    Write-Host \"[OK] Added ultron & friday aliases to $PROFILE\" -ForegroundColor Green\n}\n\nWrite-Host ''\nWrite-Host '============================================================' -ForegroundColor Green\nWrite-Host '               ULTRON AGENT SUCCESSFULLY INSTALLED!         ' -ForegroundColor Green\nWrite-Host '============================================================' -ForegroundColor Green\nWrite-Host ''\nWrite-Host 'Next Steps:'\nWrite-Host '1. Restart your terminal, or run: . $PROFILE'\nWrite-Host '2. Edit your configuration file to add API keys:'\nWrite-Host \"   $INSTALL_DIR\\.env\"\nWrite-Host '3. Start the agent by typing:'\nWrite-Host '   ultron' -ForegroundColor Cyan\nWrite-Host ''\n";

async function fetchRemoteOrFallback(remoteUrl: string, fallbackText: string): Promise<string> {
  try {
    const response = await fetch(remoteUrl, {
      headers: { "User-Agent": "Ultron-Installer-Gateway/0.2.0" },
      cf: { cacheTtl: 60, cacheEverything: true }
    });
    if (response.ok) {
      const text = await response.text();
      if (text && text.length > 50) {
        return text;
      }
    }
  } catch (e) {
    // Fallback to embedded script if network fails
  }
  return fallbackText;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const userAgent = (request.headers.get("User-Agent") || "").toLowerCase();

    // API Health Endpoint
    if (url.pathname === "/health" || url.pathname === "/api/status") {
      return new Response(
        JSON.stringify({
          status: "online",
          agent: "ULTRON",
          version: "0.2.0",
          repository: "https://github.com/abhinav29102005/ultron",
          timestamp: new Date().toISOString(),
          capabilities: ["Streaming Live RAG", "Dual LLM Tier", "Zero Parametric Hallucination"]
        }, null, 2),
        {
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
          }
        }
      );
    }

    // Direct script endpoints
    if (url.pathname === "/install.sh") {
      const script = await fetchRemoteOrFallback(`${GITHUB_RAW_BASE}/scripts/install.sh`, FALLBACK_SH);
      return new Response(script, {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-cache, no-store, must-revalidate",
        }
      });
    }

    if (url.pathname === "/install.ps1") {
      const script = await fetchRemoteOrFallback(`${GITHUB_RAW_BASE}/scripts/install.ps1`, FALLBACK_PS1);
      return new Response(script, {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-cache, no-store, must-revalidate",
        }
      });
    }

    // Auto-detecting /install endpoint
    if (url.pathname === "/install") {
      const isPowerShell = userAgent.includes("powershell") || userAgent.includes("winhttp");
      if (isPowerShell) {
        const script = await fetchRemoteOrFallback(`${GITHUB_RAW_BASE}/scripts/install.ps1`, FALLBACK_PS1);
        return new Response(script, {
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
          }
        });
      } else {
        const script = await fetchRemoteOrFallback(`${GITHUB_RAW_BASE}/scripts/install.sh`, FALLBACK_SH);
        return new Response(script, {
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
          }
        });
      }
    }

    // Root Landing Page
    if (url.pathname === "/") {
      const origin = url.origin;
      const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ULTRON · Autonomous AI Desktop Agent & Streaming Live RAG</title>
    <meta name="description" content="Production-ready autonomous AI desktop assistant with real-time streaming RAG and zero parametric hallucination.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #08080c;
            --bg-card: rgba(18, 18, 26, 0.7);
            --border: rgba(239, 68, 68, 0.2);
            --border-hover: rgba(239, 68, 68, 0.4);
            --red-glow: rgba(239, 68, 68, 0.25);
            --red-primary: #ef4444;
            --red-accent: #dc2626;
            --cyan-accent: #06b6d4;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: 'Outfit', -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: hidden;
            position: relative;
        }

        .ambient-glow {
            position: fixed;
            top: -20%;
            left: 50%;
            transform: translateX(-50%);
            width: 800px;
            height: 600px;
            background: radial-gradient(circle, var(--red-glow) 0%, rgba(220, 38, 38, 0.05) 50%, transparent 80%);
            pointer-events: none;
            z-index: 0;
        }

        .grid-bg {
            position: fixed;
            inset: 0;
            background-image: linear-gradient(to right, rgba(255, 255, 255, 0.02) 1px, transparent 1px),
                              linear-gradient(to bottom, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
            background-size: 40px 40px;
            pointer-events: none;
            z-index: 0;
        }

        .container {
            max-width: 940px;
            width: 100%;
            padding: 60px 24px;
            display: flex;
            flex-direction: column;
            align-items: center;
            z-index: 1;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 16px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--red-primary);
            margin-bottom: 24px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background: var(--red-primary);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--red-primary);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        h1 {
            font-size: 4rem;
            font-weight: 900;
            line-height: 1.1;
            text-align: center;
            letter-spacing: -0.03em;
            margin-bottom: 20px;
            background: linear-gradient(135deg, #ffffff 40%, #f87171 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .tagline {
            font-size: 1.25rem;
            color: var(--text-muted);
            text-align: center;
            max-width: 660px;
            line-height: 1.6;
            margin-bottom: 40px;
        }

        .terminal-box {
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            backdrop-filter: blur(16px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6), 0 0 20px rgba(239, 68, 68, 0.1);
            overflow: hidden;
            margin-bottom: 48px;
        }

        .terminal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 18px;
            background: rgba(0, 0, 0, 0.4);
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .tab-group {
            display: flex;
            gap: 8px;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-family: inherit;
            font-size: 0.85rem;
            font-weight: 600;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .tab-btn.active {
            background: rgba(239, 68, 68, 0.15);
            color: var(--red-primary);
        }

        .terminal-body {
            padding: 20px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }

        .cmd-text {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.05rem;
            color: #38bdf8;
            word-break: break-all;
        }

        .copy-btn {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: #ffffff;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.85rem;
            padding: 10px 18px;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
            white-space: nowrap;
        }

        .copy-btn:hover {
            background: var(--red-primary);
            box-shadow: 0 0 16px var(--red-primary);
        }

        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 20px;
            width: 100%;
            margin-bottom: 48px;
        }

        .feature-card {
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 24px;
            transition: border-color 0.2s, transform 0.2s;
        }

        .feature-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
        }

        .feature-icon {
            font-size: 1.6rem;
            margin-bottom: 12px;
        }

        .feature-title {
            font-size: 1.15rem;
            font-weight: 700;
            margin-bottom: 8px;
            color: #ffffff;
        }

        .feature-desc {
            font-size: 0.92rem;
            color: var(--text-muted);
            line-height: 1.5;
        }

        footer {
            margin-top: auto;
            padding: 24px;
            color: #64748b;
            font-size: 0.85rem;
            display: flex;
            gap: 16px;
            align-items: center;
        }

        footer a {
            color: var(--text-muted);
            text-decoration: none;
            transition: color 0.2s;
        }

        footer a:hover {
            color: var(--red-primary);
        }
    </style>
</head>
<body>
    <div class="ambient-glow"></div>
    <div class="grid-bg"></div>

    <div class="container">
        <div class="badge">
            <span class="pulse-dot"></span>
            Streaming Live RAG · Theme 4 Ready
        </div>

        <h1>ULTRON</h1>
        <p class="tagline">The production-grade autonomous desktop AI assistant. Powered by real-time speculative RAG, dual-tier LLMs, and strict zero-hallucination grounding.</p>

        <div class="terminal-box">
            <div class="terminal-header">
                <div class="tab-group">
                    <button class="tab-btn active" id="tab-linux" onclick="switchTab('linux')">Linux / macOS</button>
                    <button class="tab-btn" id="tab-windows" onclick="switchTab('windows')">Windows</button>
                </div>
                <span style="font-size: 0.75rem; color: #64748b; font-family: monospace;">One-Line Quickstart</span>
            </div>
            <div class="terminal-body">
                <div class="cmd-text" id="cmd-display">curl -fsSL ${origin}/install | bash</div>
                <button class="copy-btn" onclick="copyCommand()">
                    <span id="copy-icon">📋</span>
                    <span id="copy-text">Copy</span>
                </button>
            </div>
        </div>

        <div class="features-grid">
            <div class="feature-card">
                <div class="feature-icon">⚡</div>
                <div class="feature-title">Speculative Streaming RAG</div>
                <div class="feature-desc">Pre-retrieval commences mid-utterance before voice finish, unlocking up to 1.3s in conversational latency savings.</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🎯</div>
                <div class="feature-title">Zero Parametric Hallucination</div>
                <div class="feature-desc">All factual assertions strictly resolve to exact provenance sections [Doc_XX §YY] with explicit uncertainty flagging.</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">🧠</div>
                <div class="feature-title">Dual-Tier Intelligence</div>
                <div class="feature-desc">Seamless combination of high-throughput NVIDIA NIM cloud models and local Ollama Qwen for instant boundary classification.</div>
            </div>
        </div>

        <footer>
            <span>ULTRON Core v0.2.0</span>
            <span>•</span>
            <a href="https://github.com/abhinav29102005/ultron" target="_blank" rel="noopener">GitHub Repository</a>
            <span>•</span>
            <a href="${origin}/health">System Health</a>
        </footer>
    </div>

    <script>
        let currentTab = 'linux';
        const origin = window.location.origin;

        function switchTab(tab) {
            currentTab = tab;
            document.getElementById('tab-linux').classList.toggle('active', tab === 'linux');
            document.getElementById('tab-windows').classList.toggle('active', tab === 'windows');
            
            const cmd = tab === 'linux' 
                ? 'curl -fsSL ' + origin + '/install | bash'
                : 'irm ' + origin + '/install | iex';
            document.getElementById('cmd-display').innerText = cmd;
        }

        function copyCommand() {
            const cmd = document.getElementById('cmd-display').innerText;
            navigator.clipboard.writeText(cmd);
            const btnText = document.getElementById('copy-text');
            btnText.innerText = 'Copied!';
            setTimeout(() => { btnText.innerText = 'Copy'; }, 2000);
        }
    </script>
</body>
</html>`;

      return new Response(html, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=300",
        }
      });
    }

    return new Response("Not Found", { status: 404 });
  }
};
