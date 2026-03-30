"""Init command — first-run setup for bute."""

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

# Provider display names for interactive selection
PROVIDER_CHOICES = [
    ("ollama", "Ollama (local, free, private)"),
    ("anthropic", "Anthropic (Claude)"),
    ("openai", "OpenAI (GPT)"),
    ("gemini", "Gemini (Google)"),
    ("deepseek", "DeepSeek"),
    ("custom", "Custom (OpenAI-compatible endpoint)"),
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

    # Interactive mode if --provider not given
    if provider is None:
        try:
            import questionary

            choice = questionary.select(
                "Choose your AI provider:",
                choices=[display for _, display in PROVIDER_CHOICES],
            ).ask()

            if choice is None:  # user cancelled
                raise click.Abort()

            # Map display name back to key
            provider = next(
                key for key, display in PROVIDER_CHOICES if display == choice
            )

            preset = PROVIDER_PRESETS.get(provider, {})
            default_model = preset.get("default_model", "")

            model = questionary.text(
                "Model?", default=default_model
            ).ask()

            if model is None:
                raise click.Abort()

            if provider == "custom":
                base_url = questionary.text(
                    "Base URL?", default="http://localhost:8080/v1"
                ).ask()
                if base_url is None:
                    raise click.Abort()

        except ImportError:
            # questionary not available, use click prompts as fallback
            provider = click.prompt(
                "AI provider",
                type=click.Choice([k for k, _ in PROVIDER_CHOICES]),
                default="ollama",
            )
            preset = PROVIDER_PRESETS.get(provider, {})
            model = click.prompt("Model", default=preset.get("default_model", ""))

    doc = default_config(provider=provider, model=model, base_url=base_url)
    save_config(doc)

    data_dir = ensure_data_dirs(doc)

    console.print(f"\n[green]Config saved to {config_path}[/green]")
    console.print(f"[green]Data directory created at {data_dir}[/green]")
