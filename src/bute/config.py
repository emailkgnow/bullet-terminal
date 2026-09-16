"""Configuration management for bt."""

import shutil
from pathlib import Path

import tomlkit

CONFIG_DIR = Path.home() / ".config" / "bt"
LEGACY_CONFIG_DIR = Path.home() / ".config" / "bute"  # pre-rename installs
CONFIG_FILE = CONFIG_DIR / "config.toml"
DATA_DIR_DEFAULT = Path.home() / "bullet-terminal"
DEMO_DATA_DIR = Path.home() / "bt-demo"
TOUR_DONE = CONFIG_DIR / ".tour_done"

def get_config_path() -> Path:
    """Return the path to the config file."""
    return CONFIG_FILE


def get_data_dir(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Resolve the data directory from config or default."""
    if config and "core" in config and "data_dir" in config["core"]:
        return Path(config["core"]["data_dir"]).expanduser()
    return DATA_DIR_DEFAULT


def _migrate_legacy_config_dir() -> None:
    """One-time *copy* of ~/.config/bute/ → ~/.config/bt/. Silent; never clobbers.

    Copy, not move, deliberately: the legacy dir is left intact so that rolling the
    code back to `pre-rename` needs no manual filesystem repair. config.toml is 15
    lines — the duplicate costs nothing, and it holds the only setting that is
    painful to lose (`data_dir`, which points at the Obsidian vault).
    """
    if CONFIG_DIR.exists() or not LEGACY_CONFIG_DIR.exists():
        return
    CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(LEGACY_CONFIG_DIR, CONFIG_DIR)


def load_config() -> tomlkit.TOMLDocument:
    """Load config from disk. Returns empty doc if file doesn't exist."""
    _migrate_legacy_config_dir()
    if not CONFIG_FILE.exists():
        return tomlkit.document()
    return tomlkit.parse(CONFIG_FILE.read_text())


def save_config(doc: tomlkit.TOMLDocument) -> None:
    """Write config to disk, preserving comments."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(tomlkit.dumps(doc))


def default_config() -> tomlkit.TOMLDocument:
    """Generate a default config.toml with comments."""
    doc = tomlkit.document()
    doc.add(tomlkit.comment("bt (Bullet Terminal) configuration"))
    doc.add(tomlkit.nl())

    core = tomlkit.table()
    core.add(tomlkit.comment("Where entry files are stored"))
    core.add("data_dir", "~/bullet-terminal")
    core.add(tomlkit.comment("Day to trigger weekly plan: monday-sunday"))
    core.add("wp_day", "sunday")
    core.add(tomlkit.comment("First day of the week: monday-sunday"))
    core.add("week_start", "monday")
    doc.add("core", core)
    doc.add(tomlkit.nl())

    habits = tomlkit.table()
    habits.add(tomlkit.comment("Habits to track daily"))
    habits.add("list", tomlkit.array('["quran", "walking", "reading"]'))
    doc.add("habits", habits)

    return doc


DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def get_wp_day(config=None) -> int:
    """Return the weekday number (0=Mon, 6=Sun) for weekly plan trigger."""
    if config and "core" in config and "wp_day" in config["core"]:
        day_name = config["core"]["wp_day"].lower()
        return DAY_NAMES.get(day_name, 6)
    return 6  # default: Sunday


def get_week_start(config=None) -> int:
    """Return the weekday number (0=Mon, 6=Sun) for the first day of the week."""
    if config and "core" in config and "week_start" in config["core"]:
        day_name = config["core"]["week_start"].lower()
        return DAY_NAMES.get(day_name, 0)
    return 0  # default: Monday


def week_bounds(target, config=None):
    """Return (start, end) dates for the week containing target, per config."""
    from datetime import timedelta
    start_weekday = get_week_start(config)
    days_since_start = (target.weekday() - start_weekday) % 7
    start = target - timedelta(days=days_since_start)
    end = start + timedelta(days=6)
    return start, end


def _make_demo_config(config: tomlkit.TOMLDocument) -> tomlkit.TOMLDocument:
    """Create a demo config pointing to isolated demo data directory."""
    if "core" not in config:
        config["core"] = tomlkit.table()
    config["core"]["data_dir"] = str(DEMO_DATA_DIR)
    # Clear habits so real ones don't leak into demo
    if "habits" in config:
        config["habits"]["list"] = tomlkit.array("[]")
    return config


def ensure_data_dirs(config: tomlkit.TOMLDocument | None = None) -> Path:
    """Create the data directory structure. Returns the data dir path."""
    data_dir = get_data_dir(config)
    for subdir in ["entries", ".index"]:
        (data_dir / subdir).mkdir(parents=True, exist_ok=True)

    from bute.migration import needs_migration, migrate_entries
    if needs_migration(config):
        migrate_entries(config)

    from bute.guide import write_guide
    write_guide(data_dir)

    return data_dir
