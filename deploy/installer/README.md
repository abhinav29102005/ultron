# ULTRON Agent Installer & Portal Endpoint

This directory contains the Cloudflare Worker that powers the one-line installation commands and web portal:

```bash
# Linux / macOS
curl -fsSL https://friday.mlsctiet.com/install | bash

# Windows (PowerShell)
irm https://friday.mlsctiet.com/install | iex
```

Or via direct Workers endpoint:
```bash
curl -fsSL https://ultron-installer.msc-295.workers.dev/install | bash
```

## How it works

1. **Request Interception**: Incoming requests to `/install` or custom paths are routed through Cloudflare edge network.
2. **Dynamic Live Fetch**: The worker fetches the latest `scripts/install.sh` or `scripts/install.ps1` directly from `https://raw.githubusercontent.com/abhinav29102005/ultron/main/`.
3. **Resilient Embedded Fallback**: If GitHub is unreachable or throttled, it immediately falls back to high-fidelity embedded scripts.
4. **Interactive Portal**: Requests to `/` serve a responsive, cybernetic dark-mode landing portal with copy-to-clipboard actions and architecture highlights.
5. **Health Telemetry**: `/health` and `/api/status` expose machine-readable JSON status.

## Manual Deployment

```bash
cd deploy/installer
npm install
npx wrangler deploy
```
