"""Filesystem helpers — atomic writes for entry and state files."""

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically.

    Writes to a hidden temp file in the same directory, fsyncs, then
    os.replace()s it over the target. A crash or a sync client (iCloud,
    Obsidian) reading mid-write sees either the old file or the new one,
    never a truncated one. The temp name starts with a dot and ends in
    .tmp so rglob("*.md") never matches it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp creates the temp file as 0600, and os.replace carries that
        # mode onto the destination. Preserve the existing file's mode (or
        # apply the umask-derived default for a new file) so a rewrite
        # doesn't silently tighten permissions on the user's entry files.
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        try:
            os.chmod(tmp_name, mode)
        except FileNotFoundError:
            pass
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
