# dp Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 5-phase DYTS ritual (`dp`) with a single-phase task picker that shows yesterday's unresolved tasks highlighted at top, then the `@thisweek`/backlog pool below, using a questionary checkbox.

**Architecture:** Rewrite `dp_cmd` in `commands/rituals.py` to a single checkbox picker. Reuse existing query functions from `ritual_ops.py`. Update tests to match new behavior. Update help text in `cli.py`.

**Tech Stack:** Python, Click, questionary, Rich

---

### Task 1: Write tests for new dp behavior

**Files:**
- Modify: `tests/test_rituals.py:18-42`

The existing dp tests assert on the old DYTS phases (Dump, Yesterday, Tasks, Schedule). Replace them with tests for the new single-phase picker.

- [ ] **Step 1: Replace the dp test assertions**

Replace the two existing dp tests with tests for the new behavior:

```python
# --- Daily Plan (dp) command tests ---


def test_dp_non_interactive_shows_tasks(runner, tmp_config, tmp_data):
    """dp -y shows weekly tasks and marks daily plan done."""
    _setup_config(tmp_config, tmp_data)
    e = Entry.create(EntryType.TASK, "deploy staging", tags=["thisweek"])
    save_entry(e)

    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert "Daily Plan" in result.output
    assert "deploy staging" in result.output
    assert "Ready" in result.output
    # Old phases should NOT appear
    assert "Dump" not in result.output
    assert "Yesterday" not in result.output
    assert "Schedule" not in result.output


def test_dp_non_interactive_no_tasks(runner, tmp_config, tmp_data):
    """dp -y with no active tasks shows empty message."""
    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert "No active tasks" in result.output
    assert "Ready" in result.output


def test_dp_non_interactive_marks_done(runner, tmp_config, tmp_data):
    """dp -y marks daily plan as done so bt shows Focus Log."""
    from bute.state import is_dyts_done_today

    _setup_config(tmp_config, tmp_data)
    result = runner.invoke(main, ["dp", "--non-interactive"])
    assert result.exit_code == 0
    assert is_dyts_done_today(tmp_data) or is_dyts_done_today()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rituals.py::test_dp_non_interactive_shows_tasks tests/test_rituals.py::test_dp_non_interactive_no_tasks tests/test_rituals.py::test_dp_non_interactive_marks_done -v`

Expected: FAIL — old dp still outputs "Dump", "Yesterday", "Schedule"

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_rituals.py
git commit -m "test(dp): rewrite dp tests for single-phase task picker"
```

---

### Task 2: Rewrite dp_cmd to single-phase task picker

**Files:**
- Modify: `src/bute/commands/rituals.py:33-232`

Replace the entire `dp_cmd` function body (lines 36-232) with the new single-phase picker.

- [ ] **Step 1: Rewrite dp_cmd**

Replace `dp_cmd` (everything from line 33 to line 232) with:

```python
@click.command("dp")
@click.option("-y", "--non-interactive", is_flag=True, help="Skip prompts.")
@click.pass_context
def dp_cmd(ctx, non_interactive):
    """Morning ritual — pick today's tasks from weekly focus."""
    config = ctx.obj.get("config")

    display_ritual_header("Daily Plan", "Pick your focus for today")

    # 1. Gather yesterday's unresolved tasks
    yesterday = get_yesterday_unresolved(config)
    yesterday_ids = {e.id for e in yesterday}

    # 2. Gather weekly/backlog pool (excluding yesterday dupes)
    pool = get_weekly_active_tasks(config)
    pool = [e for e in pool if e.id not in yesterday_ids]

    all_tasks = yesterday + pool

    if not all_tasks:
        console.print("  [dim]No active tasks.[/dim]")
    else:
        if non_interactive:
            display_entry_list(all_tasks, "")
        else:
            try:
                import questionary

                choices = []
                for e in yesterday:
                    label = f"\u21a9 {e.body}"
                    choices.append(questionary.Choice(
                        label, value=e.id, checked="today" in e.tags,
                    ))
                for e in pool:
                    choices.append(questionary.Choice(
                        e.body, value=e.id, checked="today" in e.tags,
                    ))

                selected = questionary.checkbox(
                    "Select tasks for today:", choices=choices
                ).ask()

                if selected is not None:
                    from bute.storage import entry_path_from_id, load_entry

                    selected_set = set(selected)
                    count = 0
                    for e in all_tasks:
                        path = entry_path_from_id(e.id, config)
                        if not path:
                            continue
                        entry = load_entry(path)
                        if e.id in selected_set and "today" not in entry.tags:
                            entry.tags.append("today")
                            update_entry(entry, config)
                            count += 1
                        elif e.id not in selected_set and "today" in entry.tags:
                            entry.tags.remove("today")
                            update_entry(entry, config)
                    console.print(f"  [green]{len(selected)} tasks tagged for today[/green]")
            except ImportError:
                console.print("  [dim]questionary not available — skipping selection[/dim]")
                display_entry_list(all_tasks, "")

    from bute.state import mark_dyts_done
    mark_dyts_done(config)

    console.print(f"\n  [bold green]Ready. Go.[/bold green]")
```

- [ ] **Step 2: Clean up unused imports**

At the top of `rituals.py`, the following imports are no longer needed by `dp_cmd`. Check if `wp_cmd` or other functions in the file still use them before removing:

- `confirm_capture` — used by `wp_cmd` dump phase, keep
- `display_action_confirmation` — only used by old dp Y phase, remove
- `get_today_schedule` — only used by old dp S phase, remove
- `process_dump_line` — used by `wp_cmd`, keep
- `TaskStatus` — only used by old dp Y phase, remove (check `wp_cmd` first)

Remove from imports:
```python
# Remove from display imports:
#   display_action_confirmation
# Remove from ritual_ops imports:
#   get_today_schedule
# Remove from models imports:
#   TaskStatus
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_rituals.py -v`

Expected: All dp tests PASS. wp/recap/streak tests still PASS.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/bute/commands/rituals.py
git commit -m "feat(dp): simplify to single-phase task picker

Remove Dump, Yesterday, Schedule, Habits phases.
Show yesterday's unresolved at top with ↩ prefix,
@thisweek/backlog pool below. One checkbox selection."
```

---

### Task 3: Update help text and CLAUDE.md

**Files:**
- Modify: `src/bute/cli.py:325`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update cheat sheet in cli.py**

In `src/bute/cli.py` line 325, change:

```python
t.add_row("bt dp", "Daily plan — morning ritual", "-y for non-interactive")
```

to:

```python
t.add_row("bt dp", "Daily plan — pick today's tasks", "-y for non-interactive")
```

- [ ] **Step 2: Update dp docstring reference in cli.py**

The dp command's docstring was already updated in Task 2. Verify no other references to "Dump, Yesterday, Tasks, Schedule" exist in cli.py:

Run: `grep -n "Dump\|Yesterday\|DYTS" src/bute/cli.py`

Expected: Only the `is_dyts_done_today` import at line 451-452 (this is fine — it's the gate function).

- [ ] **Step 3: Update CLAUDE.md Rituals section**

In `CLAUDE.md`, change the rituals section:

```
bute dp             # morning ritual (Dump, Yesterday, Tasks, Schedule)
```

to:

```
bute dp             # morning ritual — pick today's tasks
```

- [ ] **Step 4: Update CLAUDE.md Backlog section**

In `CLAUDE.md`, under "### Onboarding", change:

```
- **Redesign Daily Plan (`dp`)** — decompose Dump into individual entry types (t, n, j, c) mirroring the tour's layered approach. Rename to "Focus Process" since it flows into the Focus Log.
```

to:

```
- ~~**Redesign Daily Plan (`dp`)**~~ ✓ Done — simplified to single-phase task picker. Yesterday's unresolved highlighted at top, @thisweek/backlog pool below.
```

- [ ] **Step 5: Update CLAUDE.md Design Decisions**

In `CLAUDE.md`, find:

```
- **`bute` with no args** = DYTS entry point. If DYTS done today, shows Focus Log.
```

Change to:

```
- **`bute` with no args** = Daily Plan entry point. If daily plan done today, shows Focus Log.
```

- [ ] **Step 6: Commit**

```bash
git add src/bute/cli.py CLAUDE.md
git commit -m "docs: update help text and CLAUDE.md for simplified dp"
```

---

### Task 4: Manual smoke test

**Files:** None (verification only)

- [ ] **Step 1: Install and test interactively**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Run dp interactively**

```bash
bt dp
```

Verify:
- Shows "Daily Plan" header
- Yesterday's tasks appear at top with `↩` prefix (if any exist)
- `@thisweek` tasks appear below
- Checkbox selection works
- Selecting tasks adds `@today` tag
- "Ready. Go." appears after selection

- [ ] **Step 3: Run dp non-interactive**

```bash
bt dp -y
```

Verify:
- Shows task list without prompts
- Marks daily plan as done

- [ ] **Step 4: Verify Focus Log gate**

```bash
bt
```

Verify: Shows Focus Log (not dp) since dp was just completed.

- [ ] **Step 5: Run full test suite one final time**

```bash
uv run pytest -x
```

Expected: All tests pass.

- [ ] **Step 6: Final commit if any fixes needed**

Only if smoke testing revealed issues that needed fixing.
