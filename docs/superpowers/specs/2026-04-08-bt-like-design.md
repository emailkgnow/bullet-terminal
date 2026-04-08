# `bt like` — Unified Semantic Search

## Context

`bt search <query>` (semantic search by text) and `bt similar <n>` (find entries similar to entry #n) do the same thing under the hood: embed input, search the vector DB, display results. Having two commands for the same operation adds cognitive overhead. Merging them into `bt like` gives a single, intuitive command — "show me things like this."

## Command Grammar

```
bt like <input> [-n N]
```

- `bt like 3` — entries like entry #3 (current `bt similar`)
- `bt like productivity` — entries like "productivity" (current `bt search`)
- `bt like 3 -n 10` — 10 entries like entry #3
- `bt like diet plans -n 20` — 20 results for "diet plans"

## Routing Logic

1. If the input is a single integer token, attempt `resolve_numbers()` against current view state.
2. If resolution succeeds → **similar mode**: embed that entry's body, search vectors, filter out the source entry.
3. If resolution fails (no view state, number out of range) → **search mode**: treat the number as a text query.
4. If the input is anything else (multiple tokens, non-integer) → **search mode**: join tokens, embed as query, search vectors.

## Display

- **Similar mode**: header `Like: <entry body snippet>`, default limit 5
- **Search mode**: header `Like: "<query>"`, default limit 10
- Both use existing `display_search_results()` with updated title logic
- State saved as `"like"` for number-action resolution

## Changes

### Remove
- `search_cmd` in `commands/search.py`
- `similar_cmd` in `commands/search.py`
- CLI registration of both in `cli.py`
- Help table rows for `bt search` and `bt similar`

### Add
- `like_cmd` in `commands/search.py` — single command combining both flows
- CLI registration of `like` in `cli.py`
- Help table row: `bt like <input>` / `Semantic similarity` / `bt like 3, bt like productivity`

### Modify
- `display_search_results()` in `display.py` — update title from `Search:` / `Similar entries` to `Like:` format
- `CLAUDE.md` CLI grammar section — replace `search`/`similar` references with `like`

### Unchanged
- `find_cmd`, `rebuild_cmd`
- All embedding/vector infrastructure (`ai/embeddings.py`, `ai/vectors.py`, `ai/__init__.py`)
- `display_search_results()` table rendering (only title changes)

## Files to Modify

1. `src/bute/commands/search.py` — replace `search_cmd` + `similar_cmd` with `like_cmd`
2. `src/bute/cli.py` — update imports, registration, help table
3. `src/bute/display.py` — update title in `display_search_results()`
4. `CLAUDE.md` — update CLI grammar docs

## Verification

1. `bt like 3` after a view — shows similar entries, header shows source entry body
2. `bt like productivity` — semantic search, header shows query in quotes
3. `bt like 3 -n 10` — 10 similar results
4. `bt like 42` with no prior view — falls back to semantic search for "42"
5. `bt 1 done` after `bt like` — number-action works (state saved correctly)
6. `bt find keyword` — unchanged, still works
7. `bt rebuild` — unchanged, still works
