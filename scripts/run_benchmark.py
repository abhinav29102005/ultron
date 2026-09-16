#!/usr/bin/env python3
"""
scripts/run_benchmark.py
========================
Single-command real-data evaluation benchmark for Theme 4: Streaming Live RAG.
Runs the real pipeline over the real corpus without any mocks.
"""
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from streaming_rag.benchmark import main

if __name__ == "__main__":
    main()
