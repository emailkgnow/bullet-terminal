"""Guided tour — interactive first-run onboarding for bt."""

import bute.config as _config


def is_tour_done() -> bool:
    """Check if the tour has been completed."""
    return _config.TOUR_DONE.exists()


def mark_tour_done() -> None:
    """Mark the tour as complete. Clears progress file."""
    _config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _config.TOUR_DONE.touch()
    if _config.TOUR_PROGRESS.exists():
        _config.TOUR_PROGRESS.unlink()


def load_tour_progress() -> int:
    """Load the current phase index (0-based). Returns 0 if no progress saved."""
    if not _config.TOUR_PROGRESS.exists():
        return 0
    try:
        return int(_config.TOUR_PROGRESS.read_text().strip())
    except (ValueError, OSError):
        return 0


def save_tour_progress(phase: int) -> None:
    """Save the current phase index for resume on Ctrl+C."""
    _config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _config.TOUR_PROGRESS.write_text(str(phase))
