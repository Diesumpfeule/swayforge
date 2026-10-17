"""Steam helper: why does Steam download GBs before a game, and keep that out of your way.

Steam's "shader pre-caching" is a separate depot of the game (CS2: one 7 GB file,
steam_pipeline_cache.foz). Valve republishes it often and Steam fetches it again as a whole –
no delta – so a few GB come down every time it changed, right when Steam starts. Your local
cache is fine; it is not lost on reboot.

`swayforge steam` shows what Steam fetched and when. `swayforge steam window 03-06` lets Steam
auto-update only in that time window (Steam must be closed, config.vdf is backed up first).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from . import paths
from .apps import human

ROOTS = (paths.HOME / ".local/share/Steam", paths.HOME / ".steam/steam",
         paths.HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam")
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
    print("\nWhat helps:  swayforge steam window 03-06   (auto-update only at night, Steam closed)"
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


def main(action: str, arg: str = "") -> int:
    if action == "window":
        return set_window(arg or "off")
    return status()
