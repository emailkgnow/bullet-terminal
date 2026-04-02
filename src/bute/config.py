"""Configuration management for bute."""

from pathlib import Path

import tomlkit

CONFIG_DIR = Path.home() / ".config" / "bute"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DATA_DIR_DEFAULT = Path.home() / "bullet-terminal"

# Known AI provider presets
PROVIDER_PRESETS = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3",
        "needs_api_key": False,
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/",
        "default_model": "claude-sonnet-4-20250514",
        "needs_api_key": True,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "needs_api_key": True,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "needs_api_key": True,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "needs_api_key": True,
    },
}


def get_config_path() -> Path:
    """Return the path to the config file."""
    return CONFIG_FILE


def get_data_dir(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Resolve the data directory from config or default."""
    if config and "core" in config and "data_dir" in config["core"]:
        return Path(config["core"]["data_dir"]).expanduser()
    return DATA_DIR_DEFAULT


def load_config() -> tomlkit.TOMLDocument:
    """Load config from disk. Returns empty doc if file doesn't exist."""
    if not CONFIG_FILE.exists():
        return tomlkit.document()
    return tomlkit.parse(CONFIG_FILE.read_text())


def save_config(doc: tomlkit.TOMLDocument) -> None:
    """Write config to disk, preserving comments."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(tomlkit.dumps(doc))


def default_config(
    provider: str = "ollama",
    model: str | None = None,
    base_url: str | None = None,
) -> tomlkit.TOMLDocument:
    """Generate a default config.toml with comments."""
    preset = PROVIDER_PRESETS.get(provider, {})

    doc = tomlkit.document()
    doc.add(tomlkit.comment("bute (BuTe) configuration"))
    doc.add(tomlkit.nl())

    core = tomlkit.table()
    core.add(tomlkit.comment("Where entry files are stored"))
    core.add("data_dir", "~/bullet-terminal")
    doc.add("core", core)
    doc.add(tomlkit.nl())

    ai = tomlkit.table()
    ai.add(tomlkit.comment("AI provider: ollama, anthropic, openai, gemini, deepseek, or custom"))
    ai.add("provider", provider)
    ai.add("model", model or preset.get("default_model", ""))
    ai.add("base_url", base_url or preset.get("base_url", ""))
    ai.add(tomlkit.comment("For API key, use a command that prints it (e.g., keychain lookup)"))
    ai.add("api_key", "")
    doc.add("ai", ai)
    doc.add(tomlkit.nl())

    habits = tomlkit.table()
    habits.add(tomlkit.comment("Habits to track daily"))
    habits.add("list", tomlkit.array('["quran", "walking", "reading"]'))
    doc.add("habits", habits)

    return doc


def ensure_data_dirs(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Create the data directory structure. Returns the data dir path."""
    data_dir = get_data_dir(config)
    for subdir in ["entries", "collections", "habits", ".index"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)
    return data_dir
