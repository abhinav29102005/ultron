import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
import json

def run_command(command: list[str]) -> None:
    """Run a command and stop if it fails."""
    print(f"\n> {' '.join(command)}")

    result = subprocess.run(command)

    if result.returncode != 0:
        print("\n[ERROR] Command failed.")
        sys.exit(result.returncode)

def setup_environment_file() -> None:
    """Create a .env file if one does not already exist."""
    print("\n[INFO] Checking environment configuration...")

    env_file = Path(".env")

    if env_file.exists():
        print("[OK] Existing .env found. Keeping it unchanged.")
        return

    env_file.write_text(
        "# JARVIS environment configuration\n"
        "# Add your API keys and configuration here.\n\n",
        encoding="utf-8",
    )

    print("[OK] Created .env file.")

def check_windows() -> None:
    """Make sure Jarvis is running on Windows."""
    if platform.system() != "Windows":
        print("[ERROR] Jarvis currently supports Windows only.")
        sys.exit(1)

    print("[OK] Windows detected.")


def check_python() -> None:
    """Check that the current Python version is supported."""
    version = sys.version_info

    print(
        f"[INFO] Python detected: "
        f"{version.major}.{version.minor}.{version.micro}"
    )

    if version.major != 3 or version.minor != 13:
        print("[ERROR] Jarvis requires Python 3.13.")
        sys.exit(1)

    print("[OK] Python 3.13 detected.")


def install_uv() -> None:
    """Install uv using the official Windows installer."""
    print("[INFO] uv is not installed.")
    print("[INFO] Installing uv...")

    installer = (
        "https://astral.sh/uv/install.ps1"
    )

    command = [
        "powershell",
        "-ExecutionPolicy",
        "ByPass",
        "-Command",
        f"irm {installer} | iex",
    ]

    result = subprocess.run(command)

    if result.returncode != 0:
        print("[ERROR] Failed to install uv.")
        sys.exit(result.returncode)

    print("[OK] uv installation completed.")


def check_uv() -> None:
    """Check whether uv is available and install it if necessary."""
    uv_local_path = Path.home() / ".local" / "bin" / "uv.exe"

    # First check the current PATH.
    if shutil.which("uv") is not None:
        print("[OK] uv detected.")
        return

    # Check the standard uv installation location.
    if uv_local_path.exists():
        print("[OK] uv detected at the standard installation location.")

        uv_dir = str(uv_local_path.parent)

        if uv_dir not in os.environ["PATH"]:
            os.environ["PATH"] = uv_dir + os.pathsep + os.environ["PATH"]

        return

    # uv does not exist, so install it.
    install_uv()

    # Check again after installation.
    if uv_local_path.exists():
        uv_dir = str(uv_local_path.parent)

        if uv_dir not in os.environ["PATH"]:
            os.environ["PATH"] = uv_dir + os.pathsep + os.environ["PATH"]

        print("[OK] uv detected after installation.")
        return

    print("[ERROR] uv was installed but could not be found.")
    sys.exit(1)

def setup_wake_word_models() -> None:
    """Download the ONNX wake-word models required by Jarvis."""
    print("\n[INFO] Setting up wake-word models...")

    run_command([
        "uv",
        "run",
        "python",
        "-c",
        "import openwakeword; openwakeword.utils.download_models(['hey_jarvis_v0.1'])",
    ])

    print("[OK] Wake-word models are ready.")

def setup_environment() -> None:
    """Create and synchronize the Jarvis Python environment."""
    print("\n[INFO] Setting up Jarvis environment...")

    run_command(["uv", "sync"])

    print("[OK] Jarvis environment is ready.")


def install_openwakeword() -> None:
    """Install OpenWakeWord separately from the main dependency set."""
    print("\n[INFO] Installing OpenWakeWord...")

    run_command([
        "uv",
        "pip",
        "install",
        "openwakeword",
    ])

    print("[OK] OpenWakeWord installed.")

def verify_openwakeword() -> None:
    """Verify that OpenWakeWord can be imported."""
    print("\n[INFO] Verifying OpenWakeWord...")

    run_command([
        "uv",
        "run",
        "python",
        "-c",
        "from openwakeword.model import Model; print('OpenWakeWord import OK')",
    ])

    print("[OK] OpenWakeWord verified.")

def verify_dependencies() -> None:
    """Verify that all required Jarvis packages can be imported."""
    print("\n[INFO] Verifying Jarvis dependencies...")

    packages = {
        "PyQt6": "from PyQt6.QtWidgets import QApplication",
        "qasync": "import qasync",
        "faster-whisper": "import faster_whisper",
        "sounddevice": "import sounddevice",
        "numpy": "import numpy",
        "torch": "import torch",
        "torchaudio": "import torchaudio",
        "ollama": "import ollama",
        "piper": "import piper",
        "silero-vad": "import silero_vad",
        "OpenWakeWord": "from openwakeword.model import Model",
        "psutil": "import psutil",
        "pycaw": "import pycaw",
        "onnxruntime": "import onnxruntime",
        "openwakeword": "import openwakeword",
    }

    failed = []

    for name, import_statement in packages.items():
        print(f"  Checking {name}...", end=" ")

        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-c",
                import_statement,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print("OK")
        else:
            print("FAILED")
            failed.append(name)

    if failed:
        print("\n[ERROR] Missing or broken dependencies:")

        for package in failed:
            print(f"  - {package}")

        sys.exit(1)

    print("\n[OK] All Jarvis dependencies verified.")

def validate_environment_file() -> None:
    """Check that the .env file exists and is readable."""
    print("\n[INFO] Validating environment configuration...")

    env_file = Path(".env")

    if not env_file.exists():
        print("[ERROR] .env file does not exist.")
        sys.exit(1)

    if not env_file.is_file():
        print("[ERROR] .env exists but is not a file.")
        sys.exit(1)

    try:
        env_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[ERROR] Could not read .env: {exc}")
        sys.exit(1)

    print("[OK] .env is readable.")

def save_installation_state() -> None:
    """Save information about the successful Jarvis installation."""
    print("\n[INFO] Saving installation state...")

    state_dir = Path(".jarvis")
    state_dir.mkdir(exist_ok=True)

    state = {
        "version": "0.1.0",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": platform.system(),
        "environment_ready": True,
    }

    state_file = state_dir / "install.json"

    state_file.write_text(
        json.dumps(state, indent=4),
        encoding="utf-8",
    )

    print(f"[OK] Installation state saved to {state_file}")

def is_already_installed() -> bool:
    """Check whether Jarvis has already been successfully installed."""
    state_file = Path(".jarvis") / "install.json"

    if not state_file.exists():
        return False

    try:
        state = json.loads(
            state_file.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False

    return state.get("environment_ready") is True

def quick_check() -> None:
    """Perform lightweight checks for an existing installation."""
    print("\n[INFO] Existing Jarvis installation detected.")
    print("[INFO] Running quick environment check...")

    check_windows()
    check_python()
    check_uv()

    print("\n[OK] Jarvis environment looks good.")
    
def main() -> None:
    print("=" * 60)
    print("        JARVIS BOOTSTRAPPER")
    print("=" * 60)

    if is_already_installed():
        quick_check()

        print("\n[OK] Jarvis is already installed.")
        print("[INFO] No full dependency verification required.")
        return

    print("\n[INFO] First-time installation detected.")

    check_windows()
    check_python()
    check_uv()

    setup_environment()
    install_openwakeword()
    setup_wake_word_models()

    verify_openwakeword()
    verify_dependencies()

    setup_environment_file()
    validate_environment_file()

    save_installation_state()

    print("\n[OK] Jarvis installation completed successfully.")

if __name__ == "__main__":
    main()