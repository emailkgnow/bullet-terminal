# bt Onboarding Design

## Philosophy

The onboarding is a **learn-by-doing experience**, not a tutorial. The user captures real entries into their system while learning the BuJo methodology through the CLI. Each phase introduces one entry type, prompts the user to create one, and moves on. By the end, they have a populated daily log and understand the core loop.

## Trigger

First `bt` run with zero entries on disk. After onboarding, subsequent `bt` runs follow the normal DYTS → daily log flow.

## Flow

```
bt (first run, no entries)
│
├── Phase 1: Welcome
│   "bt is inspired by the Bullet Journal..."
│   Show 4 entry types: . task  = journal  - note  o event
│
├── Phase 2: Tasks (the core)
│   "Get everything off your mind — one task per line."
│   ┌─────────────────────────────────────────┐
│   │  .  call dentist                        │
│   │  .  fix backend auth bug                │
│   │  .  plan weekend trip                   │
│   │  .  (blank line to stop)                │
│   └─────────────────────────────────────────┘
│   → Show all tasks
│   → Checkbox: "Which matter this week?" → @thisweek
│   → Checkbox: "Which to focus on today?" → @today
│
├── Phase 3: Journal (the why)
│   "Write a reflection. How are you feeling right now?"
│   ┌─────────────────────────────────────────┐
│   │  =  feeling motivated to get organized  │
│   └─────────────────────────────────────────┘
│
├── Phase 4: Notes (the what)
│   "A fact, idea, or reference to remember."
│   ┌─────────────────────────────────────────┐
│   │  -  OAuth2 tokens expire in 30 days     │
│   └─────────────────────────────────────────┘
│
├── Phase 5: Calendar (the when)
│   "An event with a time or date."
│   "Use t:HHMM for time, d:MMDD for date."
│   ┌─────────────────────────────────────────┐
│   │  o  standup t:0900                      │
│   └─────────────────────────────────────────┘
│
├── Phase 6: Habits (optional)
│   "Track daily habits? One per line."
│   ┌─────────────────────────────────────────┐
│   │  >  exercise                            │
│   │  >  reading                             │
│   │  >  (blank to stop)                     │
│   └─────────────────────────────────────────┘
│
└── Phase 7: Recap
    Show daily log with everything captured
    ┌─────────────────────────────────────────┐
    │  Today — Mon Mar 30                     │
    │   1  o  standup                  9:00 AM│
    │   2  .  call dentist    @thisweek @today│
    │   3  .  fix backend auth  @thisw @today │
    │   4  =  feeling motivated...            │
    │   5  -  OAuth2 tokens expire in 30 days │
    │  ──────────────────────────────────────  │
    │   6  ○  exercise                        │
    │   7  ○  reading                         │
    └─────────────────────────────────────────┘
    Quick reference card
    "You're set. Go."
```

## Design Principles

1. **Every phase is skippable** — blank line moves on. Impatient users can rush through.
2. **Prompt suffixes teach signifiers** — `. ` for tasks, `= ` for journals, `- ` for notes, `o ` for events. Muscle memory.
3. **Real data, not examples** — everything captured goes into the actual system. No sandbox.
4. **One sitting** — 3-5 minutes total. No multi-session state tracking.
5. **Reuse existing infrastructure** — all capture goes through `process_dump_line()`, all display through `display_entry_list()`.

## What it teaches (implicitly)

- The 4 entry types and their signifiers
- The capture grammar: `bt t <text>`, `bt j <text>`, etc.
- The focus system: @thisweek scopes the week, @today scopes the day
- Calendar metadata: `t:HHMM`, `d:MMDD`
- Habits as daily check-ins
- The daily log as the home view
- Number-based actions: `bt 1 done`

## What it doesn't teach (saved for discovery)

- Tags (@tag), due dates (due:), important (!)
- Actions beyond `done` (drop, delete, edit, undo, later, untag)
- Rituals (bt dp, bt wp)
- AI features (search, review, topic, nudges)
- Line log, weekly plan, views with filters

These are discoverable via `bt --help` and `bt start`.

## Implementation

See the plan file for technical details. Key files:
- `src/bute/commands/onboarding.py` (new)
- `src/bute/cli.py` (first-run check in main())
- `src/bute/storage.py` (has_any_entries())
