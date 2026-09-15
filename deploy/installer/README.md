# FRIDAY Agent Installer Endpoint

This directory contains the Cloudflare Worker that powers the one-line installation command:

```bash
curl -fsSL https://friday.mlsctiet.com/install | bash
```

## How it works

1. The user requests `https://friday.mlsctiet.com/install`.
2. This Cloudflare Worker (`src/index.ts`) intercepts the request.
3. The Worker dynamically fetches the *latest* version of `scripts/install.sh` from the `main` branch of this GitHub repository via `raw.githubusercontent.com`.
4. The Worker returns the raw bash script text to the user's terminal, where `bash` executes it.

**Benefit:** You can update the `scripts/install.sh` file in the repository, and the installer command will immediately serve the new version without needing to redeploy the Cloudflare Worker!

## Deployment

Deployment is handled automatically via GitHub Actions (`.github/workflows/deploy-installer.yml`). 

### Prerequisites for GitHub Actions
1. Get a Cloudflare API Token (with Edit Cloudflare Workers permissions).
2. Go to your GitHub Repository Settings > Secrets and variables > Actions.
3. Add a new Repository Secret:
   - **Name:** `CLOUDFLARE_API_TOKEN`
   - **Secret:** Your token value

Any changes pushed to the `main` branch affecting files in the `deploy/installer/` directory will trigger an automatic deployment.

### Manual Deployment
If you need to deploy manually:

```bash
cd deploy/installer
npm install
npx wrangler deploy
```

*(Note: You will need to run `npx wrangler login` first if you haven't authenticated locally).*
