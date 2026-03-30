"""Error types for bute."""

import click


class DwnError(click.ClickException):
    """Base error for bute."""

    def format_message(self):
        return self.message


class ConfigNotFoundError(DwnError):
    """Raised when config.toml doesn't exist and is required."""

    def __init__(self):
        super().__init__("bt is not initialized. Run 'bt init' first.")


class EntryNotFoundError(DwnError):
    """Raised when a referenced entry doesn't exist."""

    pass


class InvalidSignifierError(DwnError):
    """Raised when an unrecognized signifier is used."""

    pass


class StateNotFoundError(DwnError):
    """Raised when no view state exists (no previous list displayed)."""

    def __init__(self):
        super().__init__("No active view. Run 'bt ls' first to see entries.")


class InvalidActionError(DwnError):
    """Raised when an unrecognized action is used."""

    pass


class InvalidEntryNumberError(DwnError):
    """Raised when a referenced entry number is out of range."""

    pass


class InvalidHabitError(DwnError):
    """Raised when a habit name is not in the configured list."""

    pass
