"""Shell completion for @tags, plus the `bt completion` helper command."""

import click
from click.shell_completion import CompletionItem


def _known_tags() -> list[str]:
    """All tags from the index. Never raises, never prints — completion must stay silent."""
    try:
        from bute.config import get_data_dir, load_config
        from bute.db import all_tags
        config = load_config()
        if not (get_data_dir(config) / ".index" / "bute.db").exists():
            return []  # a fresh DB would auto-rebuild and print — never during completion
        return all_tags(config)
    except Exception:
        return []


def complete_tags(ctx, param, incomplete: str) -> list[CompletionItem]:
    """Complete '@ba' → '@backend'. Anything not starting with '@' gets no suggestions."""
    if not incomplete.startswith("@"):
        return []
    prefix = incomplete[1:]
    return [CompletionItem(f"@{t}") for t in _known_tags() if t.startswith(prefix)]


_RC_LINE = {
    "zsh": 'eval "$(_BT_COMPLETE=zsh_source bt)"',
    "bash": 'eval "$(_BT_COMPLETE=bash_source bt)"',
    "fish": '_BT_COMPLETE=fish_source bt | source',
}
_RC_FILE = {"zsh": "~/.zshrc", "bash": "~/.bashrc", "fish": "~/.config/fish/completions/bt.fish"}


@click.command("completion")
@click.argument("shell", required=False, default="zsh", type=click.Choice(list(_RC_LINE)))
def completion_cmd(shell):
    """Print the line that enables tab completion for your shell (default zsh)."""
    click.echo(f"  Add this to {_RC_FILE[shell]}, then open a new shell:")
    click.echo()
    click.echo(f"    {_RC_LINE[shell]}")
    click.echo()
    click.echo("  Then: bt t call den @ba<TAB>  →  @backend")
