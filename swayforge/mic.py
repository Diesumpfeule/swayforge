"""Microphone volume that stays where you put it.

PipeWire normally remembers volumes, but apps with "automatic gain control" (Discord/Vesktop,
browsers, Zoom …) turn the microphone down by themselves, and some USB microphones come back at
their default level after a restart. With Settings → Audio → "Keep microphone volume" on:
- the level you set in swayforge (app, terminal settings, scrolling on the bar's microphone) is
  remembered per microphone (~/.local/share/swayforge/mic-volume.json),
- it is set again at every login,
- `swayforge mic keep` (started by Sway) puts it back whenever something else changes it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time

from . import paths


def store() -> dict:
    try:
        return json.loads((paths.STATE_DIR / "mic-volume.json").read_text())
    except (OSError, ValueError):
        return {}


def _pactl(*a: str, timeout: int = 5) -> str:
    try:
        r = subprocess.run(["pactl", *a], capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def default_source() -> str:
    return _pactl("get-default-source").strip()


def current(source: str = "@DEFAULT_SOURCE@") -> int | None:
    m = re.search(r"(\d+)%", _pactl("get-source-volume", source))
    return int(m.group(1)) if m else None


def remember(pct: int, source: str = "") -> None:
    """Called whenever you set the level in swayforge."""
    from .fsutil import atomic_write
    source = source or default_source()
    if not source or source.endswith(".monitor"):
        return
    data = store()
    data[source] = max(0, min(150, int(pct)))
    atomic_write(paths.STATE_DIR / "mic-volume.json", json.dumps(data, indent=1))


def wanted(source: str = "") -> int | None:
    return store().get(source or default_source())


def set_volume(pct: int) -> None:
    pct = max(0, min(150, int(pct)))
    _pactl("set-source-volume", "@DEFAULT_SOURCE@", f"{pct}%")
    remember(pct)


def step(delta: int) -> None:
    cur = current()
    if cur is not None:
        set_volume(cur + delta)


def restore() -> bool:
    """Put the remembered level back (login, or after an app changed it). True = something was set."""
    w = wanted()
    if w is None:
        return False
    if current() != w:
        _pactl("set-source-volume", "@DEFAULT_SOURCE@", f"{w}%")
        return True
    return False


def enabled() -> bool:
    from . import settings
    try:
        return bool(settings.load()["audio"].get("keep_mic", True))
    except Exception:                       # noqa: BLE001
        return True


def keep() -> int:
    """Long-running: watch the sound server and undo foreign changes to the microphone level."""
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    time.sleep(2)                            # let PipeWire settle after login
    restore()
    try:
        p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True)
    except OSError:
        return 1
    last = 0.0
    for line in p.stdout:                    # "Event 'change' on source #57" / "… on server #…"
        if "on source" not in line and "on server" not in line:
            continue
        now = time.monotonic()
        if now - last < 0.3:                 # one fix per burst of events
            continue
        time.sleep(0.25)
        if restore():
            last = time.monotonic()
    return 0


def main(argv: list[str]) -> int:
    act = argv[0] if argv else "status"
    if act == "keep":
        return keep()
    if act == "restore":
        restore()
        return 0
    if act in ("up", "down"):
        step(5 if act == "up" else -5)
        return 0
    if act == "set" and len(argv) > 1 and argv[1].isdigit():
        set_volume(int(argv[1]))
        return 0
    src = default_source()
    print(f"microphone: {src or '?'}\n  now: {current()}%\n  kept at: {wanted(src) if wanted(src) is not None else 'not set yet'}"
          f"\n  keeping: {'on' if enabled() else 'off'}")
    return 0
