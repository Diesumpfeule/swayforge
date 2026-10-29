"""Clipboard history: searchable, with pins, and it forgets on its own.

Everything you copy (text and pictures) lands in one small database in your home folder
(~/.local/share/swayforge/clipboard.db, readable only by you). It is trimmed by count and by age
(Settings → Clipboard). Pinned entries are kept until you unpin them. Passwords copied from a
password manager (KeePassXC, Bitwarden … mark them "sensitive") are never stored.

Pieces:
- `swayforge clip watch` – started by Sway: two `wl-paste --watch` helpers + a trim every minute,
- `swayforge clip store` – what wl-paste calls for every copy (content on stdin),
- `swayforge clip`       – Rofi picker with search (Super+V),
- the swayforge app has a full page with search, picture previews, pin/delete.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

from . import paths

MAX_BYTES = 8 * 1024 * 1024          # bigger copies (a whole video frame dump …) are not kept
AGES = [("Forever", 0), ("15 minutes", 15), ("1 hour", 60), ("1 day", 1440), ("1 week", 10080), ("30 days", 43200)]
COUNTS = [("25", 25), ("100", 100), ("250", 250), ("1000", 1000)]


def db_path() -> Path:
    return paths.XDG_DATA / "swayforge/clipboard.db"


def pause_flag() -> Path:
    return paths.STATE_DIR / "clipboard-paused"


def connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    con = sqlite3.connect(p, timeout=5)
    if new:
        os.chmod(p, 0o600)
    con.execute("""CREATE TABLE IF NOT EXISTS clip (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT UNIQUE, mime TEXT, data BLOB, preview TEXT,
        size INTEGER, created REAL, used REAL, pinned INTEGER DEFAULT 0)""")
    return con


def _conf() -> dict:
    from . import settings
    try:
        return settings.load()["clipboard"]
    except Exception:                       # noqa: BLE001 – a broken settings file must not stop copying
        from .settings import DEFAULTS
        return DEFAULTS["clipboard"]


def preview_of(mime: str, data: bytes) -> str:
    if mime.startswith("image/"):
        w = h = 0
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
            w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        return f"[picture {w}×{h}]" if w else f"[picture {mime[6:]}]"
    text = data.decode("utf-8", "replace")
    one = " ".join(text.split())
    return one[:300] if one else "(blank)"


def store(data: bytes, mime: str = "text/plain", now: float | None = None, conf: dict | None = None) -> int | None:
    """Add one copy. Returns the entry id, or None when it was skipped."""
    conf = conf or _conf()
    now = now or time.time()
    if not conf.get("enabled", True) or pause_flag().exists():
        return None
    if os.environ.get("CLIPBOARD_STATE") == "sensitive" and conf.get("skip_sensitive", True):
        return None
    if not data or len(data) > MAX_BYTES:
        return None
    if mime.startswith("image/") and not conf.get("images", True):
        return None
    if not mime.startswith("image/") and not data.strip():
        return None
    h = hashlib.sha256(mime.encode() + b"\0" + data).hexdigest()
    with closing(connect()) as con, con:
        row = con.execute("SELECT id FROM clip WHERE hash=?", (h,)).fetchone()
        if row:                              # copied again → back to the top
            con.execute("UPDATE clip SET used=? WHERE id=?", (now, row[0]))
            cid = row[0]
        else:
            cid = con.execute("INSERT INTO clip(hash,mime,data,preview,size,created,used) VALUES(?,?,?,?,?,?,?)",
                              (h, mime, data, preview_of(mime, data), len(data), now, now)).lastrowid
    trim(conf=conf, now=now)
    return cid


def trim(conf: dict | None = None, now: float | None = None) -> int:
    """Forget what is too old or beyond the maximum count (pinned entries stay). Returns how many."""
    conf = conf or _conf()
    now = now or time.time()
    gone = 0
    if not db_path().exists():
        return 0
    with closing(connect()) as con, con:
        age = int(conf.get("max_age", 0) or 0)
        if age > 0:
            gone += con.execute("DELETE FROM clip WHERE pinned=0 AND used < ?", (now - age * 60,)).rowcount
        keep = max(1, int(conf.get("max_items", 100) or 100))
        gone += con.execute("""DELETE FROM clip WHERE pinned=0 AND id NOT IN
                               (SELECT id FROM clip WHERE pinned=0 ORDER BY used DESC LIMIT ?)""", (keep,)).rowcount
    if gone:
        with closing(connect()) as con:
            con.execute("VACUUM")             # really gone from the disk, not just marked free
    return gone


def items(query: str = "", limit: int = 500) -> list[dict]:
    if not db_path().exists():
        return []
    q = f"%{query.strip()}%"
    with closing(connect()) as con:
        rows = con.execute("""SELECT id, mime, preview, size, created, used, pinned FROM clip
                              WHERE preview LIKE ? OR (mime LIKE 'text/%' AND CAST(data AS TEXT) LIKE ?)
                              ORDER BY pinned DESC, used DESC LIMIT ?""", (q, q, limit)).fetchall()
    return [{"id": r[0], "mime": r[1], "preview": r[2], "size": r[3], "created": r[4], "used": r[5],
             "pinned": bool(r[6]), "image": r[1].startswith("image/")} for r in rows]


def get(cid: int) -> tuple[str, bytes] | None:
    with closing(connect()) as con:
        r = con.execute("SELECT mime, data FROM clip WHERE id=?", (cid,)).fetchone()
    return (r[0], bytes(r[1])) if r else None


def copy(cid: int) -> bool:
    got = get(cid)
    if not got:
        return False
    mime, data = got
    try:
        subprocess.Popen(["wl-copy", "--type", mime], stdin=subprocess.PIPE, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).communicate(data, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    with closing(connect()) as con, con:
        con.execute("UPDATE clip SET used=? WHERE id=?", (time.time(), cid))
    return True


def pin(cid: int, on: bool = True) -> None:
    with closing(connect()) as con, con:
        con.execute("UPDATE clip SET pinned=? WHERE id=?", (1 if on else 0, cid))


def delete(cid: int) -> None:
    with closing(connect()) as con, con:
        con.execute("DELETE FROM clip WHERE id=?", (cid,))


def clear(keep_pinned: bool = True) -> None:
    if not db_path().exists():
        return
    with closing(connect()) as con, con:
        con.execute("DELETE FROM clip" + (" WHERE pinned=0" if keep_pinned else ""))
    with closing(connect()) as con:
        con.execute("VACUUM")
    if not keep_pinned:
        subprocess.run(["wl-copy", "--clear"], capture_output=True)


def set_paused(on: bool) -> None:
    f = pause_flag()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
    else:
        f.unlink(missing_ok=True)


# ── command line ─────────────────────────────────────────────────────
def _store_main() -> int:
    mime = sys.argv[sys.argv.index("--mime") + 1] if "--mime" in sys.argv else "text/plain"
    data = sys.stdin.buffer.read()
    if mime == "image" and data:              # wl-paste --type image: find out which kind
        mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg" if data[:2] == b"\xff\xd8" else \
            "image/gif" if data[:3] == b"GIF" else "image/webp" if data[8:12] == b"WEBP" else "image/png"
    store(data, mime)
    return 0


def watch() -> int:
    """Long-running: copy watchers + trimming every minute. Started by Sway (exec_always)."""
    from shutil import which
    if not which("wl-paste"):
        print("wl-paste missing (sudo dnf install wl-clipboard)", file=sys.stderr)
        return 1
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # pkill → helpers go with us
    me = [sys.executable, "-m", "swayforge", "clip", "store"]
    procs = [subprocess.Popen(["wl-paste", "--type", "text", "--watch", *me, "--mime", "text/plain"]),
             subprocess.Popen(["wl-paste", "--type", "image", "--watch", *me, "--mime", "image"])]
    try:
        while all(p.poll() is None for p in procs):
            try:
                trim()
            except sqlite3.Error:
                pass
            time.sleep(60)
    finally:
        for p in procs:
            p.terminate()
    return 0


def pick() -> int:
    """Rofi: search, Enter = copy · Alt+P = pin/unpin · Alt+D = delete."""
    from .tools import rofi_menu_ex
    trim()
    while True:
        its = items()
        if not its:
            subprocess.run(["notify-send", "Clipboard", "Nothing copied yet"], capture_output=True)
            return 0
        rows = [f"{'📌 ' if i['pinned'] else ''}{i['preview'][:140]}" for i in its]
        idx, code = rofi_menu_ex(rows, "Clipboard", mesg="Enter copy · Alt+P pin · Alt+D delete",
                                 keys=["Alt+p", "Alt+d"])
        if idx is None:
            return 0
        it = its[idx]
        if code == 10:
            pin(it["id"], not it["pinned"])
        elif code == 11:
            delete(it["id"])
        else:
            copy(it["id"])
            return 0


def main(argv: list[str]) -> int:
    act = argv[0] if argv else "pick"
    if act == "store":
        return _store_main()
    if act == "watch":
        return watch()
    if act == "clear":
        clear(keep_pinned="--all" not in argv)
        return 0
    if act == "pause":
        set_paused(True)
        return 0
    if act == "resume":
        set_paused(False)
        return 0
    if act == "list":
        for i in items(" ".join(argv[1:])):
            print(f"{i['id']:>6}  {'📌' if i['pinned'] else '  '} {i['preview'][:100]}")
        return 0
    return pick()
