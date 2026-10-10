#!/usr/bin/env bash
# ULTRON Agent - One-line Installer

set -e

# --- Configuration ---
REPO_URL="https://github.com/abhinav29102005/ultron.git"
INSTALL_DIR="$HOME/.ultron"
PYTHON_MIN_VERSION="3.11"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "============================================================"
echo "                   ULTRON AGENT INSTALLER                   "
echo "============================================================"
echo -e "${NC}"

# --- Prerequisites Check ---

echo -e "${BLUE}[INFO]${NC} Checking prerequisites..."

if ! command -v git &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} git is not installed. Please install git and try again."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} python3 is not installed. ULTRON requires Python $PYTHON_MIN_VERSION+."
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
echo -e "${BLUE}[INFO]${NC} Installing ULTRON to $INSTALL_DIR..."

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

# --- Install Executable Launcher ---
echo -e "${BLUE}[INFO]${NC} Installing 'ultron' launcher to $HOME/.local/bin..."
mkdir -p "$HOME/.local/bin"

cat << 'LAUNCHER' > "$HOME/.local/bin/ultron"
#!/usr/bin/env bash
if [ -f "./run.py" ] && [ -d "./core" ]; then
    TARGET_DIR="$(pwd)"
elif [ -n "$ULTRON_HOME" ] && [ -f "$ULTRON_HOME/run.py" ]; then
    TARGET_DIR="$ULTRON_HOME"
elif [ -f "$HOME/Projects/ultron/run.py" ]; then
    TARGET_DIR="$HOME/Projects/ultron"
elif [ -f "$HOME/.ultron/run.py" ]; then
    TARGET_DIR="$HOME/.ultron"
else
    echo "[ERROR] Ultron installation not found."
    exit 1
fi

cd "$TARGET_DIR" || exit 1

if [ -f "$TARGET_DIR/.venv/bin/python" ]; then
    exec "$TARGET_DIR/.venv/bin/python" "$TARGET_DIR/run.py" "$@"
elif [ -f "$TARGET_DIR/run.py" ]; then
    exec python3 "$TARGET_DIR/run.py" "$@"
else
    echo "[ERROR] Ultron entry point not found in $TARGET_DIR"
    exit 1
fi
LAUNCHER
chmod +x "$HOME/.local/bin/ultron"
ln -sf "$HOME/.local/bin/ultron" /usr/local/bin/ultron 2>/dev/null || true

ensure_path_in_rc() {
    local rc_file="$1"
    if [ -f "$rc_file" ]; then
        if ! grep -q '\.local/bin' "$rc_file"; then
            echo -e '
export PATH="$HOME/.local/bin:$PATH"' >> "$rc_file"
        fi
    fi
}
ensure_path_in_rc "$HOME/.bashrc"
ensure_path_in_rc "$HOME/.zshrc"

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}               ULTRON AGENT SUCCESSFULLY INSTALLED!         ${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Next Steps:"
echo "1. Restart your terminal, or run: source ~/.bashrc (or ~/.zshrc)"
echo "2. Get free cloud LLM keys from developer panels:"
echo "   - NVIDIA NIM (1,000 Free Credits): https://build.nvidia.com/"
echo "   - Groq Cloud (Free High-Speed):   https://console.groq.com/keys"
echo "   - OpenRouter (100+ Models):       https://openrouter.ai/keys"
echo "   - Or run 100% offline with local Ollama (zero keys needed)"
echo "3. Start the agent by typing:"
echo -e "${BLUE}   ultron${NC}"
echo "   (Ultron will interactively guide you to paste keys or configure settings)"
echo ""
