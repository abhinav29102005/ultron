/**
 * Cloudflare Worker: ULTRON Agent Installation Gateway & Landing Portal
 * Serves dynamic installer scripts, Cloud LLM Key Hub API, and cybernetic UI.
 */

interface Env {}

const GITHUB_RAW_BASE = "https://raw.githubusercontent.com/abhinav29102005/ultron/main";

interface LLMProvider {
  id: string;
  name: string;
  badge: string;
  badgeColor: string;
  portalUrl: string;
  freeTier: string;
  recommendedModels: string;
  cliCommand: string;
}

const CLOUD_PROVIDERS: LLMProvider[] = [
  {
    id: "nvidia",
    name: "NVIDIA NIM",
    badge: "1,000 Free Credits",
    badgeColor: "#10b981",
    portalUrl: "https://build.nvidia.com/",
    freeTier: "1,000 Free API credits on signup (No credit card needed)",
    recommendedModels: "nvidia/nemotron-3-super-120b-a12b, meta/llama-3.3-70b-instruct",
    cliCommand: "ultron /key nvidia nvapi-..."
  },
  {
    id: "groq",
    name: "Groq Cloud",
    badge: "Free Tier (500+ tok/s)",
    badgeColor: "#06b6d4",
    portalUrl: "https://console.groq.com/keys",
    freeTier: "Fastest LPU inference with generous free rate limits",
    recommendedModels: "llama-3.3-70b-versatile, mixtral-8x7b-32768",
    cliCommand: "ultron /key groq gsk_..."
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    badge: "100+ Models Aggregator",
    badgeColor: "#a855f7",
    portalUrl: "https://openrouter.ai/keys",
    freeTier: "Unified API gateway for Claude 3.5, DeepSeek, and Llama",
    recommendedModels: "deepseek/deepseek-chat, anthropic/claude-3.5-sonnet",
    cliCommand: "ultron /key openrouter sk-or-..."
  },
  {
    id: "openai",
    name: "OpenAI Platform",
    badge: "GPT-4o & Embeddings",
    badgeColor: "#3b82f6",
    portalUrl: "https://platform.openai.com/api-keys",
    freeTier: "Direct platform access for GPT-4o and text-embedding-3",
    recommendedModels: "gpt-4o, text-embedding-3-small",
    cliCommand: "ultron /key openai sk-..."
  },
  {
    id: "anthropic",
    name: "Anthropic Claude",
    badge: "Claude 3.5 Sonnet",
    badgeColor: "#f59e0b",
    portalUrl: "https://console.anthropic.com/",
    freeTier: "Anthropic console access for Claude 3.5 Sonnet and Haiku",
    recommendedModels: "claude-3-5-sonnet-20241022",
    cliCommand: "ultron /key anthropic sk-ant-..."
  },
  {
    id: "picovoice",
    name: "Picovoice Porcupine",
    badge: "Wake Word Detection",
    badgeColor: "#ec4899",
    portalUrl: "https://console.picovoice.ai/",
    freeTier: "Free personal tier for custom 'Ultron' wake word recognition",
    recommendedModels: "Ultron Porcupine wake word",
    cliCommand: "ultron /key picovoice <key>"
  },
  {
    id: "ollama",
    name: "Local Ollama",
    badge: "100% Offline · Zero Keys",
    badgeColor: "#64748b",
    portalUrl: "https://ollama.com/",
    freeTier: "Completely private, local CPU/GPU execution with zero telemetry",
    recommendedModels: "qwen2.5:7b-instruct, llama3.2:3b",
    cliCommand: "ultron /mode offline"
  }
];

const FALLBACK_SH = `#!/usr/bin/env bash
# ULTRON Agent - One-line Installer
set -e

REPO_URL="https://github.com/abhinav29102005/ultron.git"
INSTALL_DIR="$HOME/.ultron"

echo "Installing ULTRON to $INSTALL_DIR..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR" && git pull origin main
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

uv sync
[ -f .env ] || cp .env.example .env

echo "============================================================"
echo "               ULTRON AGENT SUCCESSFULLY INSTALLED!         "
echo "============================================================"
echo ""
echo "Next Steps:"
echo "1. Get free cloud LLM keys from developer panels:"
echo "   - NVIDIA NIM (1,000 Free Credits): https://build.nvidia.com/"
echo "   - Groq Cloud (Free High-Speed):   https://console.groq.com/keys"
echo "   - OpenRouter (100+ Models):       https://openrouter.ai/keys"
echo "   - Or run 100% offline with local Ollama (zero keys needed)"
echo "2. Start the agent by typing:"
echo "   ultron"
echo "   (Ultron will interactively guide you to paste keys or configure settings)"
echo ""
`;

const FALLBACK_PS1 = `# ULTRON Agent - Windows One-line Installer
$ErrorActionPreference = 'Stop'
$REPO_URL = 'https://github.com/abhinav29102005/ultron.git'
$INSTALL_DIR = Join-Path $HOME '.ultron'

Write-Host 'Installing ULTRON...' -ForegroundColor Cyan
if (Test-Path $INSTALL_DIR) {
    Set-Location $INSTALL_DIR
    git pull origin main
} else {
    git clone $REPO_URL $INSTALL_DIR
    Set-Location $INSTALL_DIR
}

uv sync
if (-not (Test-Path '.env')) { Copy-Item '.env.example' -Destination '.env' }

Write-Host '============================================================' -ForegroundColor Green
Write-Host '               ULTRON AGENT SUCCESSFULLY INSTALLED!         ' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Next Steps:'
Write-Host '1. Get free cloud LLM keys from developer panels:'
Write-Host '   - NVIDIA NIM (1,000 Free Credits): https://build.nvidia.com/'
Write-Host '   - Groq Cloud (Free High-Speed):   https://console.groq.com/keys'
Write-Host '   - OpenRouter (100+ Models):       https://openrouter.ai/keys'
Write-Host '   - Or run 100% offline with local Ollama (zero keys needed)'
Write-Host '2. Start the agent by typing:'
Write-Host '   ultron' -ForegroundColor Cyan
Write-Host '   (Ultron will interactively guide you to paste keys or configure settings)'
Write-Host ''
`;

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
  } catch (e) {}
  return fallbackText;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const userAgent = (request.headers.get("User-Agent") || "").toLowerCase();

    // Health & System Status Endpoint
    if (url.pathname === "/health" || url.pathname === "/api/status") {
      return new Response(
        JSON.stringify({
          status: "online",
          agent: "ULTRON",
          version: "0.2.0",
          repository: "https://github.com/abhinav29102005/ultron",
          timestamp: new Date().toISOString(),
          capabilities: [
            "Streaming Live Speculative RAG",
            "Dual-Tier LLM Architecture",
            "Zero Parametric Hallucination Grounding",
            "Interactive Cloud LLM API Key Hub",
            "Dockerized Vector & Turn Persistence",
            "Cybernetic CLI Context Dashboard"
          ]
        }, null, 2),
        {
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
          }
        }
      );
    }

    // Cloud LLM Provider Hub API Endpoint
    if (url.pathname === "/keys" || url.pathname === "/api/keys") {
      return new Response(
        JSON.stringify({
          status: "ok",
          description: "ULTRON Cloud LLM & API Key Hub",
          totalProviders: CLOUD_PROVIDERS.length,
          providers: CLOUD_PROVIDERS,
          cliCommands: {
            interactiveWizard: "/setup",
            portalHub: "/hub",
            setKey: "/key <provider> <api_key>",
            toggleOffline: "/mode offline",
            listSessions: "/chats",
            selfUpgrade: "ultron upgrade (or /upgrade)"
          }
        }, null, 2),
        {
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=300",
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
      const providersCardsHtml = CLOUD_PROVIDERS.map(p => `
        <div class="provider-card">
          <div class="provider-card-header">
            <span class="provider-name">${p.name}</span>
            <span class="provider-badge" style="color: ${p.badgeColor}; border-color: ${p.badgeColor}40; background: ${p.badgeColor}15;">${p.badge}</span>
          </div>
          <p class="provider-desc">${p.freeTier}</p>
          <div class="provider-models"><span class="model-tag">${p.recommendedModels}</span></div>
          <div class="provider-footer">
            <a href="${p.portalUrl}" target="_blank" rel="noopener" class="portal-btn">
              Get Key ↗
            </a>
            <code class="cli-hint">${p.cliCommand}</code>
          </div>
        </div>
      `).join("");

      const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ULTRON · Autonomous AI Desktop Agent & Cloud LLM Hub</title>
    <meta name="description" content="Production-ready autonomous AI desktop assistant with streaming live RAG, dual-tier LLMs, and cloud API key hub.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #08080c;
            --bg-card: rgba(18, 18, 26, 0.75);
            --border: rgba(239, 68, 68, 0.2);
            --border-hover: rgba(239, 68, 68, 0.45);
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
            top: -200px;
            left: 50%;
            transform: translateX(-50%);
            width: 800px;
            height: 600px;
            background: radial-gradient(circle, var(--red-glow) 0%, transparent 70%);
            pointer-events: none;
            z-index: 0;
        }

        .grid-bg {
            position: fixed;
            inset: 0;
            background-image: 
                linear-gradient(to right, rgba(255, 255, 255, 0.02) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
            background-size: 40px 40px;
            pointer-events: none;
            z-index: 0;
        }

        .container {
            width: 100%;
            max-width: 1080px;
            padding: 60px 24px;
            display: flex;
            flex-direction: column;
            align-items: center;
            position: relative;
            z-index: 1;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: var(--red-primary);
            padding: 6px 16px;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 24px;
            box-shadow: 0 0 20px rgba(239, 68, 68, 0.15);
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background: var(--red-primary);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--red-primary);
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        h1 {
            font-size: clamp(3rem, 7vw, 5rem);
            font-weight: 900;
            letter-spacing: -0.04em;
            text-align: center;
            margin-bottom: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #cbd5e1 50%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .tagline {
            font-size: 1.25rem;
            color: var(--text-muted);
            text-align: center;
            max-width: 720px;
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

        .section-heading {
            text-align: center;
            margin: 32px 0 24px;
            width: 100%;
        }

        .section-heading h2 {
            font-size: 2rem;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 8px;
        }

        .section-heading p {
            color: var(--text-muted);
            font-size: 1rem;
            max-width: 600px;
            margin: 0 auto;
        }

        .providers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
            gap: 20px;
            width: 100%;
            margin-bottom: 48px;
        }

        .provider-card {
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            backdrop-filter: blur(12px);
            transition: all 0.2s ease;
        }

        .provider-card:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
            box-shadow: 0 12px 28px rgba(0,0,0,0.4);
        }

        .provider-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .provider-name {
            font-size: 1.15rem;
            font-weight: 700;
            color: #ffffff;
        }

        .provider-badge {
            font-size: 0.72rem;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid;
            letter-spacing: 0.02em;
        }

        .provider-desc {
            font-size: 0.88rem;
            color: var(--text-muted);
            line-height: 1.45;
        }

        .provider-models {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }

        .model-tag {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #38bdf8;
            padding: 2px 8px;
            border-radius: 4px;
        }

        .provider-footer {
            margin-top: auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-top: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            gap: 8px;
        }

        .portal-btn {
            background: rgba(239, 68, 68, 0.15);
            color: #fca5a5;
            text-decoration: none;
            font-size: 0.8rem;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid rgba(239, 68, 68, 0.3);
            transition: all 0.2s;
        }

        .portal-btn:hover {
            background: var(--red-primary);
            color: #ffffff;
            box-shadow: 0 0 10px var(--red-primary);
        }

        .cli-hint {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: #94a3b8;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
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
            flex-wrap: wrap;
            justify-content: center;
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
            Streaming Live RAG · Multi-Provider LLM Hub
        </div>

        <h1>ULTRON</h1>
        <p class="tagline">The production-grade autonomous desktop AI assistant. Powered by speculative streaming RAG, dual-tier LLMs, interactive cloud key management, and zero parametric hallucination.</p>

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

        <div class="section-heading">
            <h2>Cloud LLM Key Hub</h2>
            <p>Obtain free inference keys directly from provider developer panels or switch between cloud and offline models with ease.</p>
        </div>

        <div class="providers-grid">
            ${providersCardsHtml}
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
                <div class="feature-title">Multi-Provider Key Hub</div>
                <div class="feature-desc">Seamlessly configure keys across NVIDIA NIM, Groq, OpenRouter, OpenAI, and Anthropic, or run 100% offline with Ollama.</div>
            </div>
        </div>

        <footer>
            <span>ULTRON Core v0.2.0</span>
            <span>•</span>
            <a href="https://github.com/abhinav29102005/ultron" target="_blank" rel="noopener">GitHub Repository</a>
            <span>•</span>
            <a href="${origin}/keys">API Key Hub (JSON)</a>
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
