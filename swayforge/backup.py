"""Automatic settings backups: a small archive of everything swayforge needs after a reset.

Off by default. With Settings → System & files → "Automatic backup" on, a backup is written at
login when the last one is older than the chosen number of days – into a folder of your choice
(a second drive or a synced folder makes sense), keeping only the newest few.
Restore: `./install.sh --restore FILE` after a reset, or `swayforge restore FILE`.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import paths, settings

NAME = "swayforge-backup-"


def folder(s: dict | None = None) -> Path:
    s = s or settings.load()
    return Path(os.path.expanduser(s["backup"]["dir"] or "~/Backups/swayforge"))


def all_backups(s: dict | None = None) -> list[Path]:
    """Newest first – automatic ones in the backup folder plus manual exports in your home folder."""
    found = []
    for d in {folder(s), paths.HOME}:
        if d.is_dir():
            found += [p for p in d.glob(NAME + "*.tar.gz") if p.is_file()]
    if (paths.HOME / "swayforge-backup.tar.gz").is_file():
        found.append(paths.HOME / "swayforge-backup.tar.gz")
    return sorted(set(found), key=lambda p: p.stat().st_mtime, reverse=True)


def last(s: dict | None = None) -> Path | None:
    b = all_backups(s)
    return b[0] if b else None


def make(s: dict | None = None) -> Path:
    """Write a backup now and thin out old automatic ones."""
    from . import tools
    s = s or settings.load()
    d = folder(s)
    d.mkdir(parents=True, exist_ok=True)
    out = d / (NAME + time.strftime("%Y%m%d-%H%M") + ".tar.gz")
    tools.export(str(out), quiet=True)
    keep = max(1, int(s["backup"]["keep"]))
    for old in sorted(d.glob(NAME + "*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
    return out


def due(s: dict | None = None, now: float | None = None) -> bool:
    s = s or settings.load()
    if not s["backup"]["auto"]:
        return False
    d = folder(s)
    newest = max((p.stat().st_mtime for p in d.glob(NAME + "*.tar.gz")), default=0.0) if d.is_dir() else 0.0
    return (now or time.time()) - newest >= max(1, int(s["backup"]["every_days"])) * 86400


def auto_run(s: dict | None = None) -> Path | None:
    """Called at session start: back up when it's time. Never raises."""
    try:
        s = s or settings.load()
        return make(s) if due(s) else None
    except Exception as e:                       # noqa: BLE001
        from . import screensaver
        screensaver.log(f"automatic backup failed: {type(e).__name__}: {e}")
        return None
