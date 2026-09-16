#!/usr/bin/env bash
# run_benchmark.sh – Single-command gate verification for ULTRON Streaming RAG
set -euo pipefail
cd "$(dirname "$0")"
echo "[ULTRON] Running Streaming RAG Benchmark..."
uv run python scripts/run_benchmark.py "$@"
