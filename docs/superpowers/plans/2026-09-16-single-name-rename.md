# Single Name Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire `bute` from every user-visible surface so the project has one name — Bullet Terminal — and one command — `bt`.

**Architecture:** Five independent renames (config dir, index file, help/docstrings, distribution name, docs), each with its own commit. The two renames that touch a real user's disk (config dir, index file) get silent one-time migrations so reinstalling keeps their config and avoids a full re-embed. The Python import package `bute` and the `src/bute/` directory are deliberately **not** renamed.

**Tech Stack:** Python 3.11, Click, tomlkit, pytest, uv (hatchling build).

**Spec:** `docs/superpowers/specs/2026-09-16-single-name-design.md`

## Global Constraints

- Shell command stays `bt`. Import module stays `bute`. `src/bute/` directory stays.
- Distribution name becomes `bullet-terminal` (verified free on PyPI 2026-09-16).
- Config dir becomes `~/.config/bt/`; demo dir `~/bt-demo`; index file `.index/bt.db`.
- The name is two words, **"Bullet Terminal"** — never `BuTe`, never `Bullet-Terminal`.
  - Rendered `bt --help` header, verbatim: `bt (Bullet Terminal) — life management CLI`
  - `main` docstring, verbatim: `bt (Bullet Terminal) — life management CLI based on Bullet Journal.`
- Drop "AI-powered" wherever it appears — the LLM layer was removed in the BYOAI change and the phrase is now false advertising.
- Migrations are silent — no console output.
- Every code step: run `uv run pytest -q -m "not slow"` before committing; all tests must pass.
- Commit messages follow the repo's `type(scope): summary` style and end with the attribution line from the session's system reminder.
- Never touch `~/.config/bute/` or the real data dir by hand — the migration code does it on the first `bt` run after reinstall.
- Do not edit files under `docs/superpowers/` other than ticking boxes in this plan.

---

### Task 0: Safety net (run this first)

The repo lives in `~/dev/`, which is **not** iCloud-synced, so GitHub is its only
off-machine copy — and as of 2026-09-16 `origin/main` is four commits behind local.
Two of those commits are today's `find` work. Close that before renaming anything.

- [ ] **Step 1: Push the unpushed commits**

```bash
git push origin main
```

Expected: `origin/main` advances from `6e6db26` to `127efc2`.
Verify: `git rev-list --left-right --count origin/main...main` prints `0	0`.

- [ ] **Step 2: Tag the last known-good commit**

```bash
git tag -a pre-rename -m "last good state before the single-name rename"
git push origin pre-rename
```

Rollback for the whole rename then becomes `git reset --hard pre-rename`.

- [ ] **Step 3: Commit this plan and its spec**

```bash
git add docs/superpowers/plans/2026-09-16-single-name-rename.md \
        docs/superpowers/specs/2026-09-16-single-name-design.md
git commit -m "docs(plan): add the single-name rename plan and spec"
git push origin main
```

---

### Task 1: Config dir `~/.config/bute/` → `~/.config/bt/` with legacy migration

**Files:**
- Modify: `src/bute/config.py:7-10` (constants), `src/bute/config.py:24-28` (`load_config`), `src/bute/config.py:41` (default comment)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `bute.config.LEGACY_CONFIG_DIR: Path` and `bute.config._migrate_legacy_config_dir() -> None`. Tests monkeypatch `bute.config.CONFIG_DIR`, `CONFIG_FILE`, `LEGACY_CONFIG_DIR` — the function must read these as module globals at call time, not capture them at import.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_config_dir_is_bt_not_bute():
    from bute.config import CONFIG_DIR, DEMO_DATA_DIR

    assert CONFIG_DIR.name == "bt"
    assert DEMO_DATA_DIR.name == "bt-demo"


def test_default_config_comment_never_says_bute():
    import tomlkit

    assert "bute" not in tomlkit.dumps(default_config()).lower()


def test_load_config_migrates_legacy_bute_dir(tmp_path, monkeypatch):
    """A pre-rename ~/.config/bute/ is moved to ~/.config/bt/ on first load."""
    legacy = tmp_path / ".config" / "bute"
    legacy.mkdir(parents=True)
    (legacy / "config.toml").write_text('[core]\nwp_day = "monday"\n')
    new_dir = tmp_path / ".config" / "bt"
    monkeypatch.setattr("bute.config.LEGACY_CONFIG_DIR", legacy)
    monkeypatch.setattr("bute.config.CONFIG_DIR", new_dir)
    monkeypatch.setattr("bute.config.CONFIG_FILE", new_dir / "config.toml")

    doc = load_config()

    assert doc["core"]["wp_day"] == "monday"
    assert (new_dir / "config.toml").exists()
    # Copied, not moved: the legacy dir stays so `git reset --hard` is a full rollback.
    assert (legacy / "config.toml").exists()


def test_load_config_keeps_existing_bt_dir_over_legacy(tmp_path, monkeypatch):
    """If both dirs exist, the new one wins and the legacy one is left alone."""
    legacy = tmp_path / ".config" / "bute"
    legacy.mkdir(parents=True)
    (legacy / "config.toml").write_text('[core]\nwp_day = "monday"\n')
    new_dir = tmp_path / ".config" / "bt"
    new_dir.mkdir(parents=True)
    (new_dir / "config.toml").write_text('[core]\nwp_day = "friday"\n')
    monkeypatch.setattr("bute.config.LEGACY_CONFIG_DIR", legacy)
    monkeypatch.setattr("bute.config.CONFIG_DIR", new_dir)
    monkeypatch.setattr("bute.config.CONFIG_FILE", new_dir / "config.toml")

    doc = load_config()

    assert doc["core"]["wp_day"] == "friday"
    assert legacy.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_config.py -k "bute or legacy"`
Expected: 4 failed — `AttributeError: ... has no attribute 'LEGACY_CONFIG_DIR'` for the two migration tests, assertion failures for the other two.

- [ ] **Step 3: Implement**

In `src/bute/config.py`, replace lines 3–10:

```python
import shutil
from pathlib import Path

import tomlkit

CONFIG_DIR = Path.home() / ".config" / "bt"
LEGACY_CONFIG_DIR = Path.home() / ".config" / "bute"  # pre-rename installs
CONFIG_FILE = CONFIG_DIR / "config.toml"
DATA_DIR_DEFAULT = Path.home() / "bullet-terminal"
DEMO_DATA_DIR = Path.home() / "bt-demo"
TOUR_DONE = CONFIG_DIR / ".tour_done"
```

Replace `load_config` (currently lines 24–28):

```python
def _migrate_legacy_config_dir() -> None:
    """One-time *copy* of ~/.config/bute/ → ~/.config/bt/. Silent; never clobbers.

    Copy, not move, deliberately: the legacy dir is left intact so that rolling the
    code back to `pre-rename` needs no manual filesystem repair. config.toml is 15
    lines — the duplicate costs nothing, and it holds the only setting that is
    painful to lose (`data_dir`, which points at the Obsidian vault).
    """
    if CONFIG_DIR.exists() or not LEGACY_CONFIG_DIR.exists():
        return
    CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(LEGACY_CONFIG_DIR, CONFIG_DIR)


def load_config() -> tomlkit.TOMLDocument:
    """Load config from disk. Returns empty doc if file doesn't exist."""
    _migrate_legacy_config_dir()
    if not CONFIG_FILE.exists():
        return tomlkit.document()
    return tomlkit.parse(CONFIG_FILE.read_text())
```

Change line 41 (inside `default_config`):

```python
    doc.add(tomlkit.comment("bt (Bullet Terminal) configuration"))
```

Change line 1 docstring to `"""Configuration management for bt."""`.

- [ ] **Step 4: Guard the real config dir from the whole test suite**

`load_config()` now has a side effect that moves a directory in `$HOME`. Fourteen
test files do not use the `tmp_config` fixture; none of them reach `load_config()`
today, but nothing stops the next one from doing so and silently moving the real
`~/.config/bute/` mid-test-run. Close it permanently with an autouse fixture.

Append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _never_migrate_the_real_config_dir(tmp_path, monkeypatch):
    """Point the legacy-config lookup at a path that does not exist.

    load_config() moves ~/.config/bute/ → ~/.config/bt/ on first call. No test may
    ever trigger that against the user's real home directory.
    """
    monkeypatch.setattr(
        "bute.config.LEGACY_CONFIG_DIR", tmp_path / "no-legacy-config", raising=False
    )
```

The two migration tests in Step 1 monkeypatch `LEGACY_CONFIG_DIR` themselves; the
later `monkeypatch.setattr` inside the test body wins over the autouse fixture, so
they keep working.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_config.py`
Expected: all pass (existing tests plus the 4 new ones).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

Confirm the real config dir was not touched: `ls ~/.config/bute/ ~/.config/bt/ 2>&1`
Expected: `~/.config/bute/` still holds `config.toml`, and `~/.config/bt/` does not
exist yet. The real copy happens in Task 4 Step 6, on the first run of the
reinstalled tool — not during a test run.

- [ ] **Step 7: Commit**

```bash
git add src/bute/config.py tests/conftest.py tests/test_config.py
git commit -m "refactor(config): move config dir to ~/.config/bt with silent legacy migration"
```

---

### Task 2: Index file `.index/bute.db` → `.index/bt.db` with migration

**Files:**
- Modify: `src/bute/db.py:31-38` (`_db_path`), `src/bute/db.py:46-48` (call site in `get_connection`), `src/bute/db.py:247-262` (`_migrate_from_vectors` → `_migrate_index_file`)
- Modify: `src/bute/completion.py:13`
- Modify: `src/bute/guide.py:98`, `src/bute/guide.py:202`
- Modify: `tests/test_db.py:33`
- Create: `tests/test_db_migration.py`

**Interfaces:**
- Consumes: `tmp_data` fixture from `tests/conftest.py` (monkeypatches `bute.config.DATA_DIR_DEFAULT`, closes the DB after).
- Produces: `bute.db._migrate_index_file(config=None) -> None` replacing `_migrate_from_vectors`. No other module imports the old name (verified with grep), so no shim is needed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_migration.py`:

```python
"""One-time moves of the SQLite index to .index/bt.db."""

from bute.db import _db_path, _migrate_index_file


def test_db_path_is_bt_db(tmp_data):
    assert _db_path().name == "bt.db"
    assert _db_path().parent == tmp_data / ".index"


def test_migrate_renames_bute_db_to_bt_db(tmp_data):
    index = tmp_data / ".index"
    index.mkdir(parents=True)
    (index / "bute.db").write_bytes(b"old-index")

    _migrate_index_file()

    assert (index / "bt.db").read_bytes() == b"old-index"
    assert not (index / "bute.db").exists()


def test_migrate_moves_vectors_db_to_bt_db(tmp_data):
    old_dir = tmp_data / ".vectors"
    old_dir.mkdir(parents=True)
    (old_dir / "bute.db").write_bytes(b"very-old-index")

    _migrate_index_file()

    assert (tmp_data / ".index" / "bt.db").read_bytes() == b"very-old-index"
    assert not old_dir.exists()


def test_migrate_keeps_existing_bt_db(tmp_data):
    index = tmp_data / ".index"
    index.mkdir(parents=True)
    (index / "bt.db").write_bytes(b"current")
    (index / "bute.db").write_bytes(b"stale")

    _migrate_index_file()

    assert (index / "bt.db").read_bytes() == b"current"


def test_migrate_is_a_noop_on_fresh_data_dir(tmp_data):
    _migrate_index_file()
    assert not (tmp_data / ".index" / "bt.db").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_db_migration.py`
Expected: `ImportError: cannot import name '_migrate_index_file'`.

- [ ] **Step 3: Implement**

In `src/bute/db.py`, replace `_db_path` (lines 31–38):

```python
def _db_path(config=None) -> Path:
    """Return path to the SQLite index file: <data_dir>/.index/bt.db"""
    if _db_path_override is not None:
        return _db_path_override
    data_dir = get_data_dir(config)
    index_dir = data_dir / ".index"
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir / "bt.db"
```

In `get_connection`, change the call at line 48 from `_migrate_from_vectors(config)` to `_migrate_index_file(config)`.

Replace `_migrate_from_vectors` (lines 247–262) with:

```python
def _migrate_index_file(config=None) -> None:
    """One-time move of older index files to .index/bt.db. Silent; never clobbers.

    Handles both prior layouts: .index/bute.db (pre-rename) and .vectors/bute.db
    (before the index moved out of .vectors/).
    """
    data_dir = get_data_dir(config)
    new_dir = data_dir / ".index"
    new_path = new_dir / "bt.db"

    if not new_path.exists():
        for old_path in (new_dir / "bute.db", data_dir / ".vectors" / "bute.db"):
            if old_path.exists():
                new_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                break

    old_dir = data_dir / ".vectors"
    if old_dir.exists() and not any(old_dir.iterdir()):
        old_dir.rmdir()
```

Change `src/bute/db.py:1` to `"""SQLite structured index for bt entries.`.

In `src/bute/completion.py:13` change `"bute.db"` to `"bt.db"`:

```python
        if not (get_data_dir(config) / ".index" / "bt.db").exists():
```

In `src/bute/guide.py:98` change `bute.db` to `bt.db` inside the tree diagram (keep the column alignment — `bt.db` is two characters shorter, so add two spaces before `SQLite index`):

```
    └── bt.db             SQLite index (FTS5 + vectors)
```

In `src/bute/guide.py:202` change `` `.index/bute.db` `` to `` `.index/bt.db` ``.

In `tests/test_db.py:33` change `index_dir / "bute.db"` to `index_dir / "bt.db"`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_db_migration.py tests/test_db.py`
Expected: all pass.

- [ ] **Step 5: Run the full suite and confirm no stray references**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

Run: `grep -rn "bute\.db\|_migrate_from_vectors" src/ tests/`
Expected: exactly the two `bute.db` mentions inside `_migrate_index_file` in `src/bute/db.py` and the fixtures in `tests/test_db_migration.py`; nothing else.

- [ ] **Step 6: Commit**

```bash
git add src/bute/db.py src/bute/completion.py src/bute/guide.py tests/test_db.py tests/test_db_migration.py
git commit -m "refactor(db): rename index file to .index/bt.db with silent migration"
```

---

### Task 3: Help surface, install hint, and module docstrings

**Files:**
- Modify: `src/bute/__init__.py:1`
- Modify: `src/bute/cli.py:1`, `src/bute/cli.py:264`, `src/bute/cli.py:421`
- Modify: `src/bute/commands/search.py:13`
- Modify: module docstrings (exact list in Step 3)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `runner`, `tmp_config`, `tmp_data` fixtures from `tests/conftest.py`. `bt --help` is rendered by `DwnGroup.format_help` → `_print_help()` (`src/bute/cli.py:50-52`), which already says "Bullet-Terminal" in its header; the `main` docstring at line 421 is what Click shows for `--help` in other contexts and what still says "BuTe" and "AI-powered".

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_help_never_says_bute(runner, tmp_config, tmp_data):
    """The only public names are 'Bullet Terminal' and 'bt'."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "bute" not in result.output.lower()
    assert "ai-powered" not in result.output.lower()
    assert "Bullet Terminal" in result.output
    assert "Bullet-Terminal" not in result.output

    from bute.cli import main as cli_main
    assert "bute" not in (cli_main.__doc__ or "").lower()
    assert "Bullet Terminal" in (cli_main.__doc__ or "")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_cli.py::test_help_never_says_bute`
Expected: FAIL on the `__doc__` assertion (`"bt (BuTe) — AI-powered ..."` contains "bute").

- [ ] **Step 3: Implement**

`src/bute/__init__.py:1`:

```python
"""bt (Bullet Terminal) — CLI life management system based on the Bullet Journal method."""
```

`src/bute/cli.py:421` — the `main` docstring:

```python
    """bt (Bullet Terminal) — life management CLI based on Bullet Journal."""
```

`src/bute/cli.py:264`:

```python
    """Print the full bt help using Rich."""
```

`src/bute/cli.py:272` — the rendered help header. It currently hyphenates the name
(`Bullet-Terminal`), which is a third spelling; the name is two words:

```python
    console.print(Align.center(Text.from_markup("[bold]bt[/bold] (Bullet Terminal) — life management CLI")))
```

`src/bute/cli.py:1`:

```python
"""CLI entry point and custom command routing for bt."""
```

`src/bute/commands/search.py:13` — the install hint shown when embeddings are missing. Replace the `bute[embeddings]` line with:

```python
    "  Install with: [bold]uv tool install --from . --with fastembed --with sqlite-vec bullet-terminal --force[/bold]"
```

Module docstrings — one `sed` pass, then verify. These are internal but the rename is complete only if a `grep` of the tree turns up no stray `bute` prose:

```bash
cd /Users/khalidal-ghamdi/dev/bullet-terminal
sed -i '' \
  -e '1s/for bute\./for bt./' \
  -e '1s/for bute entries\./for bt entries./' \
  -e '1s/for bute using/for bt using/' \
  -e '1s/for bute (/for bt (/' \
  -e '1s/for bute — /for bt — /' \
  -e '1s/for bute capture/for bt capture/' \
  src/bute/models.py src/bute/parser.py src/bute/display.py src/bute/errors.py \
  src/bute/storage.py src/bute/ai/vectors.py src/bute/ai/embeddings.py \
  src/bute/commands/search.py src/bute/commands/rituals.py src/bute/commands/views.py
sed -i '' -e 's/"""A single bute entry — /"""A single bt entry — /' src/bute/models.py
sed -i '' -e 's/"""Base error for bute\."""/"""Base error for bt."""/' src/bute/errors.py
sed -i '' -e 's#~/bute/linelog#<data_dir>/linelog#' src/bute/linelog.py
```

- [ ] **Step 4: Verify nothing user-facing or prose-level says `bute`**

Run:

```bash
grep -rniE '\bbute\b|BuTe\b' src/ \
  | grep -vE 'from bute|import bute|bute\.(config|db|models|storage|display|parser|cli|commands|ai|state|linelog|guide|migration|fsutil|errors|completion)|LEGACY_CONFIG_DIR'
```

Expected: no output. (`\bbute\b` is deliberate — it skips the word "attri**bute**" in
`src/bute/commands/action.py:344`, which a plain `-i bute` grep otherwise reports.) Any remaining hit is a prose mention to fix by hand in the same style as above.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass, including `test_help_never_says_bute`.

- [ ] **Step 6: Commit**

```bash
git add src/bute tests/test_cli.py
git commit -m "docs(help): name the tool 'bt (Bullet Terminal)' everywhere users can see"
```

---

### Task 4: Distribution name `bute` → `bullet-terminal`

**Files:**
- Modify: `pyproject.toml:2`
- Regenerate: `uv.lock`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the installed tool is named `bullet-terminal`; the `bt` executable is unchanged. `pyproject.toml:32` (`bt = "bute.cli:main"`) and `:39` (`packages = ["src/bute"]`) stay exactly as they are — they reference the import module, not the distribution.

- [ ] **Step 1: Change the distribution name**

`pyproject.toml:2`:

```toml
name = "bullet-terminal"
```

- [ ] **Step 2: Regenerate the lockfile**

Run: `uv lock`
Expected: `uv.lock` now has `name = "bullet-terminal"` for the root package (`grep -n -A2 '^name = "bullet-terminal"' uv.lock` shows `source = { editable = "." }`).

- [ ] **Step 3: Verify the build and the extras spelling**

Run: `uv build 2>&1 | tail -2`
Expected: `dist/bullet_terminal-0.1.0-py3-none-any.whl` and `dist/bullet_terminal-0.1.0.tar.gz` (hatchling normalises the hyphen to an underscore in filenames — that is correct).

Run: `rm -rf dist/`

- [ ] **Step 4: Run the tests**

Run: `uv sync --extra embeddings --extra dev && uv run pytest -q -m "not slow"`
Expected: all pass.

- [ ] **Step 5: Replace the installed tool**

`uv tool` refuses to install a second package that provides the same `bt` executable, so the old one must go first:

```bash
uv tool uninstall bute
uv tool install --from . --with fastembed --with sqlite-vec bullet-terminal --force --reinstall
```

Run: `uv tool list`
Expected: a `bullet-terminal v0.1.0` entry with `- bt` beneath it, and no `bute` entry.

- [ ] **Step 6: Verify the migrations ran against the real install**

Run: `bt --version && bt tags >/dev/null && ls ~/.config/bt/ && ls ~/Documents/Obsidian/Home/bullet-terminal/.index/`
Expected: `bt, version 0.1.0`; `~/.config/bt/` now contains `config.toml` (moved from `~/.config/bute/`, which no longer exists); `.index/` contains `bt.db` and no `bute.db`. `bt tags` should return instantly — if it prints "Building search index…" the index migration did not fire; stop and investigate Task 2's `_migrate_index_file` before continuing.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: rename distribution to bullet-terminal; bt stays the command"
```

---

### Task 5: README and CLAUDE.md

**Files:**
- Modify: `README.md:1-6`, `README.md:12`, `README.md:16`, `README.md:53`, `README.md:67`, `README.md:230`
- Modify: `CLAUDE.md:5-7`, `CLAUDE.md:22`, `CLAUDE.md:30`, and every grammar example line that begins with `bute `

**Interfaces:**
- Consumes: the new install spelling from Task 4 and the paths from Tasks 1–2.

- [ ] **Step 1: README — add the "why the name" sentence and fix paths**

Replace `README.md:5` (the paragraph beginning "bt stays opinionated and lean.") with:

```markdown
bt stays opinionated and lean. The goal is to capture fast, plan each morning, and keep the mental loop closed — in a terminal. The name mirrors BuJo (Bullet Journal): same family, different medium.
```

Replace the install block (`README.md:11-13`):

````markdown
```bash
uv tool install 'bullet-terminal[embeddings] @ git+https://github.com/emailkgnow/bullet-terminal'
```
````

Replace `README.md:15` (the bullet about fastembed) with:

```markdown
- `[embeddings]` pulls in `fastembed` + `sqlite-vec` for `bt like` (local semantic search). Drop the extra if you only want the core BuJo loop: `uv tool install 'bullet-terminal @ git+https://github.com/emailkgnow/bullet-terminal'`.
```

Replace `README.md:16`:

```markdown
- Run `bt init` once to create `~/.config/bt/config.toml` and `~/bullet-terminal/`.
```

Then:

```bash
sed -i '' -e 's#\.index/bute\.db#.index/bt.db#g' README.md
```

This rewrites lines 53 and 230. Fix line 67 by hand — it is inside the tree diagram and needs its alignment kept:

```
│   └── bt.db           # SQLite index (metadata + FTS5 + vectors) — regenerable
```

- [ ] **Step 2: Verify the README**

Run: `grep -niE '\bbute\b|BuTe\b' README.md`
Expected: no output.

Sanity-check that the `[embeddings]` extra resolves, using the local source (the
`git+https://` form in the README cannot be tested until the repo is public — it
will 404 against a private repo even with valid credentials in some setups):

```bash
uv tool install --from '.[embeddings]' bullet-terminal --force --reinstall >/dev/null
uv tool list | grep -A1 bullet
```

Expected: `bullet-terminal v0.1.0` / `- bt`.

Then confirm the extra actually landed: `bt like productivity | head -3`
Expected: results, not the "Install with:" hint from `src/bute/commands/search.py:13`.

- [ ] **Step 3: CLAUDE.md — explicit edits first, then the sweep**

Replace `CLAUDE.md:5-7`:

```markdown
## What is bt?

bt (Bullet Terminal) is a CLI life management system based on the Bullet Journal methodology. Single user, local data, plain Markdown files. The name mirrors BuJo (Bullet Journal) — same family, different medium. The distribution is `bullet-terminal`; the Python import package is still `bute` (invisible to users, so it was never renamed).
```

Replace `CLAUDE.md:22`:

```bash
uv tool install --from . --with fastembed --with sqlite-vec bullet-terminal --force --reinstall
```

Replace `CLAUDE.md:30`:

```markdown
### CLI Dispatch (cli.py — DwnGroup)
```

Now the sweep. `src/bute` must survive (it is the import path on line 19), so protect it, replace every other whole-word `bute` with `bt`, then restore:

```bash
cd /Users/khalidal-ghamdi/dev/bullet-terminal
perl -pi -e 's#src/bute#__KEEP_SRC_BUTE__#g; s/\bbute\b/bt/g; s#__KEEP_SRC_BUTE__#src/bute#g' CLAUDE.md
```

(`perl`, not `sed`: macOS BSD `sed` does not understand `\b` — verified, it leaves the text untouched.)

- [ ] **Step 4: Verify CLAUDE.md**

Run: `grep -n "bute" CLAUDE.md`
Expected: exactly the lines containing `src/bute` (the coverage command and the note in the "What is bt?" paragraph) — nothing else.

Run: `grep -n "^bt " CLAUDE.md | wc -l`
Expected: ≥ 50 (every grammar example now starts with `bt `).

- [ ] **Step 5: Run the tests one last time**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: one name — Bullet Terminal, command bt; retire bute from README and CLAUDE.md"
```

---

### Task 6: Final sweep

**Files:** none new.

- [ ] **Step 1: Tree-wide grep for anything user-visible**

Run:

```bash
grep -rniE '\bbute\b|BuTe\b' README.md CLAUDE.md pyproject.toml src/ tests/ \
  | grep -vE 'from bute|import bute|bute\.(config|db|models|storage|display|parser|cli|commands|ai|state|linelog|guide|migration|fsutil|errors|completion)|src/bute|LEGACY_CONFIG_DIR|"bute\.db"|bute-demo'
```

Expected: no output. The surviving `bute` mentions are exactly: the import path
`src/bute` and `from bute...` lines, `LEGACY_CONFIG_DIR`, and the two legacy
filenames inside the migration functions and their tests — all intentional per the
spec's "Out of scope".

Any other hit is a leftover; fix it in the style of the task it belongs to and
amend that task's commit (nothing in this plan pushes, so amending is safe).

- [ ] **Step 2: Confirm the installed tool end to end**

Run: `bt --help | head -3 && bt find dentist | head -5`
Expected: header reads `bt (Bullet Terminal) — life management CLI` (two words, no
hyphen); find returns results without printing "Building search index…".

- [ ] **Step 3: Report**

Report the six commit hashes and the outputs of Step 1 and Step 2 verbatim. Do not push.

---

## Rollback

`git reset --hard pre-rename` is the entire rollback. Neither on-disk change needs
manual repair, by design:

- **Config** — Task 1 *copies* `~/.config/bute/` → `~/.config/bt/` and leaves the
  original in place. Code reset to `pre-rename` reads `~/.config/bute/` and finds it
  exactly as it was. Delete the now-unused copy once you're confident:
  `rm -rf ~/.config/bt`.
- **Index** — Task 2 moves `.index/bute.db` → `.index/bt.db`. Code reset to
  `pre-rename` finds no `bute.db`, creates an empty one, and `reconcile_index()`
  repopulates it from the `.md` files on the next read. Self-healing, at the cost of
  re-embedding 325 entries once. The orphaned `bt.db` (2.7 MB) can be deleted.

Also swap the installed tool back:

```bash
uv tool uninstall bullet-terminal
uv tool install --from . --with fastembed --with sqlite-vec bute --force --reinstall
```

**Do not restore `~/.config/bute/config.toml.bak`.** It is stale — it carries
`data_dir = "~/bullet-terminal"` instead of the real
`~/Documents/Obsidian/Home/bullet-terminal`, so restoring it points bt at an empty
directory and every entry appears to have vanished. The live `config.toml` is the
only good copy, which is precisely why Task 1 copies rather than moves it.

Entry data is never touched by this plan.
