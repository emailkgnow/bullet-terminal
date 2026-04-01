# Collections — Super Notes & Super Tasks

**Date:** 2026-04-01
**Status:** Draft

## Overview

Collections replace the FFFF pipeline (find/form/focus/finish) with a simpler, more flexible model. A collection is a bucket of raw items that the user accumulates over time using `+collection` syntax during normal capture. When ready, the user can ask the AI to **analyze** (cluster and organize) or **execute** (analyze + generate sequenced tasks).

A collection that stops at analysis is a **super note** — synthesized knowledge. A collection that goes through execution is a **super task** — a project broken into actionable steps.

### Design Principles

- **Option B**: items live only in the collection until Execute generates real entries. No dual storage.
- **Two AI stages, not four**: Analyze (understand) and Execute (act). Execute includes Analyze.
- **Every stage has standalone value**: raw = parking lot, analyzed = organized knowledge, executed = actionable project.
- **Stay BuJo**: collections are a Bullet Journal concept. `+` is just rapid logging for "add to collection."

## 1. `+collection` Capture Syntax

### Grammar

```
bt <signifier> <text> +<collection-name> [@tags] [key:value]
```

Examples:
```bash
bt t fix kitchen faucet +home-reno
bt n measured kitchen — 12x15 +home-reno
bt j feeling overwhelmed by scope +home-reno
bt c contractor visit d:0415 +home-reno
bt t! fix prod bug +q2-launch                    # important modifier
bt t fix faucet +home-reno @plumbing due:friday   # tags + metadata preserved
```

### Parser Changes (`parser.py`)

Add `COLLECTION_RE`:
```python
COLLECTION_RE = re.compile(r"^\+([a-zA-Z0-9_-]+)$")
```

Extend `ParsedInput`:
```python
@dataclass
class ParsedInput:
    signifier: str
    important: bool
    body_words: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    collection: str | None = None  # NEW
```

In `parse_capture_tokens()`, match `+name` tokens the same way `@tag` tokens are matched. Only one collection per capture (first match wins; error or ignore subsequent `+` tokens).

### Capture Flow (`capture.py`)

When `parsed.collection` is set:

1. Reconstruct a raw line from the parsed input preserving type context:
   ```
   {signifier_bullet} {body} {tags} {metadata}
   ```
   Example: `. fix kitchen faucet @plumbing due:friday`

2. Append that line to the collection via `append_to_collection()`.

3. Show a confirmation: `"Added to +home-reno (12 items)"` — no Entry is created.

4. **No Entry object is created.** The item exists only inside the collection.

### Signifier Bullets in Collection Items

Items are stored with their BuJo signifier prefix so the AI knows the type:
```
. = task idea
- = note/reference
= = journal/reflection
o = calendar/event
```

This gives the AI dimensional context during analysis — a journal entry ("feeling overwhelmed") is context, not a task.

## 2. Collection Storage Model

### File Format

Path: `~/bute/collections/<safe-name>.md`

YAML frontmatter + markdown sections for each stage artifact:

```markdown
---
name: home-reno
stage: analyzed
created: 2026-03-15T10:30:00+03:00
analyzed_at: 2026-04-01T14:00:00+03:00
---

## Input

- . fix kitchen faucet @plumbing
- . replace water heater
- - measured kitchen — 12x15
- = feeling overwhelmed by scope
- o contractor visit (Apr 15)

## Analysis

**Plumbing**
- Fix kitchen faucet (leaking, urgent)
- Replace water heater (aging, preventive)

**Renovation**
- Kitchen remodel (12x15 space, needs layout planning)

**Scheduling**
- Contractor visit Apr 15 — use as decision checkpoint
```

When executed, a third section is appended:

```markdown
## Tasks

1. Buy replacement washer for kitchen faucet
2. Replace kitchen faucet washer
3. Get water heater quotes from 2 contractors
4. Finalize kitchen layout before Apr 15 contractor visit
5. Discuss renovation scope with contractor on Apr 15
```

### Stages

| Stage | Stored Sections | Meaning |
|-------|----------------|---------|
| `raw` | Input | Accumulating items |
| `analyzed` | Input + Analysis | Organized knowledge (super note) |
| `executed` | Input + Analysis + Tasks | Actionable project (super task) |

### Frontmatter Fields

```yaml
name: string           # collection name
stage: raw|analyzed|executed
created: ISO datetime   # when first item was added
analyzed_at: ISO datetime  # when analysis was run (if applicable)
executed_at: ISO datetime  # when execution was run (if applicable)
```

### Storage API Changes (`collection_storage.py`)

Current API stores a single `content` field. New API needs to handle sectioned content:

```python
def load_collection(name, config=None) -> dict | None:
    """Returns dict with: name, stage, created, input_items,
    analysis_content, tasks_content, raw_content (full file)."""

def save_collection(name, stage, sections: dict, config=None) -> Path:
    """Save collection with sections: {'input': str, 'analysis': str, 'tasks': str}"""

def append_to_collection(name, items: list[str], config=None) -> Path:
    """Append items to the Input section. Only valid for 'raw' stage."""

def list_collections_with_meta(config=None) -> list[dict]:
    """Return list of dicts with name, stage, item_count, created."""
```

`append_to_collection()` should reject appending to analyzed/executed collections — the raw input phase is closed once processing begins. The user can always create a new collection.

## 3. `bt +collection` — View Command

### Dispatch (`cli.py`)

In `resolve_command()`, add a new section after the `@tag` filter check:

```python
# Section 5: Collection — +name [subcommand]
if first.startswith("+") and len(first) > 1:
    collection_name = first[1:]
    subcommand = rest[0] if rest else None

    if subcommand == "analyze":
        return "analyze_collection", cmd, [collection_name]
    elif subcommand == "execute":
        return "execute_collection", cmd, [collection_name]
    else:
        return "view_collection", cmd, [collection_name]
```

### View Behavior

`bt +home-reno` shows the full trail — every stage artifact the collection has:

```
╭─ home-reno (analyzed) ──────────────────────────╮
│                                                  │
│  ▸ INPUT — 5 entries                            │
│    . fix kitchen faucet @plumbing                │
│    . replace water heater                        │
│    - measured kitchen — 12x15                    │
│    = feeling overwhelmed by scope                │
│    o contractor visit (Apr 15)                   │
│                                                  │
│  ▸ ANALYSIS                                     │
│    Plumbing                                      │
│      · Fix kitchen faucet (leaking, urgent)      │
│      · Replace water heater (aging, preventive)  │
│    Renovation                                    │
│      · Kitchen remodel (12x15, needs layout)     │
│    Scheduling                                    │
│      · Contractor visit Apr 15                   │
│                                                  │
╰──────────────────────────────────────────────────╯
```

If executed, a third section appears with the numbered task list and completion status.

### Display (`display.py`)

New function: `display_collection(collection: dict)` — renders a Rich Panel with subsections for each stage. Only shows sections that exist (raw collection shows only Input).

## 4. `bt +collection analyze` — Analyze Command

### Flow

1. Load collection
2. **Guard**: if stage is not `raw`, show message:
   - `analyzed` → "Already analyzed. View with `bt +home-reno`"
   - `executed` → "Already executed. View with `bt +home-reno`"
3. **Guard**: check LLM availability
4. Send raw items to AI with analyze prompt
5. Display the AI's structured analysis
6. Prompt: "Accept this analysis?" (Y/n)
7. On confirm: save collection with stage `analyzed`, preserving Input section, adding Analysis section and `analyzed_at` timestamp
8. On reject: "Analysis discarded. Raw items preserved. Run analyze again when ready."

### AI Prompt — Analyze

System prompt context: bute's dimensions (Heart/Soul, Mind, Body), BuJo methodology.

User prompt:
```
Here are raw items from a collection called "{name}". Each item has a
signifier prefix indicating its type:
  . = task idea
  - = note/reference
  = = journal/reflection
  o = calendar/event

Items:
{items}

Cluster these items into coherent themes. For each theme:
- Give it a clear, concise name
- List the items that belong to it
- Briefly note connections or tensions between items

Be faithful to the original items — don't add, remove, or rephrase.
Organize what's there. Use the item types as context (journals reveal
feelings, notes are facts, tasks are intentions, events are commitments).
```

## 5. `bt +collection execute` — Execute Command

### Flow

1. Load collection
2. **Guard**: if stage is `executed`, show message: "Already executed. View with `bt +home-reno`"
3. **Guard**: check LLM availability
4. **If stage is `raw`**: run the full Analyze flow first (step 4-7 from Section 4). If user rejects analysis, stop.
5. **If stage is `analyzed`**: proceed directly to task generation.
6. Send analyzed content to AI with execute prompt
7. Display the AI's sequenced task list
8. Prompt: "Create these tasks?" (Y/n)
9. On confirm:
   - Parse tasks from response (numbered lines)
   - Create Entry objects (type: TASK) for each task
   - Store `collection: "{name}"` in each entry's `extra_meta`
   - Tag each entry with the collection name (sanitized) for filtering
   - Embed entries for semantic search
   - Save collection with stage `executed`, adding Tasks section and `executed_at` timestamp
   - Display confirmation: "5 tasks created from +home-reno"
10. On reject: "Task generation discarded. Analysis preserved. Run execute again when ready."

### AI Prompt — Execute

```
Here is the analyzed structure of a collection called "{name}":

{analysis_content}

Generate a sequenced list of concrete, actionable tasks that would
implement or address these themes. Requirements:
- Each task starts with a verb
- Tasks are specific enough to act on in a single session
- Tasks are ordered sequentially — each builds on the previous
- Number each task (1, 2, 3...)
- Keep the total manageable (aim for 5-15 tasks)

Output only the numbered task list, nothing else.
```

### Task Creation

Each generated task becomes a real `Entry`:
```python
entry = Entry.create(
    entry_type=EntryType.TASK,
    body=task_text,
    tags=[safe_collection_name],
    extra_meta={"collection": collection_name},
)
```

The `tags` field includes the sanitized collection name for `bt t @home-reno` filtering. The `extra_meta["collection"]` field provides the structured link back to the collection for display with `+` notation.

## 6. `bt collections` — List All Collections

### Behavior

Shows all collections with their stage and item count:

```
  Collections
  ┌────┬──────────────┬──────────┬───────┐
  │  # │ Name         │ Stage    │ Items │
  ├────┼──────────────┼──────────┼───────┤
  │  1 │ home-reno    │ executed │    12 │
  │  2 │ q2-launch    │ analyzed │     8 │
  │  3 │ bright-ideas │ raw      │    23 │
  └────┴──────────────┴──────────┴───────┘
```

Selecting a number (e.g., `bt 1`) shows the full collection view (same as `bt +home-reno`). This requires saving state with `view_name = "collections"` and mapping numbers to collection names.

### Implementation

New command `collections_cmd` registered in `cli.py`. Uses `list_collections_with_meta()` from storage and `save_state()` for number mapping.

For the number-action dispatch: when state view is `"collections"`, the number resolves to a collection name and shows the collection view. This is different from entry-based views where numbers map to ULIDs — we need to handle this case in state resolution.

## 7. Weekly Plan Integration

### How Executed Tasks Enter the Weekly Flow

Tasks generated by Execute are regular entries with `extra_meta["collection"]`. They appear in the active task pool alongside all other tasks.

During `bt plan`:
1. User sees all active tasks, including collection-generated ones
2. Collection tasks are visually grouped or marked with `+collection` in their display metadata
3. User selects tasks for the week as usual — they get tagged `@thisweek`
4. In daily log, they appear as regular tasks

### Display of Collection Tasks

In any task list view, entries with `extra_meta["collection"]` display the collection as metadata:

```
  1  . fix kitchen faucet washer          +home-reno  due:Apr 5
  2  . buy paint for bedroom              +home-reno
  3  . call Ahmed about project           @work
```

The `+collection` notation appears alongside tags and due dates in the meta column. This orients the user without requiring any special handling — the tasks are normal tasks with extra context.

### No Changes to Ritual Flow

The weekly/daily plan commands (`bt plan`, `bt ls`) don't need structural changes. Collection tasks flow through the existing `@thisweek` / `@today` tag system. The only addition is displaying `+collection` in the meta column.

## 8. AI Prompts

Two prompts replace the existing four (form, focus, finish):

| Old | New | Purpose |
|-----|-----|---------|
| `form_prompt()` | `analyze_prompt()` | Cluster raw items into themes |
| `focus_prompt()` | *(merged into execute)* | — |
| `finish_prompt()` | `execute_prompt()` | Generate sequenced tasks from analysis |

The analyze prompt incorporates what form did (categorize) but also leverages the dimensional context (signifier types) that the old form prompt didn't have.

The execute prompt incorporates both focus (identify what matters) and finish (generate tasks) into one step — the AI prioritizes and generates tasks in a single pass, informed by the analysis structure.

See Sections 4 and 5 for full prompt text.

## 9. Migration

### Commands Removed

- `bt find` — replaced by `+collection` capture syntax
- `bt form` — replaced by `bt +collection analyze`
- `bt focus` — merged into execute
- `bt finish` — replaced by `bt +collection execute`

### Files Changed

| File | Change |
|------|--------|
| `commands/ffff.py` | **Replace** — new `commands/collections.py` with `analyze_cmd`, `execute_cmd`, `view_collection_cmd`, `collections_list_cmd` |
| `collection_storage.py` | **Update** — sectioned storage model, `list_collections_with_meta()` |
| `parser.py` | **Update** — add `COLLECTION_RE`, `collection` field on `ParsedInput` |
| `capture.py` | **Update** — handle `parsed.collection` (append to collection, no Entry) |
| `cli.py` | **Update** — `+collection` dispatch in `resolve_command()`, remove FFFF registrations, add collection commands, update help text |
| `display.py` | **Update** — add `display_collection()`, show `+collection` in entry meta |
| `state.py` | **Update** — handle `collections` view type for number mapping |
| `ai/prompts.py` | **Update** — replace `form_prompt/focus_prompt/finish_prompt` with `analyze_prompt/execute_prompt` |
| `tests/test_ffff.py` | **Replace** — `tests/test_collections.py` with new test suite |

### Existing Collections

If any collections exist from the old FFFF pipeline with stages `formed`/`focused`/`finished`, they won't match the new stage names. A simple migration note in release: old collections should be recreated, or we can add a one-time migration that maps `formed` → `analyzed`, `focused/finished` → `executed` and restructures the content into sections.

## 10. CLI Help Text

```
  Capture — signifier + text
    bt t <text>                 Task       bt n <text>     Note
    bt j <text>                 Journal    bt c <text>     Calendar
    bt t <text> +<collection>   Add to collection (any signifier)

  Views
    bt t / n / j / c            View by type (task log, notes, etc.)
    bt ls                       Daily log
    bt @<tag>                   Filter by tag

  Collections — ideas to action
    bt +<name>                  View collection (full trail)
    bt +<name> analyze          AI clusters and organizes
    bt +<name> execute          AI generates sequenced tasks
    bt collections              List all collections

  Actions — number + command
    bt 1 done                   Mark complete
    bt 2 drop                   Drop task
    ...

  Rituals
    bt                          DYTS or daily log
    bt plan                     Weekly planning
    bt recap                    End-of-day summary
```

## Open Questions

1. **Re-running analyze**: Should the user be able to re-analyze after adding more items? This would require either allowing append to analyzed collections (resetting to raw) or a separate "reset" command. For now: no. Start a new collection or process what you have.

2. **Collection task ordering**: Execute generates numbered/sequenced tasks. Should the display preserve this sequence number, or just show them in creation order (which is the same, since they're created sequentially with ULIDs)?

3. **Collection completion**: When all tasks from a collection are done, should the collection status update? Could be a nice touch but not essential for v1.

4. **`bt +name` with text but no signifier**: e.g., `bt +home-reno new idea`. This has no signifier. Should it default to note (`-`)? Or require a signifier? Recommend: require a signifier to stay consistent with capture grammar.
