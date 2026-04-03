# Merge Recap & Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `bt recap` and `bt review` into a single `bt recap [period]` command that shows structured daily display when no arg is given, and runs the full analyze pipeline (tree + confirm + save note + offer mind map) when a period is specified.

**Architecture:** `bt recap` (no arg) keeps the existing structured display (done/open/dropped/captured/habits) with no AI. `bt recap day|week|month|year` gathers entries for the period and calls the existing `_run_analyze()` from `commands/tags.py` with a synthetic label like `today`, `this-week`, `this-month`, `this-year`. The `bt review` command and `review_prompt()` are deleted.

**Tech Stack:** Python, Click, Rich

---

### Task 1: Make `_run_analyze()` accept a label override

`_run_analyze()` currently uses the `tag` parameter for display labels, note tags, and `upsert_tag_stage()`. For period-based recap, we need it to accept entries directly (instead of loading by tag) and use a display label that isn't a real tag.

**Files:**
- Modify: `src/bute/commands/tags.py:36-77`

- [ ] **Step 1: Add `label` and `entries` parameters to `_run_analyze()`**

Change the signature and internals so it can be called with pre-loaded entries and a custom label instead of a tag name:

```python
def _run_analyze(tag: str, entries, config, *, label: str | None = None) -> str | None:
    """Run the analyze stage. Returns analysis text or None if rejected.

    Args:
        tag: The tag name (used for tag_stages and note tagging).
             Pass empty string when using label override.
        entries: Pre-loaded entries to analyze.
        config: App config.
        label: Display label override. If set, used in display and note body
               instead of tag. tag_stages is skipped when label is set.
    """
    from bute.ai import _LLM_INSTALL_MSG, is_llm_available, llm_send
    from bute.ai.prompts import analyze_prompt, format_entries

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return None

    display_name = label or tag
    console.print(f"  [dim]Analyzing {len(entries)} entries for @{display_name}...[/dim]")

    formatted = format_entries(entries)
    response = llm_send(analyze_prompt(), f"Tag: \"@{display_name}\"\n\nEntries:\n{formatted}", config)
    from bute.display import display_analyze_tree
    display_analyze_tree(display_name, response)

    if click.confirm("\n  Accept this analysis?", default=True):
        if tag:
            upsert_tag_stage(tag, "analyzed", analysis=response, config=config)

        # Save analysis as a note for future reference
        from bute.ai import embed_entry
        from bute.display import confirm_capture
        from bute.models import Entry, EntryType
        from bute.storage import save_entry

        note_tags = [tag, "ai-analysis"] if tag else [display_name, "ai-analysis"]
        entry = Entry.create(
            entry_type=EntryType.NOTE,
            body=_format_analysis_for_note(display_name, response),
            tags=note_tags,
        )
        save_entry(entry, config)
        embed_entry(entry.id, entry.body, config)
        confirm_capture(entry)

        console.print(f"  [green]@{display_name} → analyzed[/green]")

        # Offer mind map view
        if click.confirm("  View as mind map?", default=False):
            from bute.display import display_analyze_map
            display_analyze_map(display_name, response)

        return response
    else:
        console.print(f"  [dim]Analysis discarded. Run analyze again when ready.[/dim]")
        return None
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `uv run pytest tests/test_rituals.py -v`
Expected: All existing tests pass (recap tests use `-q` flag which we haven't removed yet, but they should still pass at this step since we only changed `_run_analyze`).

- [ ] **Step 3: Commit**

```bash
git add src/bute/commands/tags.py
git commit -m "refactor: add label override to _run_analyze for period-based analysis"
```

---

### Task 2: Rewrite `recap_cmd` to support optional period argument

Replace the current `recap_cmd` with a new version: no arg = structured display (no AI, no `-q` flag), with period arg = analyze pipeline.

**Files:**
- Modify: `src/bute/commands/rituals.py:477-551` (replace `recap_cmd`)
- Delete: `src/bute/commands/rituals.py:554-595` (delete `review_cmd`)

- [ ] **Step 1: Rewrite `recap_cmd` and delete `review_cmd`**

Replace everything from line 477 to end of file with:

```python
# --- Recap ---


@click.command("recap")
@click.argument("period", required=False, default=None)
@click.pass_context
def recap_cmd(ctx, period):
    """End-of-day summary, or AI analysis of a period (day, week, month, year)."""
    config = ctx.obj.get("config")

    if period is None:
        # Structured display — no AI
        _recap_daily(config)
    else:
        _recap_period(period, config)


def _recap_daily(config):
    """Show today's structured recap: done, open, dropped, captured, habits."""
    from bute.habit_storage import get_habit_summary
    from bute.ritual_ops import (
        get_tasks_done_today,
        get_tasks_dropped_today,
        get_today_captured,
    )
    from bute.state import mark_recap_done
    from bute.storage import query_and_load

    done = get_tasks_done_today(config)
    open_tasks = query_and_load(config, type="task", status="active", tag="today")
    dropped = get_tasks_dropped_today(config)
    captured = get_today_captured(config)

    # Check habits
    configured_habits = []
    if config and "habits" in config and "list" in config["habits"]:
        configured_habits = list(config["habits"]["list"])
    habits = get_habit_summary(date.today(), configured_habits, config) if configured_habits else {}

    has_content = done or open_tasks or dropped or captured or any(v is not None for v in habits.values())
    if not has_content:
        console.print("  [dim]Nothing to recap — quiet day.[/dim]")
        mark_recap_done(config)
        return

    console.print()
    console.print("  [bold]Recap[/bold]")
    console.print(f"  [dim]{'─' * 50}[/dim]")

    if done:
        display_entry_list(done, "Done")

    if open_tasks:
        display_entry_list(list(open_tasks), "Open")

    if dropped:
        display_entry_list(dropped, "Dropped")

    if captured:
        display_entry_list(captured, "Captured")

    if configured_habits:
        from bute.display import display_habit_line
        display_habit_line(habits, configured_habits)

    mark_recap_done(config)
    console.print()


def _recap_period(period: str, config):
    """AI-analyze all entries for the given period."""
    from datetime import timedelta

    from bute.ai import _LLM_INSTALL_MSG, is_llm_available
    from bute.commands.tags import _run_analyze
    from bute.storage import query_and_load

    if not is_llm_available(config):
        console.print(_LLM_INSTALL_MSG)
        return

    today = date.today()
    if period == "day":
        start = today
        label = "today"
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        label = "this-week"
    elif period == "month":
        start = today.replace(day=1)
        label = "this-month"
    elif period == "year":
        start = today.replace(month=1, day=1)
        label = "this-year"
    else:
        console.print(f"  [red]Unknown period: {period}. Use day, week, month, or year.[/red]")
        return

    entries = query_and_load(config, created_since=start.isoformat())

    if not entries:
        console.print(f"  [dim]No entries for {label.replace('-', ' ')}.[/dim]")
        return

    _run_analyze("", entries, config, label=label)
```

- [ ] **Step 2: Run tests to verify daily recap still works**

Run: `uv run pytest tests/test_rituals.py -v -k recap`
Expected: Some tests will fail because they use the `-q` flag which no longer exists. That's expected — we fix the tests in the next task.

- [ ] **Step 3: Commit**

```bash
git add src/bute/commands/rituals.py
git commit -m "feat: merge recap and review — bt recap [period] with analyze pipeline"
```

---

### Task 3: Update tests for new recap behavior

The existing recap tests use `-q` to skip AI. Since the new `bt recap` (no arg) never calls AI, we remove `-q` from all test invocations. We also delete the `test_review_no_entries` test and add a test for the period branch.

**Files:**
- Modify: `tests/test_rituals.py:143-207`

- [ ] **Step 1: Update existing recap tests — remove `-q` flag**

Replace the review and recap test sections (lines 143-207) with:

```python
# --- Recap command tests ---


def test_recap_shows_done_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "finished task", tags=["today"])
    save_entry(e)
    e.status = TaskStatus.DONE
    update_entry(e)

    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "finished task" in result.output
    assert "Done" in result.output


def test_recap_shows_open_tasks(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "still going", tags=["today"])
    save_entry(e)

    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "still going" in result.output
    assert "Open" in result.output


def test_recap_shows_captured(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    j = Entry.create(EntryType.JOURNAL, "feeling good")
    save_entry(j)

    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "feeling good" in result.output


def test_recap_empty_day(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["recap"])
    assert result.exit_code == 0
    assert "Nothing to recap" in result.output


def test_recap_marks_done(runner, tmp_config, tmp_data):
    _setup_config(tmp_config, tmp_data)
    j = Entry.create(EntryType.JOURNAL, "a thought")
    save_entry(j)

    runner.invoke(main, ["recap"])

    from bute.state import is_recap_done_today
    assert is_recap_done_today()


def test_recap_period_no_ai(runner, tmp_config, tmp_data):
    """bt recap week without AI available shows install message."""
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["recap", "week"])
    assert result.exit_code == 0
    assert "AI" in result.output or "No entries" in result.output


def test_recap_invalid_period(runner, tmp_config, tmp_data):
    """bt recap with unknown period shows error."""
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["recap", "quarter"])
    assert result.exit_code == 0
    assert "Unknown period" in result.output
```

- [ ] **Step 2: Run the updated tests**

Run: `uv run pytest tests/test_rituals.py -v -k recap`
Expected: All recap tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_rituals.py
git commit -m "test: update recap tests for merged command, remove review test"
```

---

### Task 4: Delete `review_prompt()` and `recap_prompt()` from prompts.py

Both are dead code now — recap no longer uses AI for the daily view, and the period view uses `analyze_prompt()`.

**Files:**
- Modify: `src/bute/ai/prompts.py:54-83` (delete `review_prompt`)
- Modify: `src/bute/ai/prompts.py:162-183` (delete `recap_prompt`)

- [ ] **Step 1: Delete `review_prompt()` (lines 54-83)**

Remove the entire `review_prompt` function.

- [ ] **Step 2: Delete `recap_prompt()` (lines 162-183)**

Remove the entire `recap_prompt` function.

- [ ] **Step 3: Verify no remaining references**

Run: `grep -r "review_prompt\|recap_prompt" src/`
Expected: No results (the imports in `rituals.py` were already removed in Task 2).

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/bute/ai/prompts.py
git commit -m "chore: delete dead review_prompt and recap_prompt"
```

---

### Task 5: Update CLI registration and help text

Remove `review_cmd` from imports and `add_command`. Update help text to show `bt recap [period]` in Rituals and remove `bt review` from AI Features.

**Files:**
- Modify: `src/bute/cli.py:336-343` (imports)
- Modify: `src/bute/cli.py:374-375` (add_command)
- Modify: `src/bute/cli.py:253` (recap help line)
- Modify: `src/bute/cli.py:259` (review help line — delete)

- [ ] **Step 1: Remove `review_cmd` from import**

Change the import block (line 336-343):

```python
from bute.commands.rituals import (  # noqa: E402
    dp_cmd,
    dump_cmd,
    linelog_cmd,
    recap_cmd,
    wp_cmd,
)
```

(Remove `review_cmd` from the import list.)

- [ ] **Step 2: Remove `review_cmd` from `add_command`**

Delete line 375: `main.add_command(review_cmd)`

- [ ] **Step 3: Update help text — recap line**

Change line 253 from:
```python
    console.print("    [bold]bt recap[/bold]           End-of-day summary ([dim]-q to skip AI[/dim])")
```
to:
```python
    console.print("    [bold]bt recap[/bold]             End-of-day summary — done, open, dropped, captured")
    console.print("    [bold]bt recap[/bold] [period]    AI analysis of a period ([dim]day, week, month, year[/dim])")
```

- [ ] **Step 4: Delete the review help line**

Delete line 259:
```python
    console.print("    [bold]bt review[/bold] [period]   AI summary ([dim]day, week, month[/dim])")
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass. No import errors.

- [ ] **Step 6: Commit**

```bash
git add src/bute/cli.py
git commit -m "chore: remove bt review, update help text for bt recap [period]"
```

---

### Task 6: Update CLAUDE.md

Update the CLI grammar reference so `bt recap` and `bt review` reflect the merged command.

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Rituals section in CLI Grammar**

In the Rituals block, change:
```
bute recap          # end-of-day summary (-q to skip AI)
```
to:
```
bute recap          # end-of-day summary: done, open, dropped, captured
bute recap week     # AI analysis of the period (day, week, month, year)
```

- [ ] **Step 2: Remove the review reference**

In the Views or AI sections, if `bute review` appears, delete it. Also check the Backlog section — `bt reflect` is listed as "Done as `bt recap`", update if needed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for merged bt recap [period]"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Manual smoke test — daily recap**

Run: `bt recap`
Expected: Shows structured display (done/open/dropped/captured/habits) with no AI call. Marks recap done.

- [ ] **Step 3: Manual smoke test — period recap**

Run: `bt recap week`
Expected: If AI is configured, gathers entries for this week, runs analyze pipeline, shows tree, prompts to accept, offers to save note and view mind map. If no AI, shows install message.

- [ ] **Step 4: Verify review is gone**

Run: `bt review`
Expected: Click error — unknown command.

- [ ] **Step 5: Verify help text**

Run: `bt --help`
Expected: Shows `bt recap [period]` in Rituals. No `bt review` anywhere.
