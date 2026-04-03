"""Init command — first-run setup for bute."""

import subprocess
import sys

import click
from rich.console import Console

from bute.config import (
    PROVIDER_PRESETS,
    default_config,
    ensure_data_dirs,
    get_config_path,
    save_config,
)

console = Console()


def _store_api_key(provider: str, api_key: str) -> str:
    """Store API key in macOS Keychain. Returns the config value to use."""
    service = f"bute-{provider}-api-key"
    if sys.platform == "darwin":
        try:
            # Delete existing entry if any
            subprocess.run(
                ["security", "delete-generic-password", "-s", service, "-a", "bute"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        try:
            result = subprocess.run(
                ["security", "add-generic-password", "-s", service, "-a", "bute", "-w", api_key],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                console.print(f"  [green]API key saved to macOS Keychain ({service})[/green]")
                return f"keychain:{service}"
        except Exception:
            pass
    # Fallback: store directly in config
    console.print("  [dim]API key saved to config file.[/dim]")
    return api_key


def _prompt_api_key(provider: str) -> str | None:
    """Prompt for API key and store it. Returns config value or None to skip."""
    preset = PROVIDER_PRESETS.get(provider, {})
    if not preset.get("needs_api_key", True):
        return ""

    console.print(f"\n  [dim]Get your API key from your {provider} dashboard.[/dim]")
    api_key = click.prompt("  API key", hide_input=True, default="", show_default=False)

    if not api_key:
        console.print("  [dim]Skipped. Add it later in ~/.config/bute/config.toml[/dim]")
        return ""

    return _store_api_key(provider, api_key)

# Cloud provider choices (shown when user picks Cloud AI)
CLOUD_PROVIDERS = [
    ("anthropic", "Anthropic (Claude)"),
    ("openai", "OpenAI (GPT)"),
    ("gemini", "Gemini (Google)"),
    ("deepseek", "DeepSeek"),
    ("custom", "Custom (OpenAI-compatible endpoint)"),
]

# Top-level AI setup choices
AI_SETUP_CHOICES = [
    "Local AI (Gemma 4 — free, private, no account needed)",
    "Cloud AI (Anthropic, OpenAI, etc.)",
    "No AI (core features only)",
]


@click.command("init")
@click.option("--provider", type=str, default=None, help="AI provider name.")
@click.option("--model", type=str, default=None, help="Model name.")
@click.option("--base-url", type=str, default=None, help="Custom API base URL.")
@click.pass_context
def init_cmd(ctx, provider, model, base_url):
    """Initialize bt — create config and data directories."""
    config_path = get_config_path()

    if config_path.exists():
        if not click.confirm("Config already exists. Reinitialize?", default=False):
            return

    # Non-interactive mode (flags provided)
    if provider is not None:
        _save_and_finish(provider, model, base_url, config_path)
        return

    # Interactive mode
    try:
        import questionary

        choice = questionary.select(
            "How do you want to set up AI?",
            choices=AI_SETUP_CHOICES,
        ).ask()

        if choice is None:
            raise click.Abort()

        if choice == AI_SETUP_CHOICES[0]:
            # Local AI — Gemma 4 via Ollama
            _setup_local_ai(config_path)

        elif choice == AI_SETUP_CHOICES[1]:
            # Cloud AI — pick a provider
            _setup_cloud_ai(config_path)

        else:
            # No AI
            _save_and_finish("ollama", "", None, config_path)
            console.print("  [dim]AI disabled. Core features work fine without it.[/dim]")
            console.print("  [dim]Run bt init anytime to enable AI.[/dim]")

    except ImportError:
        # questionary not available — fall back to click prompts
        console.print("\n  [bold]AI setup:[/bold]")
        console.print("  1. Local AI (Gemma 4 — free, private)")
        console.print("  2. Cloud AI (Anthropic, OpenAI, etc.)")
        console.print("  3. No AI")
        ai_choice = click.prompt("Choose", type=click.IntRange(1, 3), default=1)

        if ai_choice == 1:
            _setup_local_ai(config_path)
        elif ai_choice == 2:
            provider = click.prompt(
                "Cloud provider",
                type=click.Choice([k for k, _ in CLOUD_PROVIDERS]),
                default="anthropic",
            )
            preset = PROVIDER_PRESETS.get(provider, {})
            model = click.prompt("Model", default=preset.get("default_model", ""))
            api_key_value = _prompt_api_key(provider)
            _save_and_finish(provider, model, None, config_path, api_key=api_key_value)
        else:
            _save_and_finish("ollama", "", None, config_path)
            console.print("  [dim]AI disabled. Run bt init anytime to enable it.[/dim]")


def _setup_local_ai(config_path):
    """Install Ollama + Gemma 4 and configure bt."""
    console.print()
    from bute.ollama_setup import setup_local_ai

    if setup_local_ai():
        _save_and_finish("ollama", "gemma4:e4b", None, config_path)
        console.print("\n  [bold green]All AI features work offline. No account needed.[/bold green]")
    else:
        console.print("\n  [yellow]Local AI setup incomplete.[/yellow]")
        console.print("  [dim]bt will work without AI. Run bt init to try again.[/dim]")
        _save_and_finish("ollama", "gemma4:e4b", None, config_path)


def _setup_cloud_ai(config_path):
    """Pick a cloud provider, model, and API key."""
    try:
        import questionary

        choice = questionary.select(
            "Choose your cloud provider:",
            choices=[display for _, display in CLOUD_PROVIDERS],
        ).ask()

        if choice is None:
            raise click.Abort()

        provider = next(key for key, display in CLOUD_PROVIDERS if display == choice)
        preset = PROVIDER_PRESETS.get(provider, {})

        model = questionary.text(
            "Model?", default=preset.get("default_model", "")
        ).ask()
        if model is None:
            raise click.Abort()

        base_url = None
        if provider == "custom":
            base_url = questionary.text(
                "Base URL?", default="http://localhost:8080/v1"
            ).ask()
            if base_url is None:
                raise click.Abort()

        api_key_value = _prompt_api_key(provider)
        _save_and_finish(provider, model, base_url, config_path, api_key=api_key_value)

    except ImportError:
        provider = click.prompt(
            "Cloud provider",
            type=click.Choice([k for k, _ in CLOUD_PROVIDERS]),
            default="anthropic",
        )
        preset = PROVIDER_PRESETS.get(provider, {})
        model = click.prompt("Model", default=preset.get("default_model", ""))
        api_key_value = _prompt_api_key(provider)
        _save_and_finish(provider, model, None, config_path, api_key=api_key_value)


def _save_and_finish(provider, model, base_url, config_path, api_key=""):
    """Save config, create data dirs, print success."""
    doc = default_config(provider=provider, model=model, base_url=base_url, api_key=api_key)
    save_config(doc)
    data_dir = ensure_data_dirs(doc)
    console.print(f"\n  [green]Config saved to {config_path}[/green]")
    console.print(f"  [green]Data directory at {data_dir}[/green]")
