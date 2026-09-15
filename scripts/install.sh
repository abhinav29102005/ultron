#!/usr/bin/env bash
# FRIDAY Agent - One-line Installer
# Run via: curl -fsSL https://friday.mlsctiet.com/install | bash

set -e

# --- Configuration ---
REPO_URL="https://github.com/MicrosoftStudentChapter/friday-agent.git"
INSTALL_DIR="$HOME/.friday-agent"
PYTHON_MIN_VERSION="3.11"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "============================================================"
echo "                   FRIDAY AGENT INSTALLER                   "
echo "============================================================"
echo -e "${NC}"

# --- Prerequisites Check ---

echo -e "${BLUE}[INFO]${NC} Checking prerequisites..."

if ! command -v git &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} git is not installed. Please install git and try again."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} python3 is not installed. FRIDAY requires Python $PYTHON_MIN_VERSION+."
    exit 1
fi

# Basic version check (crude but usually sufficient for major.minor)
py_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if awk "BEGIN {exit !($py_version < $PYTHON_MIN_VERSION)}"; then
     echo -e "${RED}[ERROR]${NC} Python $PYTHON_MIN_VERSION or higher is required. Found $py_version."
     exit 1
fi
echo -e "${GREEN}[OK]${NC} Python $py_version detected."

# --- System Dependencies ---
echo -e "${BLUE}[INFO]${NC} Checking for missing system dependencies (C-compilers, Audio headers)..."

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v apt-get &> /dev/null; then
        echo -e "${BLUE}[INFO]${NC} Detected Debian/Ubuntu (apt-get). Installing dependencies..."
        sudo apt-get update
        sudo apt-get install -y build-essential python3-dev python3.11-dev portaudio19-dev libasound2-dev
    elif command -v dnf &> /dev/null; then
        echo -e "${BLUE}[INFO]${NC} Detected Fedora/RHEL (dnf). Installing dependencies..."
        sudo dnf install -y gcc gcc-c++ python3-devel python3.11-devel portaudio-devel alsa-lib-devel
    elif command -v pacman &> /dev/null; then
        echo -e "${BLUE}[INFO]${NC} Detected Arch Linux (pacman). Installing dependencies..."
        sudo pacman -Sy --needed --noconfirm base-devel python portaudio alsa-lib
    else
        echo -e "${RED}[WARNING]${NC} Unsupported Linux package manager. You may need to manually install C compilers, python-dev, and portaudio."
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v brew &> /dev/null; then
        echo -e "${BLUE}[INFO]${NC} Detected macOS (Homebrew). Installing dependencies..."
        brew install portaudio
    else
        echo -e "${RED}[WARNING]${NC} Homebrew not found. You may need to manually install portaudio."
    fi
fi

# --- Install uv if needed ---
if ! command -v uv &> /dev/null; then
    echo -e "${BLUE}[INFO]${NC} uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="/usr/local/bin" sh || curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Ensure uv is in PATH for this session if installed locally
    export PATH="$HOME/.local/bin:$PATH"
    
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}[ERROR]${NC} Failed to install uv or add it to PATH."
        exit 1
    fi
else
    echo -e "${GREEN}[OK]${NC} uv detected."
fi

# --- Clone Repository ---
echo -e "${BLUE}[INFO]${NC} Installing FRIDAY to $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${BLUE}[INFO]${NC} Existing installation found. Updating..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# --- Setup Environment ---
echo -e "${BLUE}[INFO]${NC} Setting up Python environment and dependencies..."
UV_PYTHON_DOWNLOADS=auto uv sync

if [ ! -f ".env" ]; then
    echo -e "${BLUE}[INFO]${NC} Creating default .env file..."
    cp .env.example .env
fi

# --- Add Alias ---
echo -e "${BLUE}[INFO]${NC} Setting up 'friday' alias..."

add_alias_if_needed() {
    local rc_file="$1"
    local alias_cmd="alias friday='cd $INSTALL_DIR && uv run python main.py'"
    
    if [ -f "$rc_file" ]; then
        if ! grep -q "alias friday=" "$rc_file"; then
            echo -e "\n# FRIDAY Agent Alias" >> "$rc_file"
            echo "$alias_cmd" >> "$rc_file"
            echo -e "${GREEN}[OK]${NC} Added alias to $rc_file"
        fi
    fi
}

add_alias_if_needed "$HOME/.bashrc"
add_alias_if_needed "$HOME/.zshrc"

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}               FRIDAY AGENT SUCCESSFULLY INSTALLED!         ${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Next Steps:"
echo "1. Restart your terminal, or run: source ~/.bashrc (or ~/.zshrc)"
echo "2. Edit your configuration file to add API keys:"
echo "   $INSTALL_DIR/.env"
echo "3. Start the agent by typing:"
echo -e "${BLUE}   friday${NC}"
echo ""
