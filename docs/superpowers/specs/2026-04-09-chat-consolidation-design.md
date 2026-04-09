# AI Chat Consolidation Design

**Date:** 2026-04-09
**Status:** Draft

## Overview

Consolidate all AI features into `bt chat` as the single AI interface. Chat becomes an agentic session where the AI can both read and write bt data through tool calling. Standalone AI commands (`recap`, `nudges`, `topic`, `analyze`, `autotag`, `map`) are removed — their capabilities are subsumed by natural conversation with an AI that has full access to bt's data layer.

**Product story:** bt works without AI. bt works better with it. AI is an amplifier, not a dependency.

## Entry Point

`bt chat` — always starts a blank session. No arguments, no pre-loaded context, no anchored entries.

The previous `bt <n> chat` (anchored session) pattern is removed. Users start blank and pull context during the conversation.

## Architecture: Tool Calling

The AI interacts with bt through OpenAI-style function calling. Tools are defined as JSON schemas and registered with the LLM at session start. When the AI needs data or wants to act, it emits a tool call. bt executes the call (with confirmation for writes) and feeds the result back to the AI.

This approach:
- Works with all major providers (OpenAI, Anthropic, Ollama, OpenAI-compatible APIs)
- Cleanly separates intent (LLM) from execution (bt)
- Is reliable and well-supported vs. prompt-driven structured output

## AI Tools

### Read Tools

| Tool | Parameters | Returns |
|---|---|---|
| `query_entries` | `type?`, `date_from?`, `date_to?`, `tags?`, `exclude_tags?`, `status?`, `important?`, `has_due?`, `limit?` | Formatted entry list with display numbers |
| `search_text` | `query`, `type?`, `limit?` | FTS5 keyword search results |
| `search_similar` | `query`, `limit?` | Semantic similarity results (requires embeddings) |

All parameters on `query_entries` are optional — the AI composes the right combination from natural language context. Example: "what did I journal about last week?" becomes `query_entries(type="journal", date_from="2026-03-30", date_to="2026-04-05")`.

### Write Tools

| Tool | Parameters | Confirmation |
|---|---|---|
| `create_entry` | `signifier`, `body`, `tags?`, `due?`, `date?`, `time?` | Always |
| `add_tag` | `entry_ids`, `tag` | Always |
| `remove_tag` | `entry_ids`, `tag` | Always |
| `mark_done` | `entry_ids` | Always |
| `mark_dropped` | `entry_ids` | Always |
| `toggle_important` | `entry_ids` | Always |
| `update_due` | `entry_ids`, `due_date` | Always |

Write tools accept `entry_ids` as arrays for batch operations. Delete is intentionally excluded — too destructive for AI-initiated actions.

### Display Tool

| Tool | Parameters | Returns |
|---|---|---|
| `display_map` | `tag` or `entries` | Renders mind map in the existing `bt map` format |

Preserves the map rendering format from the current `display_analyze_map()` function. Invoked when the user asks the AI to "map" something.

## Context Model

**Two lanes for pulling context:**

1. **AI-driven (autonomous):** The AI decides what to fetch based on the user's natural language. "What should I focus on?" — the AI calls `query_entries` for active tasks, recent journals, overdue items, etc.

2. **User-driven (explicit):** The user types `/bt <args>` to pull specific entries. Same query syntax as the CLI: `/bt t`, `/bt @backend`, `/bt w last`, `/bt 3`.

Both lanes produce the same result: entries are displayed in the terminal and injected into the AI's message history.

**Scoping:** When the user explicitly scopes context ("based on these 3 entries only"), the AI respects the boundary and does not pull more.

## Session Lifecycle

1. User runs `bt chat`
2. System prompt + tool definitions sent to LLM
3. User types naturally — AI responds, calling tools as needed
4. Entries from `/bt` or tool calls are displayed and tracked
5. `/done` exits the session — no special exit flow

## Slash Commands

Only two survive:

| Command | Purpose |
|---|---|
| `/done` | Exit chat |
| `/bt <args>` | Explicit context pull (same syntax as CLI) |

Everything else is conversational:
- "What entries do you have?" replaces `/context`
- "Forget everything, start fresh" replaces `/clear`
- "Summarize this chat as a note" replaces `/save`

## Number Actions

When entries are displayed (from `/bt` or AI tool results), display numbers are assigned. Users act on them directly:

- `1 done` — mark entry 1 done
- `2 3 @backend` — tag entries 2 and 3
- `4 !` — toggle important

**Key distinction:**
- User types `1 done` → executes immediately (user-initiated, explicit)
- AI calls `mark_done(["ulid123"])` → confirms first (AI-initiated, needs approval)

## Confirmation UX

Every AI-initiated write action requires confirmation.

**Single-entry:**
```
AI wants to: add @reflection to "morning thoughts on project direction"
Apply? [y/n]
```

**Batch:**
```
AI wants to: add @backend to 5 entries
  1. · fix API timeout handling
  2. · refactor auth middleware
  3. · document REST endpoints
  4. · review rate limiting
  5. · update error codes
Apply? [y/n/p]
```

**Create:**
```
AI wants to create:
  . call dentist about appointment @health due:2026-04-11
Create? [y/n]
```

Rules:
- `p` (pick) on batch actions lets the user select which entries to apply to
- AI sees the confirmation result (approved/denied/partial) and adjusts accordingly
- Denied actions: AI acknowledges and moves on, does not retry
- Multiple write tools in one AI turn: confirm each sequentially

## System Prompt

The system prompt establishes:

**Identity:** A thinking partner for a BuJo-based life management system with read/write access to the user's entries. Every write action requires user approval.

**Context awareness:** Today's date, current week number, bt's entry types (task, note, journal, calendar), statuses (active, done, dropped), and tag conventions.

**Behavioral guidelines:**
- Pull entries via tools before responding to questions that require data — don't guess
- Explain *why* before proposing write actions
- Don't over-fetch — pull the minimum context needed
- Respect explicit scoping boundaries
- Use `display_map` when asked to map something

**Reused from existing code:**
- `autotag_prompt(existing_tags)` — provides the existing tag vocabulary when the AI suggests tags

**Not included:**
- Hardcoded templates for recap/nudges/topic/analyze — the AI handles these naturally from conversation

## Commands Removed from CLI

| Command | Replacement |
|---|---|
| `bt recap [period]` | "recap my week" in chat |
| `bt nudges` | "what should I focus on" in chat |
| `bt topic <name>` | "what do I have on X" in chat |
| `bt analyze @tag` | "analyze @tag" in chat |
| `bt autotag` | "tag my untagged entries" in chat |
| `bt map @tag` | "map @backend" in chat (uses `display_map` tool) |
| `bt <n> chat` | removed — start blank, pull context |

## Chat Features Removed

| Feature | Replacement |
|---|---|
| `/context` | "what entries do you have?" |
| `/clear` | "forget everything, start fresh" |
| `/save` | "summarize this chat as a note" |
| `/done` exit proposal flow | entry creation mid-conversation |

## Help Text Updates

`cli.py` help text updated to:
- Remove entries for `recap`, `nudges`, `topic`, `analyze`, `autotag`, `map`
- Update `chat` description to reflect its new role as the AI interface
- Update the AI section of `--help` to show `chat` as the single entry point

## Code Changes

### Deleted Files
- `commands/nudges.py`
- `commands/topic.py`

### Modified Files
- `commands/chat.py` — rewrite: tool calling, new session lifecycle, confirmation UX, remove exit proposal flow
- `commands/rituals.py` — remove `recap` command and `_recap_daily` (unused)
- `commands/tags.py` — remove `analyze` and `map` commands, keep `display_analyze_map()` as utility
- `ai/prompts.py` — new system prompt, remove `chat_prompt()`, `chat_summary_prompt()`, `topic_prompt()`, `nudges_prompt()`, `analyze_prompt()`. Keep `autotag_prompt()`, `format_entries()`
- `ai/llm.py` — add tool calling support to `stream_chat()` (handle tool call responses in streaming)
- `cli.py` — remove command registrations, update help text

### New Code
- `ai/tools.py` — tool schema definitions and execution layer (query, search, write actions, display_map, confirmation UX)

## Graceful Degradation

**No API key:** `bt chat` prints "Chat requires an AI provider. Run `bt init` to set one up." All other bt features work normally.

**No embeddings (fastembed not installed):** `search_similar` tool is not registered with the LLM. No error — it simply isn't available. `query_entries` and `search_text` still work.

**No vector DB (sqlite-vec not installed):** Same as above — `search_similar` not registered.

**LLM call fails mid-conversation:** Display the error, keep the session alive. User can retry or `/done` to exit.
