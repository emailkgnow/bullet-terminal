# bt goals — Design Spec

## Summary

A view command that shows notes tagged `@goal`, with progress counts from connected tags. No new entry types, no schema changes. Goals are notes; tags do the connecting.

## Data Model

Zero changes. A goal is a note (`-`) with the `@goal` tag. Connected tags are every other tag on that note except system tags (`@today`, `@thisweek`).

## Capture

```
bt n "get fit by summer" @goal @fitness
bt n "launch bt publicly" @goal @bt-launch
bt n "learn islam" @goal @prayer @fasting
bt n "write a novel" @goal                    # unlinked — no connected tags yet
```

## View — `bt goals`

```
Goals
     Entry                                         Progress
  !  get fit by summer                              @fitness          2 active  1 done
     launch bt publicly                             @bt-launch        4 active  0 done
     learn islam                                    @prayer @fasting  1 active  0 done
     write a novel                                  —                 0 active  0 done
```

### Display rules

- Important goals first (consistent with all other views).
- Connected tags shown in the progress column area.
- Unlinked goals (no connected tags) show `—`.
- Progress = count of tasks with *any* connected tag, split by active/done.
- A task matching multiple goals counts toward each — correct, not a bug.

### Numbering and state

`bt goals` saves state via `save_state("goals", [e.id for e in goals])`. All number-actions work: `bt 2 @fitness` (add tag), `bt 1 !` (toggle important), `bt 3 untag @goal` (archive), `bt 1 edit`, etc.

## Connected tags logic

Given a goal note with tags `["goal", "prayer", "fasting", "thisweek", "today"]`:

1. Filter out system tags: `goal`, `today`, `thisweek`.
2. Remaining: `["prayer", "fasting"]` — these are the connected tags.
3. Query tasks where *any* tag matches: `tag IN ("prayer", "fasting")`.
4. Count active vs done.

System tags list: `goal`, `today`, `thisweek`. This list lives as a constant, not scattered in conditionals.

## Drill in and analyze

Already works — no changes needed:

```
bt @fitness            # all entries tagged @fitness
bt @fitness analyze    # AI clusters entries under this goal
```

## Archive a goal

`bt 1 untag @goal` from the goals view. Removes the note from the goals view. All entries stay tagged. The goal note itself remains as a regular note.

## What to build

1. **`goals_cmd`** in `commands/views.py` — new Click command.
   - Query: `query_and_load(config, type="note", tag="goal")`.
   - For each goal note, extract connected tags (all tags minus system tags).
   - For each connected tag set, count active/done tasks via `query_entries`.
   - Render a custom table with entry info + connected tags + progress counts.
   - Call `save_state("goals", ...)` for number-actions.

2. **Register in `cli.py`** — import and `main.add_command(goals_cmd)`.

3. **Help text** — add `bt goals` line to the custom help in `cli.py`.

## What NOT to build

- No new entry type or signifier.
- No new DB table or schema changes.
- No ritual integration (future: surface goals in `bt plan` header).
- No goal-specific actions — standard number-actions cover everything.

## System tags constant

Define `SYSTEM_TAGS = {"goal", "today", "thisweek"}` in `models.py` alongside existing constants. Used by `goals_cmd` to filter connected tags. Available for future use (e.g., `bt tags` could dim system tags).

## Testing

- `test_goals_view` — create goal notes with connected tags, create tasks, verify `bt goals` output shows correct counts.
- `test_goals_unlinked` — goal with only `@goal` tag shows `—` and 0/0.
- `test_goals_multi_tag` — goal with multiple connected tags aggregates across all.
- `test_goals_state` — verify `save_state` is called so number-actions work.
- `test_goals_important_first` — important goals appear before non-important.
