"""Nudges command — AI-generated actionable suggestions."""

from datetime import date, timedelta

import click
from rich.console import Console

console = Console()


@click.command("nudges")
@click.option("--days", default=7, help="Days of history to analyze.")
@click.pass_context
def nudges_cmd(ctx, days):
    """AI analyzes recent entries and suggests actions."""
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send_with_entries
    from bute.ai.prompts import nudges_prompt

    config = ctx.obj.get("config")

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    from bute.storage import query_and_load

    cutoff = date.today() - timedelta(days=days)
    entries = query_and_load(config, created_since=cutoff.isoformat())

    if not entries:
        console.print(f"  [dim]No entries in the last {days} days.[/dim]")
        return

    # Truncate to avoid token limits
    entries = entries[:50]

    console.print(f"  [dim]Analyzing {len(entries)} entries from the last {days} days...[/dim]")
    response = llm_send_with_entries(
        nudges_prompt(), entries, "Generate nudges", config
    )
    from bute.display import display_ai_response
    display_ai_response(response)
