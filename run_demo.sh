#!/usr/bin/env bash
# ==============================================================================
# Samsung PRISM GenAI Hackathon (Theme 4: Streaming Live RAG)
# Official Recording & Demonstration Runner
# ==============================================================================

set -e

# Change directory to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH=".:$PYTHONPATH"

echo "======================================================================"
echo " Starting Samsung PRISM Theme 4 Demonstration Runner"
echo "======================================================================"
echo " Mode Options:"
echo "   1) Step-by-Step [Default]: Press [Enter] to advance each turn"
echo "      (Recommended for manual screen recording with voice-over narration)"
echo "   2) Auto: Paced hands-free playback (1.5s - 2s delay between turns)"
echo "   3) Fast: Accelerated execution for verification"
echo "======================================================================"

if [ "$1" == "--auto" ]; then
    python3 scripts/record_demo.py --mode auto
elif [ "$1" == "--fast" ]; then
    python3 scripts/record_demo.py --mode auto --speed fast
else
    # Default is step-by-step for manual recording
    python3 scripts/record_demo.py --mode step
fi
