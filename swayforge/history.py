"""Undo for Apply: every successful apply keeps a copy of what it applied.

~/.local/share/swayforge/history/<time>/ holds settings.toml plus your own theme and layout files
that were in use – everything the generated configs are made from. Going back restores those
and applies again, so every generated file (Sway, bar, launcher, GTK …) is exactly as it was.
Files that belong to you (custom.conf, style.css …) are never touched by apply, so there is
nothing to roll back there. The last KEEP versions are kept.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import paths, settings, tomlw
from .fsutil import atomic_write

KEEP = 15


def root() -> Path:
    return paths.STATE_DIR / "history"


def _flat(d: dict, pre: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if k in ("style_backup",):
            continue
        if isinstance(v, dict) and k not in ("outputs", "keys"):
            out.update(_flat(v, f"{pre}{k}."))
        else:
            out[f"{pre}{k}"] = v
    return out


def describe(old: dict | None, new: dict) -> str:
    """What changed, in a few words: 'theme.name: nord → rust, bar.layout …'."""
    if old is None:
        return "first saved version"
    a, b = _flat(old), _flat(new)
    diffs = [k for k in b if a.get(k) != b[k]] + [k for k in a if k not in b]
    if not diffs:
        return "nothing changed (applied again)"
    parts = []
    for k in diffs[:3]:
        o, n = a.get(k), b.get(k)
        short = lambda v: (json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)[:24]  # noqa: E731
        parts.append(f"{k}: {short(o)} → {short(n)}")
    return ", ".join(parts) + (f" (+{len(diffs) - 3} more)" if len(diffs) > 3 else "")


def entries() -> list[dict]:
    """Newest first: [{id, when, summary, path}]."""
    out = []
    for d in sorted(root().glob("*"), reverse=True) if root().is_dir() else []:
        try:
            meta = json.loads((d / "meta.json").read_text())
        except (OSError, ValueError):
            continue
        out.append({"id": d.name, "when": meta.get("when", d.name), "summary": meta.get("summary", ""),
                    "theme": meta.get("theme", ""), "layout": meta.get("layout", ""), "path": str(d)})
    return out


def _load(entry_id: str) -> dict | None:
    import tomllib
    try:
        return tomllib.loads((root() / entry_id / "settings.toml").read_text())
    except (OSError, ValueError):
        return None


def record(s: dict, note: str = "") -> str | None:
    """Keep a copy of the settings that were just applied. Returns the new entry id (None = identical)."""
    from . import layouts, themes
    prev = entries()
    old = _load(prev[0]["id"]) if prev else None
    clean = {k: v for k, v in s.items()}
    if old is not None and _flat(old) == _flat(clean) and not note:
        return None                                   # applied again without changes – no new entry
    eid = time.strftime("%Y%m%d-%H%M%S")
    n = 1
    while (root() / eid).exists():
        eid = f"{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    d = root() / eid
    d.mkdir(parents=True)
    atomic_write(d / "settings.toml", tomlw.dumps(clean))
    t = themes.get(s["theme"]["name"])
    if t.custom and t.path and Path(t.path).exists():
        shutil.copy2(t.path, d / "theme.toml")
    lay = s["bar"]["layout"]
    if layouts.custom(lay):
        shutil.copy2(layouts.user_dir() / f"{lay}.toml", d / "layout.toml")
    summary = (note + " · " if note else "") + describe(old, clean)
    atomic_write(d / "meta.json", json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "summary": summary,
                                              "theme": t.label, "layout": layouts.get(lay).label}))
    for extra in entries()[KEEP:]:
        shutil.rmtree(extra["path"], ignore_errors=True)
    return eid


def restore(entry_id: str, live: bool = True):
    """Go back to one version: settings + your theme/layout file, then apply. Returns render.Result."""
    from . import layouts, render
    import re
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}(-[0-9]+)?", entry_id) or not (root() / entry_id).is_dir():
        raise ValueError("unknown version")
    old = _load(entry_id)
    if old is None:
        raise ValueError("that version can't be read")
    d = root() / entry_id
    s = settings._merge(settings.DEFAULTS, settings._migrate(old))
    if (d / "theme.toml").exists():
        paths.USER_THEMES.mkdir(parents=True, exist_ok=True)       # your theme as it was then
        shutil.copy2(d / "theme.toml", paths.USER_THEMES / f"{s['theme']['name']}.toml")
    if (d / "layout.toml").exists():
        layouts.user_dir().mkdir(parents=True, exist_ok=True)
        shutil.copy2(d / "layout.toml", layouts.user_dir() / f"{s['bar']['layout']}.toml")
    settings.save(s)
    res = render.apply(s, live=live, note=f"back to {entries_when(entry_id)}")
    return res


def entries_when(entry_id: str) -> str:
    return next((e["when"] for e in entries() if e["id"] == entry_id), entry_id)


def undo(live: bool = True):
    """Back to the version before the last apply."""
    es = entries()
    if len(es) < 2:
        raise ValueError("nothing to undo yet – there is only one saved version")
    return restore(es[1]["id"], live)


def main(argv: list[str]) -> int:
    act = argv[0] if argv else "list"
    try:
        if act == "undo":
            res = undo()
        elif act == "restore" and len(argv) > 1:
            es = entries()
            ref = argv[1]
            eid = es[int(ref) - 1]["id"] if ref.isdigit() and 0 < int(ref) <= len(es) else ref
            res = restore(eid)
        else:
            es = entries()
            if not es:
                print("No saved versions yet – every Apply keeps one.")
            for i, e in enumerate(es, 1):
                print(f"{i:>3}  {e['when']}  {e['theme']} / {e['layout']}\n     {e['summary']}")
            print("\nGo back:  swayforge undo   ·   swayforge history restore NUMBER")
            return 0
    except (ValueError, IndexError) as e:
        print(f"✗ {e}")
        return 1
    print("✓ restored and applied" if not res.errors else "✗ " + "; ".join(res.errors))
    return 1 if res.errors else 0
