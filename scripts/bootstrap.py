#!/usr/bin/env python3
"""
bootstrap.py – ULTRON Agent Bootstrap Script
=============================================
Checks for required software, installs missing dependencies,
and requests elevated permissions when needed.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(text: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}\n")


def print_step(text: str) -> None:
    print(f"{Colors.BLUE}>> {Colors.RESET}{text}")


def print_success(text: str) -> None:
    print(f"{Colors.GREEN}[OK] {Colors.RESET}{text}")


def print_warning(text: str) -> None:
    print(f"{Colors.YELLOW}[WARN] {Colors.RESET}{text}")


def print_error(text: str) -> None:
    print(f"{Colors.RED}[ERR] {Colors.RESET}{text}")


def print_info(text: str) -> None:
    print(f"{Colors.CYAN}[INFO] {Colors.RESET}{text}")


def ask_permission(prompt: str) -> bool:
    """Ask user for yes/no permission."""
    while True:
        response = input(f"{Colors.YELLOW}? {prompt} [y/N]: {Colors.RESET}").strip().lower()
        if response in ("y", "yes"):
            return True
        if response in ("n", "no", ""):
            return False
        print_warning("Please answer 'y' or 'n'")


def run_command(cmd: list[str], capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        if capture:
            return subprocess.run(cmd, capture_output=True, text=True, check=check)
        return subprocess.run(cmd, check=check)
    except subprocess.CalledProcessError as e:
        if capture:
            return e
        raise


def check_command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


def get_python_version() -> tuple[int, int]:
    """Get Python major and minor version."""
    return sys.version_info.major, sys.version_info.minor


def check_python_version(min_major: int = 3, min_minor: int = 12) -> bool:
    """Check if Python version meets minimum requirements."""
    major, minor = get_python_version()
    if major > min_major or (major == min_major and minor >= min_minor):
        print_success(f"Python {major}.{minor} (>= {min_major}.{min_minor} required)")
        return True
    print_error(f"Python {major}.{minor} found, but {min_major}.{min_minor}+ is required")
    return False


def check_venv() -> bool:
    """Check if running inside a virtual environment."""
    in_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    if in_venv:
        print_success("Running inside virtual environment")
    else:
        print_warning("Not running inside a virtual environment")
    return in_venv


def create_venv(venv_path: Path) -> bool:
    """Create a virtual environment."""
    print_step(f"Creating virtual environment at {venv_path}...")
    try:
        venv.create(venv_path, with_pip=True)
        print_success("Virtual environment created")
        return True
    except Exception as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False


def get_pip_cmd(venv_path: Optional[Path] = None) -> list[str]:
    """Get the pip command for the current or specified environment."""
    if venv_path:
        if platform.system() == "Windows":
            return [str(venv_path / "Scripts" / "python.exe"), "-m", "pip"]
        return [str(venv_path / "bin" / "python"), "-m", "pip"]
    return [sys.executable, "-m", "pip"]


def install_pip_packages(pip_cmd: list[str], packages: list[str], upgrade: bool = True) -> bool:
    """Install Python packages using pip."""
    cmd = pip_cmd + ["install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)

    print_step(f"Installing packages: {', '.join(packages)}")
    try:
        run_command(cmd)
        print_success("Packages installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install packages: {e}")
        return False


def check_system_dependencies() -> dict[str, bool]:
    """Check for system-level dependencies."""
    deps = {
        "git": check_command_exists("git"),
        "curl": check_command_exists("curl"),
        "wget": check_command_exists("wget"),
    }

    # Check for audio dependencies (PortAudio)
    system = platform.system()
    if system == "Linux":
        deps["portaudio"] = check_command_exists("pkg-config") and run_command(
            ["pkg-config", "--exists", "portaudio-2.0"], check=False
        ).returncode == 0
        deps["ffmpeg"] = check_command_exists("ffmpeg")
    elif system == "Darwin":  # macOS
        deps["portaudio"] = check_command_exists("brew") and run_command(
            ["brew", "list", "portaudio"], check=False
        ).returncode == 0
        deps["ffmpeg"] = check_command_exists("ffmpeg")
    elif system == "Windows":
        deps["portaudio"] = True  # pyaudio wheels include PortAudio
        deps["ffmpeg"] = check_command_exists("ffmpeg")

    return deps


def install_system_dependencies(deps: dict[str, bool]) -> bool:
    """Install missing system dependencies."""
    missing = [name for name, installed in deps.items() if not installed]
    if not missing:
        print_success("All system dependencies are satisfied")
        return True

    print_warning(f"Missing system dependencies: {', '.join(missing)}")

    system = platform.system()
    if system == "Linux":
        # Try to detect package manager
        if check_command_exists("apt"):
            if not ask_permission("Install missing dependencies using apt (requires sudo)?"):
                return False
            print_step("Updating package list...")
            run_command(["sudo", "apt", "update"])
            packages = []
            if "portaudio" in missing:
                packages.append("portaudio19-dev")
            if "ffmpeg" in missing:
                packages.append("ffmpeg")
            if "git" in missing:
                packages.append("git")
            if "curl" in missing:
                packages.append("curl")
            if packages:
                print_step(f"Installing: {', '.join(packages)}")
                run_command(["sudo", "apt", "install", "-y"] + packages)
        elif check_command_exists("dnf"):
            if not ask_permission("Install missing dependencies using dnf (requires sudo)?"):
                return False
            packages = []
            if "portaudio" in missing:
                packages.append("portaudio-devel")
            if "ffmpeg" in missing:
                packages.append("ffmpeg")
            if packages:
                run_command(["sudo", "dnf", "install", "-y"] + packages)
        elif check_command_exists("pacman"):
            if not ask_permission("Install missing dependencies using pacman (requires sudo)?"):
                return False
            packages = []
            if "portaudio" in missing:
                packages.append("portaudio")
            if "ffmpeg" in missing:
                packages.append("ffmpeg")
            if packages:
                run_command(["sudo", "pacman", "-S", "--noconfirm"] + packages)
        else:
            print_error("Unsupported Linux distribution. Please install dependencies manually.")
            return False

    elif system == "Darwin":
        if not check_command_exists("brew"):
            print_error("Homebrew not found. Please install Homebrew first: https://brew.sh")
            return False
        if not ask_permission("Install missing dependencies using Homebrew?"):
            return False
        packages = []
        if "portaudio" in missing:
            packages.append("portaudio")
        if "ffmpeg" in missing:
            packages.append("ffmpeg")
        if "git" in missing:
            packages.append("git")
        if packages:
            run_command(["brew", "install"] + packages)

    elif system == "Windows":
        print_info("On Windows, most dependencies are bundled with Python wheels.")
        print_info("For ffmpeg, you can download from https://ffmpeg.org/download.html")
        print_info("For git, download from https://git-scm.com/download/win")
        if "ffmpeg" in missing and not ask_permission("Open ffmpeg download page in browser?"):
            pass
        else:
            import webbrowser
            webbrowser.open("https://ffmpeg.org/download.html")

    print_success("System dependencies handled")
    return True


def check_cuda() -> bool:
    """Check for CUDA availability."""
    try:
        result = run_command(["nvidia-smi"], capture=True, check=False)
        if result.returncode == 0:
            print_success("NVIDIA GPU detected (CUDA available)")
            return True
    except FileNotFoundError:
        pass
    print_warning("No NVIDIA GPU detected (CPU-only mode)")
    return False


def install_python_dependencies(project_root: Path, venv_path: Optional[Path] = None) -> bool:
    """Install Python dependencies from pyproject.toml and requirements.txt."""
    pip_cmd = get_pip_cmd(venv_path)

    # Upgrade pip first
    print_step("Upgrading pip...")
    run_command(pip_cmd + ["install", "--upgrade", "pip"])

    # Install from pyproject.toml
    print_step("Installing project dependencies from pyproject.toml...")
    try:
        run_command(pip_cmd + ["install", "-e", str(project_root)])
        print_success("Project dependencies installed")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install project dependencies: {e}")
        return False

    # Install speech requirements
    speech_req = project_root / "speech" / "requirements.txt"
    if speech_req.exists():
        print_step("Installing speech dependencies...")
        try:
            run_command(pip_cmd + ["install", "-r", str(speech_req)])
            print_success("Speech dependencies installed")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install speech dependencies: {e}")
            return False

    return True


def setup_env_file(project_root: Path) -> bool:
    """Set up .env file from example if it doesn't exist."""
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if env_file.exists():
        print_success(".env file already exists")
        return True

    if env_example.exists():
        print_step("Creating .env file from .env.example...")
        shutil.copy(env_example, env_file)
        print_success(".env file created")
        print_warning("Please edit .env file to add your API keys (Picovoice, NVIDIA, etc.)")
        return True

    print_warning("No .env.example found, creating empty .env")
    env_file.touch()
    return True


def ollama_available() -> bool:
    return check_command_exists("ollama")


def ollama_has_model(model: str) -> bool:
    """True when the model is already pulled, so we do not re-download it."""
    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=30
        )
        return out.returncode == 0 and model in out.stdout
    except Exception:
        return False


def setup_local_model(project_root: Path, assume_yes: bool = False) -> bool:
    """Detect hardware, choose a fitting local model, and offer to pull it.

    The model is chosen from the machine's RAM/VRAM/disk rather than hardcoded,
    so a thin laptop and a workstation each get something usable.
    """
    sys.path.insert(0, str(project_root))
    try:
        from utils.model_picker import describe, detect_specs
    except Exception as exc:
        print_warning(f"Could not load the model picker ({exc}); skipping.")
        return False

    specs = detect_specs()
    for line in describe(specs).splitlines():
        print_info(line)

    if specs["low_disk"]:
        print_warning(
            f"Only {specs['free_disk_gb']} GB free - picked the smallest model."
        )

    if not ollama_available():
        print_warning("Ollama is not installed, so no model can be pulled.")
        print_info("Install it from https://ollama.com/download, then run:")
        print_info(f"  ollama pull {specs['model']}")
        return False

    if ollama_has_model(specs["model"]):
        print_success(f"{specs['model']} is already installed.")
        write_model_to_env(project_root, specs["model"])
        return True

    prompt = (
        f"Download {specs['model']} (~{specs['approx_gb']} GB) now?"
    )
    if not (assume_yes or ask_permission(prompt)):
        print_info(f"Skipped. You can pull it later with: ollama pull {specs['model']}")
        write_model_to_env(project_root, specs["model"])
        return False

    print_step(f"Pulling {specs['model']} (this can take several minutes)...")
    try:
        result = subprocess.run(["ollama", "pull", specs["model"]], check=False)
        if result.returncode != 0:
            print_error(f"ollama pull failed for {specs['model']}.")
            return False
    except Exception as exc:
        print_error(f"Could not run ollama pull: {exc}")
        return False

    print_success(f"{specs['model']} installed.")
    write_model_to_env(project_root, specs["model"])
    return True


def write_model_to_env(project_root: Path, model: str) -> None:
    """Point QWEN_MODEL at the chosen model, preserving the rest of .env."""
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        print_warning(f"Could not read .env: {exc}")
        return

    out, replaced = [], False
    for line in lines:
        if line.strip().startswith("QWEN_MODEL="):
            out.append(f"QWEN_MODEL={model}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"QWEN_MODEL={model}")

    try:
        env_path.write_text(chr(10).join(out) + chr(10), encoding="utf-8")
        print_success(f"Set QWEN_MODEL={model} in .env")
    except Exception as exc:
        print_warning(f"Could not update .env: {exc}")


def print_next_steps(project_root: Path, venv_path: Optional[Path] = None) -> None:
    """Print next steps for the user."""
    print_header("Bootstrap Complete!")
    print(f"{Colors.GREEN}ULTRON Agent is ready to run.{Colors.RESET}\n")

    if venv_path:
        if platform.system() == "Windows":
            activate = venv_path / "Scripts" / "activate.bat"
            run_cmd = f"{venv_path}\\Scripts\\python -m ULTRON"
        else:
            activate = venv_path / "bin" / "activate"
            run_cmd = f"source {activate} && python -m ULTRON"
        print(f"{Colors.CYAN}To activate the virtual environment:{Colors.RESET}")
        print(f"  {Colors.WHITE}{activate}{Colors.RESET}\n")

    print(f"{Colors.CYAN}To run ULTRON:{Colors.RESET}")
    print(f"  {Colors.WHITE}python -m ULTRON{Colors.RESET}          (text mode)")
    print(f"  {Colors.WHITE}python run.py --mode wakeword{Colors.RESET}  (voice with wake word)")
    print(f"  {Colors.WHITE}python run.py --mode no-wake{Colors.RESET}   (continuous voice)\n")

    print(f"{Colors.CYAN}Configuration:{Colors.RESET}")
    print(f"  Edit {Colors.WHITE}{project_root / '.env'}{Colors.RESET} to add API keys")
    print(f"  - Picovoice Access Key (for wake word)")
    print(f"  - NVIDIA API Key (for LLM)")
    print(f"  - Ollama URL (for local LLM)\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ULTRON Agent Bootstrap Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Skip virtual environment creation/use",
    )
    parser.add_argument(
        "--venv-path",
        type=Path,
        default=Path(".venv"),
        help="Path for virtual environment (default: .venv)",
    )
    parser.add_argument(
        "--skip-system",
        action="store_true",
        help="Skip system dependency checks",
    )
    parser.add_argument(
        "--skip-python",
        action="store_true",
        help="Skip Python package installation",
    )
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Skip local model detection and download",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Assume yes to all prompts",
    )

    args = parser.parse_args()

    # Override ask_permission if --yes flag is used
    global ask_permission
    if args.yes:
        ask_permission = lambda _: True

    project_root = Path(__file__).parent.absolute()
    venv_path = args.venv_path if not args.no_venv else None

    print_header("ULTRON Agent Bootstrap")

    # 1. Check Python version
    print_step("Checking Python version...")
    if not check_python_version(3, 12):
        print_error("Please install Python 3.12 or higher")
        return 1

    # 2. Check/Create virtual environment
    if venv_path:
        if not venv_path.exists():
            print_step("Virtual environment not found")
            if ask_permission(f"Create virtual environment at {venv_path}?"):
                if not create_venv(venv_path):
                    return 1
            else:
                print_warning("Continuing without virtual environment")
                venv_path = None
        else:
            print_success(f"Virtual environment found at {venv_path}")

    # 3. Check system dependencies
    if not args.skip_system:
        print_step("Checking system dependencies...")
        deps = check_system_dependencies()
        for name, installed in deps.items():
            if installed:
                print_success(f"{name} found")
            else:
                print_warning(f"{name} not found")
        if not install_system_dependencies(deps):
            print_warning("Some system dependencies may be missing")

    # 4. Check CUDA
    print_step("Checking GPU support...")
    check_cuda()

    # 5. Install Python dependencies
    if not args.skip_python:
        print_step("Installing Python dependencies...")
        if not install_python_dependencies(project_root, venv_path):
            return 1

    # 6. Setup .env file
    print_step("Setting up configuration...")
    setup_env_file(project_root)

    # 7. Pick and install a local model that fits this machine
    if not args.skip_model:
        print_step("Selecting a local model for this machine...")
        setup_local_model(project_root, assume_yes=args.yes)

    # 8. Print next steps
    print_next_steps(project_root, venv_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())