"""steamtune – Steam helper: why does Steam download GBs before a game, and keep that out of your way.

Steam's "shader pre-caching" is a separate depot of the game (CS2: one 7 GB file,
steam_pipeline_cache.foz). Valve republishes it often and Steam fetches it again as a whole –
no delta – so a few GB come down every time it changed, right when Steam starts. Your local
cache is fine; it is not lost on reboot.

    steamtune                    what Steam fetched and when, cache size per drive
    steamtune window 03-06       Steam auto-updates only in that time window (or: off)
    steamtune limit N SIZE       cap the shader cache on library N (e.g. 30G, or: off)
    steamtune prune [--dry]      enforce the caps: drop the shader cache of the longest-unplayed games
    steamtune move N DIR         keep library N's shader cache on another drive (symlink; DIR or: back)
Steam must be closed for everything that changes files.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

HOME = Path.home()
ROOTS = (HOME / ".local/share/Steam", HOME / ".steam/steam",
         HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam")
CFG = HOME / ".config/steamtune.json"


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1000
LOG_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] AppID (\d+) (.*)$")
STARTED = re.compile(r"update started : download \d+/(\d+), store \d+/\d+, reuse \d+/(\d+), .*stage \d+/(\d+)")


def root() -> Path | None:
    return next((r.resolve() for r in ROOTS if (r / "config/config.vdf").is_file()), None)


def running() -> bool:
    return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0


def libraries(r: Path) -> list[Path]:
    txt = (r / "steamapps/libraryfolders.vdf").read_text(errors="replace") if (r / "steamapps/libraryfolders.vdf").is_file() else ""
    return [Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', txt)]


def app_name(r: Path, appid: str) -> str:
    for lib in libraries(r) + [r]:
        m = lib / f"steamapps/appmanifest_{appid}.acf"
        if m.is_file():
            n = re.search(r'"name"\s+"([^"]+)"', m.read_text(errors="replace"))
            if n:
                return n.group(1)
    return f"app {appid}"


def shader_downloads(r: Path, limit: int = 8) -> list[dict]:
    """Updates whose "Shader update" phase was downloading, newest last."""
    log = r / "logs/content_log.txt"
    if not log.is_file():
        return []
    started: dict[str, tuple[str, int, int, int]] = {}    # appid -> last "update started"
    out = []
    for line in log.read_text(errors="replace").splitlines():
        m = LOG_LINE.match(line)
        if not m:
            continue
        when, appid, rest = m.groups()
        s = STARTED.search(rest)
        if s:
            started[appid] = (when, *map(int, s.groups()))
        elif rest.startswith("Shader update changed") and "Downloading" in rest and appid in started:
            t, dl, reuse, stage = started.pop(appid)
            out.append({"time": t, "app": appid, "download": dl, "reuse": reuse, "stage": stage})
    return out[-limit:]


def cache_size(r: Path, appid: str) -> int:
    total = 0
    for lib in libraries(r) + [r]:
        d = lib / "steamapps/shadercache" / appid
        if d.is_dir():
            total += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            break
    return total


def _config(r: Path) -> str:
    return (r / "config/config.vdf").read_text(errors="replace")


def window(r: Path) -> str:
    c = _config(r)
    g = lambda k: (re.search(rf'"{k}"\s+"([^"]*)"', c) or [None, ""])[1]
    if g("AutoUpdateWindowEnabled") != "1":
        return "off (Steam updates whenever it likes)"
    return f"{g('AutoUpdateWindowStart') or '?'}:00 – {g('AutoUpdateWindowEnd') or '?'}:00"


def status() -> int:
    r = root()
    if not r:
        print("Steam not found (looked in ~/.local/share/Steam and the Flatpak folder).")
        return 1
    print(f"Steam: {r}   ({'running' if running() else 'closed'})")
    print(f"Auto-update window: {window(r)}\n")
    ups = shader_downloads(r)
    if ups:
        print("Shader pre-cache downloads (from content_log.txt):")
        for u in ups:
            print(f"  {u['time']}  {app_name(r, u['app']):<28} download {human(u['download']):>9}"
                  f"   (file on disk {human(u['stage'])})")
        big = max(ups, key=lambda u: u["download"])
        print(f"\n→ Valve republishes {app_name(r, big['app'])}'s pre-cache as one big file, so Steam fetches"
              "\n  it again whenever it changed. Your local cache is NOT lost on reboot.")
    else:
        print("No shader pre-cache downloads in the log.")
    for lib in libraries(r):
        if not lib.is_dir():
            print(f"\n⚠ Steam library {lib} is not mounted – Steam may re-check games. See `swayforge mount`.")
    print("\nWhat helps:  steamtune window 03-06   (auto-update only at night, Steam closed)"
          "\n             Steam → game → Properties → Shader Pre-Caching off (this one game only)")
    return 0


def set_window(spec: str) -> int:
    r = root()
    if not r:
        print("Steam not found.")
        return 1
    if running():
        print("Close Steam first (it rewrites config.vdf when it quits).")
        return 1
    cfg = r / "config/config.vdf"
    c = cfg.read_text(errors="replace")
    if spec == "off":
        new = re.sub(r'("AutoUpdateWindowEnabled"\s+)"1"', r'\1"0"', c)
    else:
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", spec)
        if not m or not all(0 <= int(x) <= 23 for x in m.groups()):
            print("usage: swayforge steam window HH-HH (e.g. 03-06) | off")
            return 2
        a, b = m.groups()
        anchor = re.search(r'^([ \t]*)"AutoUpdateWindowEnabled"[ \t]+"\d"[^\n]*$', c, re.M)
        if not anchor:
            print("config.vdf has no AutoUpdateWindowEnabled entry – set it once in Steam → Settings → Downloads.")
            return 1
        ind = anchor.group(1)
        c = re.sub(r'^[ \t]*"AutoUpdateWindow(Start|End)"[^\n]*\n', "", c, flags=re.M)
        anchor = re.search(r'^[ \t]*"AutoUpdateWindowEnabled"[ \t]+"\d"[^\n]*$', c, re.M)
        block = f'{ind}"AutoUpdateWindowEnabled"\t\t"1"\n{ind}"AutoUpdateWindowStart"\t\t"{int(a)}"\n{ind}"AutoUpdateWindowEnd"\t\t"{int(b)}"'
        new = c[:anchor.start()] + block + c[anchor.end():]
    bak = cfg.with_name(f"config.vdf.swayforge-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(cfg, bak)
    cfg.write_text(new)
    print(f"Auto-update window: {window(r)}   (backup: {bak.name})")
    return 0


# ── cache size per drive ─────────────────────────────────────────────

def parse_size(txt: str) -> int | None:
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([KMGT]?)B?", txt.strip().upper())
    if not m:
        return None
    return int(float(m.group(1).replace(",", ".")) * 1000 ** ("", "K", "M", "G", "T").index(m.group(2)))


def load_cfg() -> dict:
    try:
        return json.loads(CFG.read_text())
    except (OSError, ValueError):
        return {}


def save_cfg(c: dict) -> None:
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps(c, indent=2) + "\n")


def dir_size(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file() and not f.is_symlink()) if d.is_dir() else 0


def last_played(r: Path) -> dict[str, int]:
    """appid -> LastPlayed (unix) as Steam's ShaderCacheManager recorded it."""
    c = _config(r)
    return {a: int(t) for a, t in re.findall(r'"(\d+)"\s*\{\s*"LastPlayed"\s+"(\d+)"', c)}


def lib_cache(lib: Path) -> Path:
    return lib / "steamapps/shadercache"


def pick_library(r: Path, key: str) -> Path | None:
    libs = libraries(r)
    if key.isdigit() and int(key) < len(libs):
        return libs[int(key)]
    return next((l for l in libs if str(l).rstrip("/") == key.rstrip("/")), None)


def apps_in(lib: Path, r: Path) -> list[tuple[str, int, int]]:
    """(appid, bytes, last played or dir mtime), oldest first."""
    lp = last_played(r)
    out = []
    for d in lib_cache(lib).glob("*"):
        if d.is_dir() and d.name.isdigit():
            out.append((d.name, dir_size(d), lp.get(d.name) or int(d.stat().st_mtime)))
    return sorted(out, key=lambda x: x[2])


def cache_report(r: Path) -> None:
    lims = load_cfg().get("limits", {})
    print("Shader cache per Steam library:")
    for i, lib in enumerate(libraries(r)):
        c = lib_cache(lib)
        if not lib.is_dir():
            print(f"  [{i}] {lib}   (not mounted)")
            continue
        total = sum(b for _, b, _ in apps_in(lib, r))
        free = shutil.disk_usage(lib).free
        lim = lims.get(str(lib))
        where = f" → {c.resolve()}" if c.is_symlink() else ""
        print(f"  [{i}] {lib}   cache {human(total)}"
              f"   limit {human(lim) if lim else 'none'}   drive free {human(free)}{where}")


def set_limit(r: Path, key: str, size: str) -> int:
    lib = pick_library(r, key)
    if not lib:
        print("No such library – see the numbers in `steamtune`.")
        return 2
    cfg = load_cfg()
    lims = cfg.setdefault("limits", {})
    if size == "off":
        lims.pop(str(lib), None)
    else:
        n = parse_size(size)
        if not n:
            print("size like 30G, 500M, 1.5T – or off")
            return 2
        lims[str(lib)] = n
    save_cfg(cfg)
    print(f"Limit for {lib}: {human(lims[str(lib)]) if str(lib) in lims else 'none'}   (apply it: steamtune prune)")
    return 0


def prune(r: Path, dry: bool, quiet: bool = False) -> int:
    lims = load_cfg().get("limits", {})
    if not lims:
        if not quiet:
            print("No limits set – `steamtune limit N 30G`.")
        return 0
    if running() and not dry:
        if not quiet:
            print("Close Steam first (it would rebuild what is deleted).")
        return 1
    for lib in libraries(r):
        lim = lims.get(str(lib))
        if not lim or not lib.is_dir():
            continue
        apps = apps_in(lib, r)
        total = sum(b for _, b, _ in apps)
        keep_newest = apps[-1][0] if apps else ""          # the game you played last is never touched
        freed = 0
        for appid, size, _ in apps:
            if total - freed <= lim or appid == keep_newest:
                continue
            print(f"  {'would drop' if dry else 'dropping'}  {app_name(r, appid):<28} {human(size)}   ({lib})")
            if not dry:
                shutil.rmtree(lib_cache(lib) / appid, ignore_errors=True)
            freed += size
        if freed:
            print(f"  {lib}: {human(total)} → {human(total - freed)} (limit {human(lim)})")
        elif not quiet:
            print(f"  {lib}: {human(total)} – within the limit of {human(lim)}")
    return 0


def move(r: Path, key: str, dest: str) -> int:
    lib = pick_library(r, key)
    if not lib or not lib.is_dir():
        print("No such (mounted) library – see the numbers in `steamtune`.")
        return 2
    if running():
        print("Close Steam first.")
        return 1
    src = lib_cache(lib)
    if dest == "back":
        if not src.is_symlink():
            print("Already in place.")
            return 0
        real = src.resolve()
        src.unlink()
        shutil.move(str(real), str(src))
        print(f"Shader cache is back in {src}")
        return 0
    target = Path(dest).expanduser().resolve()
    if src.is_symlink():
        print(f"Already moved to {src.resolve()} – `steamtune move {key} back` first.")
        return 1
    if not target.parent.is_dir():
        print(f"{target.parent} does not exist (is the drive mounted?).")
        return 1
    size = dir_size(src)
    if shutil.disk_usage(target.parent).free < size * 1.1:
        print(f"Not enough free space on {target.parent} for {human(size)}.")
        return 1
    print(f"Moving {human(size)} to {target} …")
    shutil.move(str(src), str(target))
    src.symlink_to(target)
    print(f"Done: {src} → {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="steamtune", description=__doc__.split("\n")[0])
    ap.add_argument("action", nargs="?", default="status",
                    choices=["status", "window", "limit", "prune", "move"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--dry", action="store_true", help="prune: only show what would be dropped")
    ap.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.action == "window":
        return set_window(a.args[0] if a.args else "off")
    r = root()
    if not r:
        print("Steam not found.")
        return 1
    if a.action == "limit" and len(a.args) == 2:
        return set_limit(r, *a.args)
    if a.action == "prune":
        return prune(r, a.dry, a.quiet)
    if a.action == "move" and len(a.args) == 2:
        return move(r, *a.args)
    if a.action in ("limit", "move"):
        print(f"usage: steamtune {a.action} LIBRARY-NUMBER {'SIZE|off' if a.action == 'limit' else 'DIR|back'}")
        return 2
    rc = status()
    print()
    cache_report(r)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
