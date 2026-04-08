# Display Metadata Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up metadata display across all views — hide system tags, show user tags dim with dot separator, show dates/times in cyan, drop relevance % from `bt like`.

**Architecture:** Modify `_build_entry_row()` to return a styled Rich `Text` object for the meta column instead of a plain string. Apply the same styling to `display_search_results()` and `confirm_capture()`. Import `SYSTEM_TAGS` from `models.py` for filtering.

**Tech Stack:** Rich (Text objects with mixed styles), existing `SYSTEM_TAGS` constant, `format_time_display()` helper

---

## File Map

- **Modify:** `src/bute/display.py` — `_build_entry_row()`, `display_entry_list()`, `display_entry_list_grouped()`, `display_search_results()`, `confirm_capture()`

---

### Task 1: Refactor `_build_entry_row()` meta column

**Files:**
- Modify: `src/bute/display.py:9,97-128`

- [ ] **Step 1: Add SYSTEM_TAGS import**

Add `SYSTEM_TAGS` to the existing import on line 9 of `src/bute/display.py`:

Change:
```python
from bute.models import Entry, EntryType, TaskStatus
```
to:
```python
from bute.models import Entry, EntryType, SYSTEM_TAGS, TaskStatus
```

- [ ] **Step 2: Rewrite the meta-building section of `_build_entry_row()`**

Replace lines 97-128 of `src/bute/display.py` (the entire `_build_entry_row` function) with:

```python
def _build_entry_row(i: int, entry: Entry, hide_tags: set | None = None) -> tuple[str, Text, Text, Text]:
    """Build the common columns for an entry row: (#, icon, body, meta)."""
    style = TYPE_STYLE[entry.type]

    icon = Text()
    if entry.important:
        icon.append("!", style="bold red")
    else:
        icon.append(" ")
    icon.append(style["icon"], style=style["color"])

    preview = _preview(entry.body)

    body = Text()
    if entry.status == TaskStatus.DONE:
        body.append(preview, style="strike dim")
    elif entry.status == TaskStatus.DROPPED:
        body.append(preview, style="dim")
    else:
        body.append(preview)

    # Build styled meta: user tags (dim) · dates (cyan)
    meta = Text()

    # User tags — filter system tags and hide_tags
    user_tags = [t for t in entry.tags if t not in SYSTEM_TAGS and (not hide_tags or t not in hide_tags)]

    # Date parts
    date_parts = []
    if entry.due:
        date_parts.append(f"due:{entry.due}")
    if entry.scheduled_time:
        date_parts.append(f"t:{format_time_display(entry.scheduled_time)}")
    if entry.scheduled_date:
        date_parts.append(f"d:{entry.scheduled_date.strftime('%b %-d')}")

    if user_tags:
        meta.append("· ", style="dim")
        meta.append(" ".join(f"@{t}" for t in user_tags), style="dim")
    if date_parts:
        meta.append(" · ", style="dim") if meta.plain else meta.append("· ", style="dim")
        meta.append(" ".join(date_parts), style="cyan")

    return str(i), icon, body, meta
```

- [ ] **Step 3: Commit**

```bash
git add src/bute/display.py
git commit -m "refactor: styled metadata in _build_entry_row — dim tags, cyan dates, dot separator"
```

---

### Task 2: Update `display_search_results()` to match

**Files:**
- Modify: `src/bute/display.py:345-389`

- [ ] **Step 1: Rewrite `display_search_results()`**

Replace the entire `display_search_results()` function (lines 345-389) with:

```python
def display_search_results(
    entries: list[Entry], distances: list[float], query: str = ""
) -> None:
    """Render search results."""
    if not entries:
        console.print("  [dim]No results found.[/dim]")
        return

    table = Table(
        show_header=False,
        show_edge=False,
        pad_edge=False,
        box=None,
        padding=(0, 1),
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)  # type icon
    table.add_column("", ratio=1)  # body
    table.add_column("")  # meta

    for i, entry in enumerate(entries, 1):
        _, icon, _, meta = _build_entry_row(i, entry)

        body = Text()
        body.append(_preview(entry.body))

        table.add_row(str(i), icon, body, meta)

    title = f'Like: "{query}"' if query else "Like"
    console.print(f"\n  [bold]{title}[/bold]")
    console.print(table)
```

Note: we reuse `_build_entry_row()` for icon and meta, but override body since search results don't have task status styling (entries may be any type). Actually, `_build_entry_row` already handles status styling correctly for all types, so we can simplify further:

```python
def display_search_results(
    entries: list[Entry], distances: list[float], query: str = ""
) -> None:
    """Render search results."""
    if not entries:
        console.print("  [dim]No results found.[/dim]")
        return

    table = Table(
        show_header=False,
        show_edge=False,
        pad_edge=False,
        box=None,
        padding=(0, 1),
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("", width=2)  # type icon
    table.add_column("", ratio=1)  # body
    table.add_column("")  # meta

    for i, entry in enumerate(entries, 1):
        num, icon, body, meta = _build_entry_row(i, entry)
        table.add_row(num, icon, body, meta)

    title = f'Like: "{query}"' if query else "Like"
    console.print(f"\n  [bold]{title}[/bold]")
    console.print(table)
```

- [ ] **Step 2: Commit**

```bash
git add src/bute/display.py
git commit -m "refactor: display_search_results uses _build_entry_row, drops relevance %"
```

---

### Task 3: Update `confirm_capture()` to filter system tags

**Files:**
- Modify: `src/bute/display.py:23-63`

- [ ] **Step 1: Filter system tags in confirm_capture**

Change line 50-51 in `confirm_capture()` from:

```python
    if entry.tags:
        meta_parts.append(" ".join(f"@{t}" for t in entry.tags))
```

to:

```python
    if entry.tags:
        user_tags = [t for t in entry.tags if t not in SYSTEM_TAGS]
        if user_tags:
            meta_parts.append(" ".join(f"@{t}" for t in user_tags))
```

- [ ] **Step 2: Commit**

```bash
git add src/bute/display.py
git commit -m "refactor: confirm_capture hides system tags"
```

---

### Task 4: Reinstall and verify

- [ ] **Step 1: Reinstall bt globally**

```bash
uv tool install --from . --with fastembed --with sqlite-vec --with openai bute --force --reinstall
```

- [ ] **Step 2: Verify `bt t` — tasks show user tags dim, no system tags**

```bash
bt t
```

Expected: No `@thisweek` or `@today` in output. User tags dim with `·` separator.

- [ ] **Step 3: Verify `bt like productivity` — no relevance %, styled metadata**

```bash
bt like productivity
```

Expected: No percentage scores. Tags dim, dates cyan if present.

- [ ] **Step 4: Verify `bt d` — daily log entries styled correctly**

```bash
bt d
```

Expected: Entries show user tags dim, dates/times cyan.

- [ ] **Step 5: Verify `bt n` — grouped view styled correctly**

```bash
bt n
```

Expected: Notes grouped by date, metadata styled with dot separator.

- [ ] **Step 6: Verify calendar entries show time in cyan**

```bash
bt c
```

Expected: Calendar events show `t:` time in cyan.
