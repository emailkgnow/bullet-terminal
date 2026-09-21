# Task Scope Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse `bt t` / `bt b` / `bt w` into a single `bt t` command whose scope is chosen by a flag, and make that same flag spell the scope on capture.

**Architecture:** `tasks_cmd` becomes the one task view, taking three mutually exclusive scope flags (bare = today, `-w` = this week, `-b` = backlog) plus stacking filters (`-a`, `@tag`, `!`). "Today" is derived from `get_daily_log` so `bt` and `bt t` can never disagree. `week_cmd` and `backlog_cmd` are deleted and their bodies fold in as branches. `cli.py`'s dispatcher learns the new flags as view flags so `bt t -b` reads and `bt t -b <text>` writes.

**Tech Stack:** Python 3.11+, Click, Rich, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-21-task-scope-flags-design.md`

## Global Constraints

- Scope flags are **task-only**. `bt n`/`bt j`/`bt c` keep their existing signature; `bt n -b` may fail with Click's "no such option" error.
- `-a` widens **status**, never scope. It stacks on whichever scope is active.
- View titles are the `--json` `view` field (`display.py:326`, `:341`). Renaming a title is a JSON contract change and must be reflected in tests.
- State view names stay `"tasks"`, `"week"`, `"backlog"` so `bt <n> done` numbering is unchanged.
- Recurring tasks are excluded from every task scope — they live in `bt streak`.
- Tests run with `uv run pytest`. Install globally after the final task with the command in `CLAUDE.md`.
- Run `uv run pytest` before every commit; a task is not done until its suite is green.

---

## File Structure

| File | Responsibility after this change |
|---|---|
| `src/bute/ritual_ops.py` | Adds `get_today_tasks()` — the single definition of "today's tasks", derived from `get_daily_log` |
| `src/bute/commands/views.py` | `tasks_cmd` owns all three task scopes; `week_cmd`/`backlog_cmd` deleted; `important_cmd` gains scope |
| `src/bute/cli.py` | `VIEW_FLAGS` constant; b/w branch deleted; registrations and help text updated |
| `src/bute/commands/capture.py` | `-l/--later` → `-w/--week`; rejects `-a` |
| `README.md`, `CLAUDE.md` | Grammar documentation |
| `tests/test_views.py` etc. | Updated suites |

---

### Task 1: `get_today_tasks()` — one definition of "today"

**Files:**
- Modify: `src/bute/ritual_ops.py` (add after `get_daily_log`, which ends at `:160`)
- Test: `tests/test_ritual_ops.py`

**Interfaces:**
- Consumes: `get_daily_log(config, include_all)` (`ritual_ops.py:58`)
- Produces: `get_today_tasks(config=None, include_all: bool = False) -> list[Entry]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ritual_ops.py`:

```python
def test_get_today_tasks_is_the_task_rows_of_the_focus_log(tmp_config, tmp_data):
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_daily_log, get_today_tasks
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "focused today", focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "not focused"))
    save_entry(Entry.create(EntryType.NOTE, "a note today"))

    tasks = get_today_tasks()
    bodies = [e.body for e in tasks]

    assert "focused today" in bodies
    assert "a note today" not in bodies
    assert all(e.type == EntryType.TASK for e in tasks)
    # Never disagrees with bt
    log_tasks = [e.id for e in get_daily_log() if e.type == EntryType.TASK]
    assert [e.id for e in tasks] == log_tasks


def test_get_today_tasks_include_all_adds_unfocused_captures(tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.ritual_ops import get_today_tasks
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "captured without focus"))

    assert "captured without focus" not in [e.body for e in get_today_tasks()]
    assert "captured without focus" in [e.body for e in get_today_tasks(include_all=True)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ritual_ops.py -k get_today_tasks -v`
Expected: FAIL with `ImportError: cannot import name 'get_today_tasks'`

- [ ] **Step 3: Write minimal implementation**

Insert into `src/bute/ritual_ops.py` immediately after `get_daily_log` returns (after line 160, before `def get_week_entries`):

```python
def get_today_tasks(config=None, include_all: bool = False) -> list[Entry]:
    """The task rows of the Focus Log — what `bt t` shows.

    Derived from get_daily_log rather than redefined, so `bt` and `bt t`
    can never disagree about what "today" means. That covers focus_date ==
    today, due <= today, scheduled_date == today, and tasks completed today.
    """
    return [
        e for e in get_daily_log(config, include_all=include_all)
        if e.type == EntryType.TASK
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ritual_ops.py -k get_today_tasks -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite and commit**

```bash
uv run pytest -q
git add src/bute/ritual_ops.py tests/test_ritual_ops.py
git commit -m "feat(views): derive today's tasks from the Focus Log

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `tasks_cmd` takes scope flags; delete `week_cmd` and `backlog_cmd`

**Files:**
- Modify: `src/bute/commands/views.py:77-150` (replace `tasks_cmd`, `week_cmd`, `backlog_cmd`)
- Modify: `src/bute/commands/views.py:21` (imports)
- Modify: `src/bute/cli.py:568-578` and `:605-606` (drop the `backlog_cmd`/`week_cmd` imports and registrations — see Ruling A)
- Test: `tests/test_views.py`

**Ruling A (controller, pre-flight):** this task must also remove
`backlog_cmd` and `week_cmd` from `cli.py`'s import list and delete
`main.add_command(backlog_cmd)` / `main.add_command(week_cmd)`. Deleting the
two commands from `views.py` while `cli.py` still imports them raises
ImportError at CLI import, which turns the *entire* suite red rather than just
the `bt b` / `bt w` tests. Task 3 keeps everything else in `cli.py`.

**Interfaces:**
- Consumes: `get_today_tasks(config, include_all)` from Task 1; `get_weekly_active_tasks(config, fallback=False)` (`ritual_ops.py:211`); `query_and_load` (`storage.py:151`); `display_entry_list` / `display_entry_list_grouped` (`display.py:316`, `:370`); `save_state(view, ids, config)`
- Produces: `tasks_cmd` — a Click command named `"tasks"` with options `-w/--week` (dest `scope_week`), `-b/--backlog` (dest `scope_backlog`), `-a/--all` (dest `show_all`), and a positional `tag`. `week_cmd` and `backlog_cmd` no longer exist.

**Note:** `bt t` (today) previously emitted the JSON view `"Tasks — All"`; it now emits `"Tasks — Today"`. `"Tasks — All"` moves to `bt t -b -a`.

- [ ] **Step 1: Write the failing tests**

Replace the body of the `# --- bt t = every task...` section marker at `tests/test_views.py:195` with this marker, and append these tests to the file:

```python
# --- bt t scopes: bare = today, -w = this week, -b = backlog ---


def test_tasks_view_shows_today(runner, tmp_config, tmp_data):
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "on today", focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe"))

    result = runner.invoke(main, ["t"])
    assert result.exit_code == 0, result.output
    assert "on today" in result.output
    assert "someday maybe" not in result.output
    assert "Tasks — Today" in result.output


def test_tasks_week_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.ritual_ops import week_anchor
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "planned this week", week_date=week_anchor()))
    save_entry(Entry.create(EntryType.TASK, "someday maybe", week_date=None))

    result = runner.invoke(main, ["t", "-w"])
    assert result.exit_code == 0, result.output
    assert "planned this week" in result.output
    assert "someday maybe" not in result.output


def test_tasks_backlog_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "someday maybe"))
    done = Entry.create(EntryType.TASK, "already finished")
    done.mark_done()
    save_entry(done)

    result = runner.invoke(main, ["t", "-b"])
    assert result.exit_code == 0, result.output
    assert "someday maybe" in result.output
    assert "already finished" not in result.output


def test_tasks_backlog_all_is_every_task(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "still open"))
    done = Entry.create(EntryType.TASK, "already finished")
    done.mark_done()
    save_entry(done)

    result = runner.invoke(main, ["t", "-b", "-a"])
    assert result.exit_code == 0, result.output
    assert "still open" in result.output
    assert "already finished" in result.output
    assert "Tasks — All" in result.output


def test_tasks_scopes_are_exclusive(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["t", "-w", "-b"])
    assert result.exit_code != 0
    assert "one scope" in result.output.lower()


def test_tasks_scope_excludes_recurring(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "meditate", repeat="daily"))
    save_entry(Entry.create(EntryType.TASK, "ordinary task"))

    result = runner.invoke(main, ["t", "-b"])
    assert "meditate" not in result.output
    assert "ordinary task" in result.output


def test_tasks_scope_tag_filter(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "tagged one", tags=["backend"]))
    save_entry(Entry.create(EntryType.TASK, "untagged one"))

    result = runner.invoke(main, ["t", "-b", "@backend"])
    assert result.exit_code == 0, result.output
    assert "tagged one" in result.output
    assert "untagged one" not in result.output


def test_tasks_scopes_write_distinct_state(runner, tmp_config, tmp_data):
    import json as _json
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "alpha"))

    for args, view in ((["t"], "tasks"), (["t", "-w"], "week"), (["t", "-b"], "backlog")):
        runner.invoke(main, args)
        state = _json.loads(state_path().read_text())
        assert state["view"] == view, args
```

Delete the now-obsolete tests that assert the old meanings: `test_tasks_view_includes_done_and_dropped`, `test_tasks_view_is_grouped_by_date`, `test_tasks_view_excludes_recurring_tasks`, `test_tasks_view_json_title`, `test_week_view_shows_this_weeks_active_tasks`, `test_week_view_excludes_done`, `test_backlog_view`, `test_backlog_writes_state`, `test_tasks_view` — and change `test_tasks_writes_state` plus every `runner.invoke(main, ["b"])` at `:82`, `:91`, `:102`, `:114` to `["t", "-b"]`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_views.py -v`
Expected: FAIL — `no such option: -w` on the scope tests.

- [ ] **Step 3: Write the implementation**

In `src/bute/commands/views.py`, change the import at line 21 to:

```python
from bute.ritual_ops import get_all_active_tasks, get_today_tasks, get_weekly_active_tasks
```

Replace everything from `@click.command("tasks")` (line 77) through the end of `backlog_cmd` (line 150) with:

```python
@click.command("tasks")
@click.argument("tag", required=False, default=None, shell_complete=complete_tags)
@click.option("--week", "-w", "scope_week", is_flag=True, help="This week's tasks.")
@click.option("--backlog", "-b", "scope_backlog", is_flag=True, help="All active tasks.")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def tasks_cmd(ctx, tag, scope_week, scope_backlog, show_all):
    """Today's tasks. -w this week, -b backlog, -a include done/dropped."""
    config = ctx.obj.get("config")

    if scope_week and scope_backlog:
        console.print("  [red]Pick one scope: -w (this week) or -b (backlog).[/red]")
        ctx.exit(1)
        return

    if tag and tag.startswith("@"):
        tag = tag[1:]

    if scope_backlog:
        entries, title, view = _backlog_scope(config, show_all)
    elif scope_week:
        entries, title, view = _week_scope(config, show_all)
    else:
        entries, title, view = _today_scope(config, show_all)

    if tag:
        entries = [e for e in entries if tag in e.tags]
        title = f"{title} @{tag}"

    # Group by date only where the result spans many dates.
    if scope_backlog and show_all:
        display_entry_list_grouped(entries, title)
    else:
        if not entries and view == "week" and not json_mode():
            console.print(
                "  [dim]Nothing planned for this week. "
                "Run [bold]bt wp[/bold] to pick tasks, "
                "or [bold]bt t -b[/bold] for the backlog.[/dim]"
            )
            save_state(view, [], config)
            return
        display_entry_list(entries, title)

    save_state(view, [e.id for e in entries], config)


def _today_scope(config, show_all):
    """Bare `bt t` — the task rows of the Focus Log."""
    entries = get_today_tasks(config, include_all=show_all)
    return entries, "Tasks — Today", "tasks"


def _week_scope(config, show_all):
    """`bt t -w` — tasks selected for this week."""
    if show_all:
        from bute.ritual_ops import week_anchor
        entries = query_and_load(
            config, type="task", week_date=week_anchor(config=config).isoformat()
        )
        entries = [e for e in entries if not e.is_recurring()]
        return entries, "Tasks — Weekly Log (all)", "week"
    return get_weekly_active_tasks(config, fallback=False), "Tasks — Weekly Log", "week"


def _backlog_scope(config, show_all):
    """`bt t -b` — active tasks; with -a, the whole task dimension."""
    kwargs = {"type": "task"}
    if not show_all:
        kwargs["status"] = "active"
    entries = [e for e in query_and_load(config, **kwargs) if not e.is_recurring()]
    title = "Tasks — All" if show_all else "Tasks — Backlog"
    return entries, title, "backlog"
```

- [ ] **Step 4: Drop the dead registrations from `cli.py` (Ruling A)**

In the import block at `src/bute/cli.py:568-578`, remove the `backlog_cmd,` and
`week_cmd,` lines. Then delete these two lines at `:605-606`:

```python
main.add_command(backlog_cmd)
main.add_command(week_cmd)
```

Leave `SHORT_TO_VIEW`, the `view_flags` sets and the b/w branch alone — Task 3
owns those. `bt b` will already stop working, because the branch looks up a
command that is no longer registered and falls through to Click's error.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_views.py -v`
Expected: PASS. `tests/test_action.py`, `test_json_output.py`, `test_rituals.py` will still fail where they invoke `["b"]` or `["w"]` — Task 3 Step 5 fixes those.

- [ ] **Step 6: Commit**

```bash
git add src/bute/commands/views.py src/bute/cli.py tests/test_views.py
git commit -m "feat(views)!: bt t takes scope flags, absorbing bt b and bt w

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Dispatcher — teach `cli.py` the new view flags, delete `b`/`w`

**Files:**
- Modify: `src/bute/cli.py:18` (`SHORT_TO_VIEW`), `:36` and `:109`/`:134` (`view_flags`), `:100-105` (b/w branch). The `backlog_cmd`/`week_cmd` imports and registrations are already gone — Task 2 removed them under Ruling A.
- Test: `tests/test_cli_dispatch.py` (create if absent), `tests/test_action.py`, `tests/test_json_output.py`, `tests/test_rituals.py`

**Interfaces:**
- Consumes: `tasks_cmd` from Task 2
- Produces: module constant `VIEW_FLAGS: set[str]` in `cli.py`, used by both `_is_capture_like` and `resolve_command`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_dispatch.py`:

```python
"""Dispatch tests for the task scope flags."""

from bute.cli import main


def test_bt_b_is_gone(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["b"])
    assert result.exit_code != 0


def test_bt_w_is_gone(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["w"])
    assert result.exit_code != 0


def test_bt_backlog_long_form_is_gone(runner, tmp_config, tmp_data):
    result = runner.invoke(main, ["backlog"])
    assert result.exit_code != 0


def test_scope_flag_alone_is_a_view(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "in the backlog"))
    result = runner.invoke(main, ["t", "-b"])
    assert result.exit_code == 0, result.output
    assert "Tasks — Backlog" in result.output


def test_scope_flag_with_text_is_a_capture(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-b", "buy", "milk"])
    assert result.exit_code == 0, result.output
    entries = query_and_load(type="task")
    assert [e.body for e in entries] == ["buy milk"]


def test_scope_flags_do_not_break_literal_json_in_capture_text(runner, tmp_config, tmp_data):
    """The --json-in-body contract (test_json_output.py:211) survives the new flags."""
    from bute.storage import query_and_load

    result = runner.invoke(main, ["n", "add", "--json", "flag", "to", "api"])
    assert result.exit_code == 0, result.output
    bodies = [e.body for e in query_and_load(None, type="note")]
    assert bodies == ["add --json flag to api"]
```

**Ruling B (controller, pre-flight):** the plan originally asserted that
`bt n --json add -w flag to parser` stores `"add -w flag to parser"`. Both
halves are wrong: `tests/test_json_output.py:211` pins the opposite contract
(a literal `--json` inside capture text is *preserved*, so the body would start
with `--json`), and Click consumes a declared `-w` appearing inside capture
text regardless of this plan. The test above asserts the contract that actually
holds. Do not reinstate the original.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_dispatch.py -v`
Expected: FAIL — `bt b` still resolves; `bt t -b` routes as a view but `-b` isn't recognised as a view flag.

- [ ] **Step 3: Write the implementation**

In `src/bute/cli.py`, replace line 18 and add the flag constant below it:

```python
# Short letter to view command mapping (when no text follows)
SHORT_TO_VIEW = {"t": "tasks", "n": "notes", "j": "journals", "c": "calendar"}
WORD_TO_VIEW = {"task": "tasks", "note": "notes", "journal": "journals", "calendar": "calendar"}

# Flags that keep a signifier on the view path instead of routing to capture.
# Scope flags (-w/-b) are task-only; the other dimensions reject them at Click.
VIEW_FLAGS = {"-a", "--all", "-w", "--week", "-b", "--backlog"}
```

In `_is_capture_like`, replace the local `view_flags = {"-a", "--all"}` (line 36) with a use of the constant:

```python
        # Only @tags / view flags after the signifier → it's a view, not capture.
        return bool(rest) and not all(r.startswith("@") or r in VIEW_FLAGS for r in rest)
```

Delete the `view_flags = {"-a", "--all"}` assignments at lines 79, 109 and 134 and replace every `view_flags` reference in `resolve_command` with `VIEW_FLAGS`.

Delete the b/w branch entirely (lines 100-105):

```python
        # 2. Single letter shortcuts — scope letters, not signifiers
        for letter, view in (("b", "backlog"), ("w", "week")):
            if first == letter:
                cmd = self.get_command(ctx, view)
                if cmd is not None:
                    return view, cmd, rest
```

The registration block needs no change — Task 2 already removed the
`backlog_cmd`/`week_cmd` imports and `main.add_command` calls under Ruling A.
Verify with `grep -n "backlog_cmd\|week_cmd" src/bute/cli.py`; expected: no output.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_dispatch.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Fix the suites that still say `b` or `w`**

Run: `uv run pytest -q` and update every `["b"]` → `["t", "-b"]` and `["w"]` → `["t", "-w"]` in `tests/test_action.py`, `tests/test_json_output.py`, `tests/test_rituals.py`, `tests/test_open_capture.py`. Re-run until green.

- [ ] **Step 6: Commit**

```bash
uv run pytest -q
git add src/bute/cli.py tests/
git commit -m "feat(cli)!: route -w/-b as task view flags, remove bt b and bt w

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Capture — `-l` becomes `-w`, and `-a` is rejected

**Files:**
- Modify: `src/bute/commands/capture.py:27-33` (options), `:110-118` (focus-date logic)
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: `VIEW_FLAGS` semantics from Task 3
- Produces: `capture_cmd` options `-w/--week` (dest `week_only`) and `-b/--backlog` (dest `backlog`). `-l/--later` no longer exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
def test_capture_week_flag_sets_week_date_only(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-w", "research", "flights"])
    assert result.exit_code == 0, result.output
    entry = query_and_load(type="task")[0]
    assert entry.week_date is not None
    assert entry.focus_date is None


def test_capture_backlog_flag_sets_neither(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-b", "someday", "idea"])
    assert result.exit_code == 0, result.output
    entry = query_and_load(type="task")[0]
    assert entry.week_date is None
    assert entry.focus_date is None


def test_capture_bare_sets_both(runner, tmp_config, tmp_data):
    from datetime import date
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "call", "dentist"])
    assert result.exit_code == 0, result.output
    entry = query_and_load(type="task")[0]
    assert entry.focus_date == date.today()
    assert entry.week_date is not None


def test_capture_rejects_all_flag(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    result = runner.invoke(main, ["t", "-a", "buy", "milk"])
    assert result.exit_code != 0
    assert "-w" in result.output and "-b" in result.output
    assert query_and_load(type="task") == []


def test_later_flag_is_gone(runner, tmp_config, tmp_data):
    from bute.storage import query_and_load

    runner.invoke(main, ["t", "-l", "research", "flights"])
    # -l is no longer an option; it must not silently set week_date only.
    entries = query_and_load(type="task")
    assert not any(e.week_date is not None and e.focus_date is None for e in entries)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_capture.py -k "week_flag or backlog_flag or bare_sets_both or rejects_all or later_flag" -v`
Expected: FAIL — `no such option: -w`, and `-a` is written into the body.

- [ ] **Step 3: Write the implementation**

In `src/bute/commands/capture.py`, replace the decorator block at lines 27-33:

```python
@click.command("capture", hidden=True, context_settings={"ignore_unknown_options": True})
@click.option("--week", "-w", "week_only", is_flag=True, help="This week, not today (bt t -w).")
@click.option("--backlog", "-b", is_flag=True, help="Backlog only — no focus dates.")
@click.argument("tokens", nargs=-1, required=True, shell_complete=complete_tags)
@click.pass_context
def capture_cmd(ctx, week_only, backlog, tokens):
    """Capture a new entry."""
    # -a is a view filter, not a capture scope. ignore_unknown_options would
    # otherwise write it into the body — reject it the way removed metadata
    # keys are rejected, with a pointer at the flag that was meant.
    for tok in tokens[1:]:
        if tok in ("-a", "--all"):
            click.echo(
                f"{tok} filters a view, it doesn't pick a capture scope. "
                "Use -w for this week or -b for the backlog."
            )
            ctx.exit(1)
            return

```

Then replace the focus-date block at lines 110-118:

```python
    # Set focus dates on tasks based on flags:
    #   default  → focus_date=today + week_date=monday (bt t)
    #   -w       → week_date only (bt t -w)
    #   -b       → no focus dates (bt t -b)
    config = ctx.obj.get("config")
    has_future_date = entry.scheduled_date and entry.scheduled_date > date.today()
    has_future_due = entry.due and entry.due > date.today()
    if entry.type == EntryType.TASK and not backlog and not has_future_date and not has_future_due:
        from bute.ritual_ops import week_anchor
        entry.week_date = week_anchor(config=config)
        if not week_only:
            entry.focus_date = date.today()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capture.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run pytest -q
git add src/bute/commands/capture.py tests/test_capture.py
git commit -m "feat(capture)!: rename -l to -w, reject -a as a capture scope

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `bt t!` respects scope

**Files:**
- Modify: `src/bute/commands/views.py:168-210` (`important_cmd`)
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `_today_scope`, `_week_scope`, `_backlog_scope` from Task 2
- Produces: `important_cmd` gains `-w/--week` (dest `scope_week`) and `-b/--backlog` (dest `scope_backlog`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_views.py`:

```python
def test_important_task_scope_defaults_to_today(runner, tmp_config, tmp_data):
    from datetime import date
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "urgent today", important=True, focus_date=date.today()))
    save_entry(Entry.create(EntryType.TASK, "urgent someday", important=True))

    result = runner.invoke(main, ["t!"])
    assert result.exit_code == 0, result.output
    assert "urgent today" in result.output
    assert "urgent someday" not in result.output


def test_important_task_backlog_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.TASK, "urgent someday", important=True))
    save_entry(Entry.create(EntryType.TASK, "ordinary someday"))

    result = runner.invoke(main, ["t!", "-b"])
    assert result.exit_code == 0, result.output
    assert "urgent someday" in result.output
    assert "ordinary someday" not in result.output


def test_important_non_task_types_ignore_scope(runner, tmp_config, tmp_data):
    from bute.models import Entry, EntryType
    from bute.storage import save_entry

    save_entry(Entry.create(EntryType.NOTE, "big idea", important=True))

    result = runner.invoke(main, ["n!"])
    assert result.exit_code == 0, result.output
    assert "big idea" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_views.py -k important -v`
Expected: FAIL — `bt t!` returns every important task, and `bt t! -b` errors on the unknown option.

- [ ] **Step 3: Write the implementation**

In `src/bute/commands/views.py`, replace the `important_cmd` decorator and the query section (lines 168-189) with:

```python
@click.command("important", hidden=True)
@click.argument("entry_type", required=False, default=None)
@click.option("--week", "-w", "scope_week", is_flag=True, help="This week's tasks.")
@click.option("--backlog", "-b", "scope_backlog", is_flag=True, help="All active tasks.")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include done/dropped.")
@click.pass_context
def important_cmd(ctx, entry_type, scope_week, scope_backlog, show_all):
    """Show important entries. Optional type filter (task, note, journal, calendar)."""
    config = ctx.obj.get("config")

    type_map = {
        "task": EntryType.TASK, "t": EntryType.TASK,
        "note": EntryType.NOTE, "n": EntryType.NOTE,
        "journal": EntryType.JOURNAL, "j": EntryType.JOURNAL,
        "calendar": EntryType.CALENDAR, "c": EntryType.CALENDAR,
    }
    filter_type = type_map.get(entry_type) if entry_type else None

    if filter_type == EntryType.TASK:
        # ! is a filter, so it stacks on a scope exactly as -a and @tag do.
        if scope_backlog:
            entries, scope_title, _ = _backlog_scope(config, show_all)
        elif scope_week:
            entries, scope_title, _ = _week_scope(config, show_all)
        else:
            entries, scope_title, _ = _today_scope(config, show_all)
        entries = [e for e in entries if e.important]
        title = scope_title.replace("Tasks — ", "Important Tasks — ")
        display_entry_list(entries, title)
        save_state("important", [e.id for e in entries], config)
        return

    kwargs = {"important": True}
    if filter_type:
        kwargs["type"] = filter_type.value
    if not show_all:
        kwargs["exclude_status"] = "dropped"
    entries = query_and_load(config, **kwargs)
```

Leave the rest of the function (the post-filter, title building, display and `save_state`) untouched — it now only handles the non-task types.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_views.py -k important -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
uv run pytest -q
git add src/bute/commands/views.py tests/test_views.py
git commit -m "feat(views): ! filters the active task scope instead of ignoring it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Help text and documentation

**Files:**
- Modify: `src/bute/cli.py:282-283`, `:339`, `:350-351`, `:386`
- Modify: `src/bute/commands/habits.py:30`, `src/bute/commands/tour.py:67`, `src/bute/commands/zen.py:15`, `src/bute/completion.py:49` (only if they name `bt b`/`bt w`/`-l`)
- Modify: `README.md:30-32`, `:159`, `:254`
- Modify: `CLAUDE.md` — CLI Grammar and Design Decisions sections
- Test: `tests/test_help_grammar.py`

**Interfaces:**
- Consumes: the finished grammar from Tasks 2-5
- Produces: no code interfaces; documentation only

- [ ] **Step 1: Write the failing test**

Append to `tests/test_help_grammar.py`:

```python
def test_help_teaches_scope_flags_and_not_the_old_commands(runner):
    result = runner.invoke(main, ["-h"])
    assert result.exit_code == 0
    out = result.output
    assert "bt t -b" in out
    assert "bt t -w" in out
    assert "-l|--later" not in out
    assert "long forms of" not in out  # the bt backlog / bt week row is gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_help_grammar.py -k scope_flags -v`
Expected: FAIL — the help still advertises `-l|--later` and the long forms.

- [ ] **Step 3: Update the help text**

In `src/bute/cli.py`, replace lines 282-283:

```python
    t.add_row("[cyan]bt t -w|--week[/cyan] <text>", "Task — this week (bt t -w), not today", "bt t -w research flights")
    t.add_row("[cyan]bt t -b|--backlog[/cyan] <text>", "Task — straight to the backlog (bt t -b)", "bt t -b someday idea")
```

Replace line 339 with a row that teaches the scopes instead of the deleted long forms:

```python
    console.print("    [dim]Also:[/dim] [bold]bt t[/bold] today · [bold]bt t -w[/bold] this week · [bold]bt t -b[/bold] backlog · [bold]-a[/bold] adds done/dropped")
```

Replace lines 350-351:

```python
    t.add_row("bt <n> later", "Off today, stays in this week (bt t -w)", "bt 3 later")
    t.add_row("bt <n> backlog", "Send to the backlog (bt t -b) — clears week and day", "bt 3 backlog")
```

Replace line 386:

```python
    t.add_row("bt <view> --json", "Emit numbered entry views as JSON", "bt t -b --json, bt @home --json")
```

- [ ] **Step 4: Update README.md**

Replace lines 30-32:

```markdown
bt t              # today's tasks
bt t -w           # this week's tasks
bt t -b           # backlog (all active tasks)
bt t -b -a        # every task, any status, grouped by date
```

At line 159, change `bt b --json` to `bt t -b --json`. At line 254, leave the capture row as is — `bt t <text>` is unchanged.

- [ ] **Step 5: Update CLAUDE.md**

In the **Views** block of the CLI Grammar section, replace the `bt t` / `bt w` / `bt b` lines with:

```
bt t              # Tasks — Today: the task rows of the Focus Log
bt t -w           # Tasks — Weekly Log: active tasks with week_date == this week
bt t -b           # Tasks — Backlog: all active tasks
bt t -b -a        # Tasks — All: every task, any status, grouped by date
bt t @backend     # any scope, filtered by tag
bt t! -b          # any scope, important only
```

In **Design Decisions**, replace the "Task views" and "Letter shortcuts are scopes, not signifiers" bullets with:

```markdown
- **Task scope is a flag, not a command** — `bt t` is today, `-w` is this week, `-b` is the backlog, and the same flag spells the scope on capture (`bt t -b <text>`). `bt b` and `bt w` were removed along with their `backlog`/`week` long forms. `t`/`n`/`j`/`c` are dimensions again, with no scope letters beside them.
- **Filters stack, scopes don't** — `-a` (include done/dropped), `@tag` and `!` compose on top of exactly one scope; `-w` and `-b` together is an error. `-a` therefore keeps the one meaning it has everywhere in bt: widen status, never scope. The full task dimension is `bt t -b -a`.
- **`bt t` and `bt` share one definition of today** — `ritual_ops.get_today_tasks()` filters `get_daily_log()` to tasks, so the two views can't disagree about focus dates, overdue tasks or today's completions.
```

- [ ] **Step 6: Sweep the remaining stale strings**

Run: `grep -rn "bt b \|bt w \|--later\|bt backlog\|bt week" src/ README.md CLAUDE.md`
Fix every hit. Expected remaining: none.

- [ ] **Step 7: Run tests and commit**

```bash
uv run pytest -q
git add src/bute README.md CLAUDE.md tests/test_help_grammar.py
git commit -m "docs(help): teach task scope flags, retire bt b and bt w

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Full verification and global reinstall

**Files:** none modified unless a failure surfaces.

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest`
Expected: all green. Fix any straggler that still invokes `["b"]`, `["w"]`, `["backlog"]`, `["week"]` or `-l`.

- [ ] **Step 2: Reinstall globally**

```bash
uv tool install --from . --with fastembed --with sqlite-vec bullet-terminal --force --reinstall
```

- [ ] **Step 3: Smoke-test the real grammar**

```bash
bt t -b
bt t -w
bt t -b -a
bt t -b smoke test entry from the scope flags refactor
bt t -b | tail -5      # the smoke entry should be there, with no focus date
bt b                   # expect: Error: No such command 'b'
bt t -a buy milk       # expect: non-zero exit, pointer at -w / -b
```

Delete the smoke entry with `bt <n> delete` when done.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "test: finish the bt b / bt w removal sweep

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** Scopes → Task 2. "Today" definition → Task 1. Filters stacking → Tasks 2 and 5. Capture flags → Task 4. `-a` rejection on capture → Task 4. Display/grouping rule → Task 2. Removals (`bt b`, `bt w`, long forms, `-l`, `week_cmd`/`backlog_cmd`) → Tasks 2, 3, 4. Docs → Task 6. Every test listed in the spec's Testing section appears in a task.

**Type consistency:** `get_today_tasks(config, include_all)` is defined in Task 1 and consumed under that exact name in Tasks 2 and 5. Click dests `scope_week`, `scope_backlog`, `show_all`, `week_only`, `backlog` are used consistently. `_today_scope` / `_week_scope` / `_backlog_scope` all return `(entries, title, view)` and are called that way in both `tasks_cmd` and `important_cmd`.

**Known ordering dependency:** the suite is red between Task 2 and Task 3 (tests still invoking `bt b`/`bt w`). Task 3 Step 5 clears it; do not run the two tasks out of order.
