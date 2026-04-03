"""Automated Ollama + Gemma 4 setup for bt."""

import shutil
import subprocess
import sys
import time

from rich.console import Console

console = Console()

MODEL = "gemma4:e4b"


def is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def is_ollama_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def is_model_pulled() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        return MODEL.split(":")[0] in result.stdout and (
            MODEL.split(":")[1] in result.stdout if ":" in MODEL else True
        )
    except Exception:
        return False


MIN_OLLAMA_VERSION = "0.20.0"


def _get_ollama_version() -> str:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        # "ollama version is 0.20.0"
        return result.stdout.strip().rsplit(" ", 1)[-1]
    except Exception:
        return "0.0.0"


def _version_tuple(v: str):
    return tuple(int(x) for x in v.split("."))


def _needs_upgrade() -> bool:
    current = _get_ollama_version()
    return _version_tuple(current) < _version_tuple(MIN_OLLAMA_VERSION)


def upgrade_ollama() -> bool:
    console.print("  [cyan]Upgrading Ollama (Gemma 4 needs v0.20+)...[/cyan]")
    try:
        result = subprocess.run(
            ["brew", "upgrade", "ollama"],
            timeout=300,
        )
        if result.returncode == 0:
            subprocess.run(["brew", "services", "restart", "ollama"], timeout=30)
            time.sleep(3)
        return result.returncode == 0
    except Exception as e:
        console.print(f"  [red]Upgrade failed: {e}[/red]")
        return False


def install_ollama() -> bool:
    console.print("  [cyan]Installing Ollama via Homebrew...[/cyan]")
    try:
        result = subprocess.run(
            ["brew", "install", "ollama"],
            timeout=300,
        )
        return result.returncode == 0
    except FileNotFoundError:
        console.print("  [red]Homebrew not found.[/red]")
        console.print("  Install Ollama manually: [bold]https://ollama.com/download[/bold]")
        return False
    except Exception as e:
        console.print(f"  [red]Installation failed: {e}[/red]")
        return False


def start_ollama() -> bool:
    console.print("  [cyan]Starting Ollama...[/cyan]")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for it to come up
        for _ in range(15):
            time.sleep(1)
            if is_ollama_running():
                return True
        console.print("  [red]Ollama didn't start in time.[/red]")
        return False
    except Exception as e:
        console.print(f"  [red]Failed to start Ollama: {e}[/red]")
        return False


def pull_model() -> bool:
    console.print(f"  [cyan]Pulling {MODEL} (9.6 GB one-time download)...[/cyan]")
    try:
        result = subprocess.run(
            ["ollama", "pull", MODEL],
            timeout=1800,  # 30 min for slow connections
        )
        return result.returncode == 0
    except Exception as e:
        console.print(f"  [red]Model pull failed: {e}[/red]")
        return False


def setup_local_ai() -> bool:
    """Full automated setup: install Ollama, start it, pull Gemma 4 E4B.

    Returns True if everything is ready.
    """
    # Step 1: Ollama installed?
    if not is_ollama_installed():
        if not install_ollama():
            return False
        console.print("  [green]Ollama installed.[/green]")
    else:
        console.print("  [green]Ollama already installed.[/green]")
        # Check if upgrade needed
        if _needs_upgrade():
            if not upgrade_ollama():
                return False
            console.print("  [green]Ollama upgraded.[/green]")

    # Step 2: Ollama running?
    if not is_ollama_running():
        if not start_ollama():
            return False
        console.print("  [green]Ollama running.[/green]")
    else:
        console.print("  [green]Ollama already running.[/green]")

    # Step 3: Model pulled?
    if not is_model_pulled():
        if not pull_model():
            return False
        console.print(f"  [green]{MODEL} ready.[/green]")
    else:
        console.print(f"  [green]{MODEL} already available.[/green]")

    return True
