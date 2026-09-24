# Entry Viewer (`bt <n>`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse `bt <n>`, `bt <n> open|edit|show|read|view` into one spelling — bare `bt <n>` — that opens a built-in Textual markdown viewer, with `e` handing off to `$EDITOR`.

**Architecture:** A new `bute/viewer.py` holds a small Textual `App` (metadata strip + rendered body + footer). `action.py` routes a bare number to `handle_view`, which runs the viewer on a TTY and falls back to the existing Rich `display_entry_full` when stdout is not a terminal. The retired action words raise a pointer via `REMOVED_ACTIONS`. leaf support is removed.

**Tech Stack:** Python, Click, Rich, Textual (new hard dependency), pytest (+ Textual's `run_test` pilot).

**Spec:** Agreed in conversation 2026-09-24 — no separate spec file. Summary: reading is ~90% of why an entry is opened, so `bt <n>` reads; `e`/`ctrl+e` edits in `$EDITOR` (fallback `nano`) and returns to a refreshed view; `q`/`esc` quits; several numbers step through with `n`/`p`; non-TTY prints via Rich; no Homebrew step.

## Global Constraints

- One spelling: `bt <n>` is the only way to open an entry. `open`, `edit`, `show`, `read`, `view` raise a pointer to `bt <n>`.
- `bt t|n|j|c open` (long-form capture) is unchanged.
- `textual` is a required dependency (`textual>=0.80`), imported lazily so other commands pay no startup cost.
- Editor resolution: `$EDITOR`, else `nano` (same as the old `handle_edit`).
- After an edit, the entry is re-indexed (`_reindex_entry`) so FTS/vectors stay current.
- README.md data/grammar docs and CLAUDE.md updated in the same commit as the grammar change.

## Review Focus

1. Piped / non-TTY `bt 1 | cat` — must print Rich output, never hang in a full-screen app. (Task 2 test: CliRunner is non-TTY.)
2. Entry file edited to invalid YAML in `$EDITOR` — viewer must not crash; shows an error line and keeps last good render. (Task 1 test.)
3. Entry whose body contains Rich markup like `[red]` or a tag value `[x]` — the meta strip must escape it. (Task 1 test.)
4. `bt 1 edit` from muscle memory — must get a clear pointer, not "Unknown action". (Task 2 test.)
5. Number not in last view / stale state — existing "not found" path must still work for bare `bt 9`. (Task 2 test.)

---

### Task 1: Textual viewer module

**Files:**
- Create: `src/bute/viewer.py`
- Modify: `pyproject.toml` (add `textual>=0.80`)
- Test: `tests/test_viewer.py`

**Interfaces:**
- Produces: `meta_markup(entry: Entry) -> str`, `prepare_body(body: str) -> str`, `EntryViewer(paths: list[Path], on_edit: Callable[[Path], None])` (a Textual `App`), `run_viewer(paths, on_edit) -> None`.

- [ ] Step 1: tests — `meta_markup` includes symbol, `!`, due/date/time/repeat, `@tags`, escapes markup; `prepare_body` turns `- [ ]`/`- [x]` into ☐/☑; pilot test: app mounts, shows body text, `n`/`p` move between two paths and the title shows `1/2`→`2/2`; pilot test: `e` calls editor (monkeypatched `subprocess.call`) then `on_edit`, then reloads changed body; invalid YAML after edit shows an error, no crash; `q` exits.
- [ ] Step 2: run, expect import failure.
- [ ] Step 3: implement `viewer.py`.
- [ ] Step 4: run, expect pass.

### Task 2: Grammar collapse + routing

**Files:**
- Modify: `src/bute/cli.py:218-220` (bare number → no appended action), help table rows `cli.py:358-359`
- Modify: `src/bute/commands/action.py` (`parse_action_tokens` allows empty action → `""`; `handle_view` replaces `handle_edit`/`handle_show`; drop leaf; `REMOVED_ACTIONS` gains `open/edit/show/read/view` with full hint text; view runs once over all resolved paths)
- Test: `tests/test_action.py` (replace leaf tests)

**Interfaces:**
- Consumes: `run_viewer(paths, on_edit)` from Task 1; `display_entry_full(entry)` from `display.py`.
- Produces: `handle_view(entries: list[Entry], config) -> None`.

- [ ] Step 1: tests — bare `bt 1` non-TTY prints Rich render (heading text, `@tag`, short id, no `# `); `bt 1 2` prints both; each of `edit/open/show/read/view` exits non-zero with message containing `bt <n>`; `bt 1` on a TTY calls `run_viewer` with the entry path (monkeypatch `_is_tty` and `run_viewer`); `bt 9` with 1-entry state → existing not-found error.
- [ ] Step 2: run, expect fails.
- [ ] Step 3: implement.
- [ ] Step 4: full suite passes.

### Task 3: Docs

**Files:** `README.md` (line 45 example, line 100 `bt <n> show`, line 281 action list), `CLAUDE.md` (Actions block, Design Decisions bullet "One way to open an entry"), `src/bute/display.py:679` docstring.

- [ ] Step 1: edit docs; Step 2: `uv run pytest`; Step 3: commit `feat(grammar)!: bt <n> opens a built-in viewer; open/edit/show/read/view retired`; Step 4: reinstall globally with `uv tool install ... --force --reinstall`.
