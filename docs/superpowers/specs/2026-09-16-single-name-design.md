# Single Name Design — retire `bute` from the user-facing surface

**Date:** 2026-09-16
**Status:** approved, pre-publish

## Problem

A newcomer meets three unrelated names in the first 30 seconds:

| Surface | Today |
|---|---|
| GitHub repo | `bullet-terminal` |
| PyPI / `uv tool install` name | `bute` |
| Shell command | `bt` |

`bute` exists only to carry the BuJo pun (BuJo → BuTe). It is not guessable from
either of the other two names and appears in the config path (`~/.config/bute/`),
the demo data dir (`~/bute-demo`), the index file (`.index/bute.db`), the install
line, the `--help` header, and forty places in the docs.

## Decision

**"Bullet Terminal" is the name. `bt` is its initials. `bute` disappears from
everything a user can see.**

| Surface | After |
|---|---|
| GitHub repo | `bullet-terminal` (unchanged) |
| Distribution name (`pyproject.toml` `name`, PyPI, `uv tool install`) | `bullet-terminal` |
| Shell command | `bt` (unchanged) |
| Config dir | `~/.config/bt/` |
| Demo data dir | `~/bt-demo` |
| SQLite index file | `.index/bt.db` |
| Help header / `--help` docstring | `bt (Bullet Terminal)` — two words; never `BuTe` or `Bullet-Terminal` |
| Python import module | `bute` (**unchanged** — invisible to CLI users; renaming touches every file for zero visible gain) |

The pun survives as one sentence in the README ("The name mirrors BuJo…"), not as
an identifier.

## Migration (one-time, automatic, silent)

There is one real user today; both migrations exist so that reinstalling does not
lose that user's config or force a full re-embed.

1. **Config dir:** on `load_config()`, if `~/.config/bt/` does not exist and
   `~/.config/bute/` does, move the whole directory. Nothing is printed.
2. **Index file:** the existing `_migrate_from_vectors()` hook in `db.py` (runs
   once per process before the connection opens) is extended to also rename
   `.index/bute.db` → `.index/bt.db`. It already handles `.vectors/bute.db`.

`~/bute-demo` gets no migration — demo data is throwaway and is deleted on every
`bt --demo` toggle anyway.

## Out of scope

- Renaming the `bute` Python package / `src/bute/` directory.
- Removing the private Obsidian path from `CLAUDE.md` (separate pre-publish item).
- Rewriting historical docs under `docs/superpowers/` — they describe the past.
- Publishing to PyPI — verified free (`bullet-terminal` → 404 on 2026-09-16) but
  deferred until the data schema settles.

## Regression guard

`bt --help` and `bt help` output must not contain `bute` (case-insensitive). A
test asserts this so the name cannot creep back into the help surface.
