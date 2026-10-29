"""Desktop widgets – clocks (dot matrix, digital, analog), music player, system monitor, workspace
preview, calendar, weather, network speed, free space, battery, sticky note, focus timer and
Clippy – drawn on the desktop (below your windows) in the colours of your theme.
`swayforge widgets overview` (Super+O) shows every workspace big, like an exposé.

`swayforge widgets run` shows the widgets switched on in Settings → Desktop widgets. One small
GTK process (gtk-layer-shell + cairo, the same pieces the CS2 overlay uses); the clocks redraw once a
second, the player and monitor every two. They sit on the "bottom" layer: above the wallpaper,
below every window, never in front of a game.
"""
from __future__ import annotations

import math
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from . import paths, settings

KINDS = {
    "clock": "Clock",
    "player": "Music player",
    "sysmon": "System monitor",
    "workspaces": "Workspace preview",
    "calendar": "Calendar",
    "weather": "Weather",
    "network": "Network speed",
    "disks": "Free space",
    "battery": "Battery",
    "notes": "Sticky note",
    "timer": "Focus timer",
    "clippy": "Clippy",
}
TOGGLES = [k for k in KINDS if k != "clock"]          # on/off switches in Settings (clock has a style)
CLOCKS = {"dots": "Dot matrix", "digital": "Digital", "analog": "Analog", "off": "Off"}
CORNERS = {"top-left": "Top left", "top-center": "Top centre", "top-right": "Top right", "bottom-left": "Bottom left",
           "bottom-center": "Bottom centre", "bottom-right": "Bottom right", "center": "Centre"}
NOTES = paths.CONFIG_DIR / "notes.md"
THUMBS = paths.HOME / ".cache/swayforge/workspaces"
WEATHER_CACHE = paths.HOME / ".cache/swayforge/weather.json"
LOG = paths.STATE_DIR / "widgets.log"

# 5×7 dot-matrix digits (and the colon) – "#" = lit
DIGITS = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    ":": [".", ".", "#", ".", "#", ".", "."],
}

TIPS = [
    "Super+Enter opens a terminal. Super+R finds any app.",
    "Super+Shift+T cycles through the colour themes.",
    "Super+Shift+B tries the next bar layout.",
    "Super+F1 shows every shortcut you have.",
    "Super+V brings back anything you copied earlier.",
    "Super+Shift+S grabs part of the screen and lets you draw on it.",
    "Super+Shift+G is gaming mode: no gaps, no notifications, full power.",
    "Ctrl+Shift+Esc opens the task manager.",
    "Super+Ctrl+I opens the swayforge app with live previews.",
    "Your own Sway lines go into ~/.config/sway/custom.conf – swayforge never touches it.",
    "Lost a setting? Settings → System & files keeps backups of every replaced file.",
    "Before a reset: Settings → System & files → Export. After it: ./install.sh --restore FILE",
    "Wallpapers folder: drop pictures or videos into Pictures/Wallpapers.",
    "Make a theme from your wallpaper: swayforge app → Themes → Theme from wallpaper.",
    "swayforge screenshare checks why Discord can't share your screen.",
    "Mount a second drive for good: Settings → Mount drives.",
    "The screensaver can be the Matrix. Settings → Power & lock.",
    "Super+Escape opens the power menu.",
    "It looks like you're writing a config. Would you like a backup first?",
    "Every generated file has a twin that belongs to you. Yours always wins.",
    "LibreWolf follows your theme too, if wolfforge is installed.",
    "Right-click the speaker in the bar to mute, scroll to change the volume.",
    "Settings → Security scans downloads and USB sticks for Windows malware.",
    "Shift+F12 in a game shows or hides the MangoHud overlay.",
]


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


# ── data sources (no GTK) ────────────────────────────────────────────
def player_state() -> dict | None:
    """What plays right now (any MPRIS player: Spotify, browsers, mpv …) via playerctl."""
    fmt = "{{status}}\t{{artist}}\t{{title}}\t{{position}}\t{{mpris:length}}\t{{playerName}}"
    try:
        r = subprocess.run(["playerctl", "metadata", "--format", fmt], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return parse_player(r.stdout)


def parse_player(out: str) -> dict | None:
    parts = out.rstrip("\n").split("\t")
    if len(parts) < 6:
        return None
    status, artist, title, pos, length, name = parts[:6]

    def num(x: str) -> float:
        try:
            return float(x) / 1_000_000
        except ValueError:
            return 0.0
    return {"status": status, "artist": artist, "title": title or "(no title)", "pos": num(pos),
            "length": num(length), "player": name}


class CpuMeter:
    """CPU load from /proc/stat (difference between two reads)."""

    def __init__(self) -> None:
        self.prev = self._read()

    @staticmethod
    def _read() -> tuple[int, int]:
        try:
            f = Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]
            v = [int(x) for x in f]
            return sum(v), v[3] + (v[4] if len(v) > 4 else 0)
        except (OSError, ValueError, IndexError):
            return 0, 0

    def load(self) -> float:
        cur = self._read()
        dt, di = cur[0] - self.prev[0], cur[1] - self.prev[1]
        self.prev = cur
        return max(0.0, min(1.0, 1 - di / dt)) if dt > 0 else 0.0


def memory() -> float:
    try:
        m = dict(re.findall(r"^(\w+):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M))
        total, avail = int(m["MemTotal"]), int(m.get("MemAvailable", m.get("MemFree", 0)))
        return 1 - avail / total if total else 0.0
    except (OSError, KeyError, ValueError):
        return 0.0


def temperature() -> float | None:
    """CPU temperature in °C (k10temp / coretemp / first thermal zone)."""
    for d in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        try:
            if (d / "name").read_text().strip() in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
                return int((d / "temp1_input").read_text()) / 1000
        except (OSError, ValueError):
            continue
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except (OSError, ValueError):
        return None


class NetMeter:
    """Download/upload in bytes per second from /proc/net/dev, plus the last 60 samples."""

    def __init__(self, path: str = "/proc/net/dev") -> None:
        self.path = path
        self.prev = self._read()
        self.t = time.monotonic()
        self.hist: list[tuple[float, float]] = []

    def _read(self) -> tuple[int, int]:
        rx = tx = 0
        try:
            for line in Path(self.path).read_text().splitlines()[2:]:
                name, _, rest = line.partition(":")
                name = name.strip()
                if name == "lo" or name.startswith(("veth", "docker", "virbr", "br-")):
                    continue
                f = rest.split()
                rx, tx = rx + int(f[0]), tx + int(f[8])
        except (OSError, ValueError, IndexError):
            pass
        return rx, tx

    def sample(self) -> tuple[float, float]:
        cur, now = self._read(), time.monotonic()
        dt = max(0.001, now - self.t)
        down, up = max(0, cur[0] - self.prev[0]) / dt, max(0, cur[1] - self.prev[1]) / dt
        self.prev, self.t = cur, now
        self.hist = (self.hist + [(down, up)])[-60:]
        return down, up


def rate(bps: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1000 or unit == "GB/s":
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1000
    return ""


def disks() -> list[tuple[str, float, int]]:
    """[(label, used fraction, free bytes)] for /, /home (if separate) and /mnt/* drives."""
    out, seen = [], set()
    cands = [("System", "/"), ("Home", str(paths.HOME))]
    try:
        cands += [(d.name, str(d)) for d in sorted(Path("/mnt").iterdir()) if os.path.ismount(d)]
    except OSError:
        pass
    for label, mp in cands:
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        if st.f_fsid in seen or not st.f_blocks:
            continue
        seen.add(st.f_fsid)
        free = st.f_bavail * st.f_frsize
        out.append((label, 1 - st.f_bavail / st.f_blocks, free))
    return out[:4]


def battery(root: str = "/sys/class/power_supply") -> dict | None:
    for d in sorted(Path(root).glob("BAT*")):
        try:
            return {"percent": int((d / "capacity").read_text()), "status": (d / "status").read_text().strip()}
        except (OSError, ValueError):
            continue
    return None


def weather_url(city: str) -> str:
    from urllib.parse import quote
    return f"https://wttr.in/{quote(city.strip())}?format=j1" if city.strip() else "https://wttr.in/?format=j1"


def parse_weather(data: dict) -> dict | None:
    """wttr.in JSON → {place, temp, feels, desc, code, days: [(weekday, min, max, code)]}."""
    try:
        cur = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        place = (area.get("areaName") or [{}])[0].get("value", "")
        days = []
        for d in data.get("weather", [])[:3]:
            wd = time.strftime("%a", time.strptime(d["date"], "%Y-%m-%d"))
            hourly = d.get("hourly") or []
            code = (hourly[4] if len(hourly) > 4 else hourly[0] if hourly else {}).get("weatherCode", "113")
            days.append((wd, int(d["mintempC"]), int(d["maxtempC"]), str(code)))
        return {"place": place, "temp": int(cur["temp_C"]), "feels": int(cur["FeelsLikeC"]),
                "desc": cur["weatherDesc"][0]["value"], "code": str(cur.get("weatherCode", "113")), "days": days}
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def weather_kind(code: str) -> str:
    """wttr/WWO weather code → sun | partly | cloud | rain | snow | storm | fog."""
    c = int(code) if str(code).isdigit() else 113
    if c == 113:
        return "sun"
    if c == 116:
        return "partly"
    if c in (119, 122):
        return "cloud"
    if c in (143, 248, 260):
        return "fog"
    if c in (200, 386, 389, 392, 395):
        return "storm"
    if c in (179, 227, 230, 323, 326, 329, 332, 335, 338, 368, 371, 374, 377, 182, 185, 317, 320, 350, 362, 365):
        return "snow"
    return "rain"


def fetch_weather(city: str) -> dict | None:
    """Weather for city (cached 30 min). Runs in a thread – never blocks drawing."""
    import json
    import urllib.request
    try:
        cache = json.loads(WEATHER_CACHE.read_text())
        if cache.get("city") == city and time.time() - cache.get("at", 0) < 1800:
            return parse_weather(cache["data"])
    except (OSError, ValueError, KeyError):
        pass
    try:
        req = urllib.request.Request(weather_url(city), headers={"User-Agent": "curl/8 swayforge"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
    except Exception as e:                         # noqa: BLE001 – offline is normal
        log(f"weather: {e}")
        return None
    try:
        WEATHER_CACHE.parent.mkdir(parents=True, exist_ok=True)
        WEATHER_CACHE.write_text(json.dumps({"city": city, "at": time.time(), "data": data}))
    except OSError:
        pass
    return parse_weather(data)


def notes_text() -> str:
    try:
        return NOTES.read_text()[:2000]
    except OSError:
        return "Click to write a note."


class Timer:
    """Focus timer: 25 min work, 5 min break, again."""
    WORK, BREAK = 25 * 60, 5 * 60

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.phase, self.left, self.running, self.last = "work", float(self.WORK), False, time.monotonic()

    def toggle(self) -> None:
        self.tick()
        self.running = not self.running
        self.last = time.monotonic()

    def tick(self) -> str | None:
        """Advance; returns 'work'/'break' when a phase just ended."""
        now = time.monotonic()
        if self.running:
            self.left -= now - self.last
        self.last = now
        if self.left <= 0:
            ended = self.phase
            self.phase = "break" if self.phase == "work" else "work"
            self.left = float(self.BREAK if self.phase == "break" else self.WORK)
            return ended
        return None


def parse_tree(tree: dict, focused_ws: str = "") -> list[dict]:
    """swaymsg -t get_tree → [{name, output, rect, focused, windows: [{app, rect, focused, floating}]}]."""
    out = []

    def leaves(node: dict, floating: bool = False):
        kids = node.get("nodes", []) + node.get("floating_nodes", [])
        if not kids and node.get("type") in ("con", "floating_con") and (node.get("pid") or node.get("app_id") or node.get("window")):
            props = node.get("window_properties") or {}
            yield {"app": node.get("app_id") or props.get("class") or node.get("name") or "?",
                   "rect": node.get("rect", {}), "focused": bool(node.get("focused")), "floating": floating}
        for k in node.get("nodes", []):
            yield from leaves(k, floating)
        for k in node.get("floating_nodes", []):
            yield from leaves(k, True)

    for o in tree.get("nodes", []):
        if o.get("name") == "__i3":
            continue
        for ws in o.get("nodes", []):
            if ws.get("type") != "workspace":
                continue
            wins = list(leaves(ws))
            out.append({"name": ws.get("name", "?"), "num": ws.get("num", -1), "output": o.get("name", ""),
                        "rect": ws.get("rect", {}), "windows": wins,
                        "focused": ws.get("name") == focused_ws or ws.get("focused", False) or any(w["focused"] for w in wins)})
    return sorted(out, key=lambda w: (w["num"] if w["num"] >= 0 else 99, w["name"]))


def sway_workspaces() -> list[dict]:
    import json
    try:
        tree = json.loads(subprocess.run(["swaymsg", "-t", "get_tree", "-r"], capture_output=True, text=True,
                                         timeout=2).stdout or "{}")
        wss = json.loads(subprocess.run(["swaymsg", "-t", "get_workspaces", "-r"], capture_output=True, text=True,
                                        timeout=2).stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    foc = next((w["name"] for w in wss if w.get("focused")), "")
    return parse_tree(tree, foc)


def thumb_path(ws_name: str) -> Path:
    return THUMBS / (re.sub(r"[^A-Za-z0-9_-]", "_", ws_name) + ".png")


def capture_visible() -> None:
    """Small picture of every workspace that is visible right now (one per monitor)."""
    import json
    try:
        outs = json.loads(subprocess.run(["swaymsg", "-t", "get_outputs", "-r"], capture_output=True, text=True,
                                         timeout=2).stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return
    THUMBS.mkdir(parents=True, exist_ok=True)
    os.chmod(THUMBS, 0o700)
    for o in outs:
        ws = o.get("current_workspace")
        if o.get("active") and ws:
            subprocess.run(["grim", "-o", o["name"], "-s", "0.3", "-l", "1", str(thumb_path(ws))],
                           capture_output=True, timeout=5)


def thumb_watcher(stop, after=None) -> None:
    """Thread: picture on every workspace switch (after it settled) and every 20 s."""
    from shutil import which
    if not which("grim"):
        return
    last = 0.0
    try:
        p = subprocess.Popen(["swaymsg", "-m", "-t", "subscribe", '["workspace"]'], stdout=subprocess.PIPE, text=True)
    except OSError:
        return
    import select
    while not stop.is_set():
        r, _, _ = select.select([p.stdout], [], [], 20)
        if r:
            line = p.stdout.readline()
            if not line:
                break
            time.sleep(0.45)                     # let the new workspace draw
        if time.monotonic() - last > 0.4:
            capture_visible()
            last = time.monotonic()
            if after:
                after()
    p.terminate()


def layout_widgets(cfg: dict) -> list[tuple[str, str]]:
    """[(kind, corner)] in drawing order – what Settings switched on."""
    out = []
    if cfg.get("clock", "dots") != "off":
        out.append(("clock", cfg.get("clock_pos", "top-right")))
    for k in TOGGLES:
        if cfg.get(k):
            out.append((k, cfg.get(f"{k}_pos", "top-right")))
    return out


SIZES = {"player": (340, 118), "sysmon": (280, 120), "clippy": (330, 190), "workspaces": (560, 128),
         "calendar": (260, 236), "weather": (300, 150), "network": (300, 120), "disks": (300, 132),
         "battery": (220, 84), "notes": (260, 190), "timer": (220, 120)}


def size_of(kind: str, cfg: dict) -> tuple[int, int]:
    k = float(cfg.get("scale", 1.0) or 1.0)
    base = {"dots": (372, 150), "digital": (330, 140), "analog": (210, 230)}.get(cfg.get("clock", "dots"), (330, 140)) \
        if kind == "clock" else SIZES[kind]
    return int(base[0] * k), int(base[1] * k)


# ── drawing (cairo) ──────────────────────────────────────────────────
def rounded(cr, x: float, y: float, w: float, h: float, r: float) -> None:
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Painter:
    """Draws one widget into a cairo context of size w×h."""

    def __init__(self, theme: dict, cfg: dict) -> None:
        self.c = {k: rgb(v) for k, v in theme["colors"].items()}
        self.font = theme.get("font", "monospace")
        self.radius = theme.get("radius", 8)
        self.alpha = float(cfg.get("opacity", 0.85))
        self.cfg = cfg

    def col(self, cr, key: str, a: float = 1.0) -> None:
        r, g, b = self.c.get(key, (1, 1, 1))
        cr.set_source_rgba(r, g, b, a)

    def card(self, cr, w: float, h: float) -> None:
        rounded(cr, 0.5, 0.5, w - 1, h - 1, self.radius + 4)
        self.col(cr, "base", self.alpha)
        cr.fill_preserve()
        self.col(cr, "surface2", 0.9)
        cr.set_line_width(1)
        cr.stroke()

    def text(self, cr, x: float, y: float, s: str, size: float, key: str = "text", bold: bool = False,
             a: float = 1.0, maxw: float | None = None) -> float:
        import cairo
        cr.select_font_face(self.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size)
        if maxw is not None:
            while s and cr.text_extents(s).x_advance > maxw:
                s = s[:-2] + "…" if len(s) > 2 else ""
        self.col(cr, key, a)
        cr.move_to(x, y)
        cr.show_text(s)
        return cr.text_extents(s).x_advance

    # — clocks —
    def clock(self, cr, w: float, h: float, now: time.struct_time, frac: float) -> None:
        style = self.cfg.get("clock", "dots")
        if style == "analog":
            return self.analog(cr, w, h, now, frac)
        self.card(cr, w, h)
        hhmm = time.strftime("%H:%M", now)
        date = time.strftime("%A, %d %B", now)
        if style == "digital":
            self.text(cr, 22, h * 0.58, hhmm, h * 0.46, "text", bold=True)
            self.text(cr, w - 62, h * 0.58, time.strftime(":%S", now), h * 0.2, "accent", bold=True)
            self.col(cr, "accent", 0.9)
            cr.rectangle(22, h * 0.67, (w - 44) * (now.tm_sec + frac) / 60, 3)
            cr.fill()
            self.text(cr, 22, h * 0.87, date, h * 0.12, "subtext")
            return
        # dot matrix
        cell = (w - 40) / (5 * 4 + 1 + 4 + 2)     # four digits, a colon, gaps
        r = cell * 0.36
        x0, y0 = 20 + cell / 2, 18 + cell / 2
        x = x0
        for ch in hhmm:
            g = DIGITS[ch]
            blink = ch == ":" and now.tm_sec % 2
            for yy, row in enumerate(g):
                for xx, v in enumerate(row):
                    cx, cy = x + xx * cell, y0 + yy * cell
                    cr.arc(cx, cy, r, 0, 2 * math.pi)
                    if v == "#" and not blink:
                        self.col(cr, "accent", 1.0)
                    else:
                        self.col(cr, "surface2", 0.35)
                    cr.fill()
            x += (len(g[0]) + 1) * cell
        # seconds: a row of 60 tiny dots, the passed ones lit
        sy = y0 + 7 * cell + cell * 0.3
        step = (w - 40) / 60
        for s in range(60):
            cr.arc(20 + step * (s + 0.5), sy, max(1.2, r * 0.32), 0, 2 * math.pi)
            self.col(cr, "accent" if s <= now.tm_sec else "surface2", 0.95 if s <= now.tm_sec else 0.4)
            cr.fill()
        self.text(cr, 20, h - 12, date, max(10, h * 0.09), "subtext")

    def analog(self, cr, w: float, h: float, now: time.struct_time, frac: float) -> None:
        cx, cy, R = w / 2, w / 2, w / 2 - 8
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        self.col(cr, "base", self.alpha)
        cr.fill_preserve()
        self.col(cr, "surface2", 0.9)
        cr.set_line_width(1.5)
        cr.stroke()
        for i in range(60):
            a = i / 60 * 2 * math.pi
            inner = R - (12 if i % 5 == 0 else 5)
            cr.move_to(cx + math.sin(a) * inner, cy - math.cos(a) * inner)
            cr.line_to(cx + math.sin(a) * (R - 3), cy - math.cos(a) * (R - 3))
            self.col(cr, "text" if i % 5 == 0 else "overlay", 0.9)
            cr.set_line_width(2.4 if i % 5 == 0 else 1)
            cr.stroke()
        sec = now.tm_sec + frac
        mins = now.tm_min + sec / 60
        hrs = now.tm_hour % 12 + mins / 60
        for val, length, width, key in ((hrs / 12, 0.5, 5, "text"), (mins / 60, 0.75, 3.2, "text"), (sec / 60, 0.85, 1.4, "accent")):
            a = val * 2 * math.pi
            cr.move_to(cx - math.sin(a) * R * 0.12, cy + math.cos(a) * R * 0.12)
            cr.line_to(cx + math.sin(a) * R * length, cy - math.cos(a) * R * length)
            self.col(cr, key)
            cr.set_line_width(width)
            cr.set_line_cap(1)
            cr.stroke()
        cr.arc(cx, cy, 4, 0, 2 * math.pi)
        self.col(cr, "accent")
        cr.fill()
        self.text(cr, cx - 34, h - 4, time.strftime("%a %d.%m.", now), 13, "subtext")

    # — player —
    def player(self, cr, w: float, h: float, p: dict | None) -> dict:
        """Returns the button areas {name: (x, y, w, h)} for clicks."""
        self.card(cr, w, h)
        if not p:
            self.text(cr, 20, h / 2 + 5, "Nothing is playing", 14, "subtext")
            return {}
        self.text(cr, 20, 32, p["title"], 16, "text", bold=True, maxw=w - 40)
        self.text(cr, 20, 54, p["artist"] or p["player"], 13, "subtext", maxw=w - 40)
        # progress
        frac = p["pos"] / p["length"] if p["length"] else 0
        rounded(cr, 20, 66, w - 40, 4, 2)
        self.col(cr, "surface2", 0.8)
        cr.fill()
        rounded(cr, 20, 66, (w - 40) * max(0.0, min(1.0, frac)), 4, 2)
        self.col(cr, "accent")
        cr.fill()
        # buttons
        areas = {}
        mid = w / 2
        for name, x, glyph in (("previous", mid - 70, "⏮"), ("play-pause", mid - 16, "⏸" if p["status"] == "Playing" else "▶"),
                               ("next", mid + 38, "⏭")):
            self.text(cr, x, h - 16, glyph, 22, "accent" if name == "play-pause" else "text", bold=True)
            areas[name] = (x - 8, h - 42, 40, 36)
        return areas

    # — system monitor —
    def sysmon(self, cr, w: float, h: float, cpu: float, mem: float, temp: float | None) -> None:
        self.card(cr, w, h)
        rows = [("CPU", cpu, f"{cpu * 100:.0f}%"), ("RAM", mem, f"{mem * 100:.0f}%")]
        if temp is not None:
            rows.append(("TEMP", min(1.0, temp / 100), f"{temp:.0f}°"))
        for i, (lab, v, txt) in enumerate(rows):
            y = 30 + i * 30
            self.text(cr, 18, y, lab, 12, "subtext", bold=True)
            rounded(cr, 70, y - 9, w - 140, 8, 4)
            self.col(cr, "surface2", 0.7)
            cr.fill()
            rounded(cr, 70, y - 9, (w - 140) * v, 8, 4)
            self.col(cr, "red" if v > 0.85 else "yellow" if v > 0.65 else "accent")
            cr.fill()
            self.text(cr, w - 60, y, txt, 12, "text", bold=True)

    # — Clippy —
    def clippy(self, cr, w: float, h: float, tip: str, t: float) -> None:
        # speech bubble
        bw, bh = w - 84, h - 30
        rounded(cr, 4, 4, bw, bh, 10)
        self.col(cr, "base", max(self.alpha, 0.92))
        cr.fill_preserve()
        self.col(cr, "accent", 0.9)
        cr.set_line_width(1.5)
        cr.stroke()
        cr.move_to(bw - 18, bh + 4)                 # bubble tail towards the clip
        cr.line_to(bw + 10, bh + 18)
        cr.line_to(bw - 34, bh + 4)
        cr.close_path()
        self.col(cr, "base", max(self.alpha, 0.92))
        cr.fill()
        self.wrap(cr, 16, 30, bw - 26, tip, 13.5)
        self.text(cr, 16, bh - 6, "click for another tip", 10.5, "overlay")
        # the paper clip, bobbing a little
        bob = math.sin(t * 1.5) * 3
        x0, y0 = w - 62, h - 150 + bob
        self.col(cr, "subtext")
        cr.set_line_width(5)
        cr.set_line_cap(1)
        cr.move_to(x0 + 14, y0 + 120)
        cr.line_to(x0 + 14, y0 + 30)
        cr.curve_to(x0 + 14, y0 + 6, x0 + 46, y0 + 6, x0 + 46, y0 + 30)
        cr.line_to(x0 + 46, y0 + 128)
        cr.curve_to(x0 + 46, y0 + 150, x0 + 4, y0 + 150, x0 + 4, y0 + 128)
        cr.line_to(x0 + 4, y0 + 46)
        cr.curve_to(x0 + 4, y0 + 34, x0 + 30, y0 + 34, x0 + 30, y0 + 46)
        cr.line_to(x0 + 30, y0 + 110)
        cr.stroke()
        # eyes (they blink now and then)
        blink = (t % 5) < 0.15
        for ex in (x0 + 10, x0 + 40):
            cr.arc(ex, y0 + 62, 9, 0, 2 * math.pi)
            self.col(cr, "text")
            cr.fill()
            if not blink:
                cr.arc(ex + 2, y0 + 63, 4, 0, 2 * math.pi)
                self.col(cr, "crust")
                cr.fill()
        for ex in (x0 + 10, x0 + 40):           # eyebrows
            cr.move_to(ex - 8, y0 + 48)
            cr.line_to(ex + 6, y0 + 45)
            self.col(cr, "crust")
            cr.set_line_width(3)
            cr.stroke()

    # — workspaces —
    def workspaces(self, cr, w: float, h: float, wss: list[dict], thumbs: bool) -> dict:
        """Mini map of every workspace; returns click areas {ws name: (x, y, w, h)}."""
        self.card(cr, w, h)
        if not wss:
            self.text(cr, 18, h / 2 + 5, "No workspaces (is Sway running?)", 13, "subtext")
            return {}
        pad, gap = 12, 8
        n = len(wss)
        bw = min(150.0, (w - 2 * pad - gap * (n - 1)) / n)
        bh = h - 2 * pad - 16
        x = (w - (bw * n + gap * (n - 1))) / 2
        areas = {}
        for ws in wss:
            r = ws["rect"] or {"x": 0, "y": 0, "width": 1920, "height": 1080}
            sc = min(bw / max(1, r.get("width", 1920)), bh / max(1, r.get("height", 1080)))
            mw, mh = r.get("width", 1920) * sc, r.get("height", 1080) * sc
            mx, my = x + (bw - mw) / 2, pad + (bh - mh) / 2
            rounded(cr, mx, my, mw, mh, 4)
            self.col(cr, "crust", 0.85)
            cr.fill()
            tp = thumb_path(ws["name"])
            drawn = False
            if thumbs and tp.exists():
                drawn = self.image(cr, tp, mx, my, mw, mh)
            if not drawn:
                for win in ws["windows"]:
                    wr = win["rect"]
                    wx, wy = mx + (wr.get("x", 0) - r.get("x", 0)) * sc, my + (wr.get("y", 0) - r.get("y", 0)) * sc
                    ww, wh = max(3, wr.get("width", 0) * sc - 2), max(3, wr.get("height", 0) * sc - 2)
                    rounded(cr, wx + 1, wy + 1, ww, wh, 2)
                    self.col(cr, "accent" if win["focused"] else "surface", 0.55 if win["focused"] else 0.85)
                    cr.fill()
                    if ww > 34 and wh > 12:
                        self.text(cr, wx + 4, wy + min(wh - 2, 12), win["app"].split(".")[-1][:14], 8.5, "text", maxw=ww - 6)
            rounded(cr, mx, my, mw, mh, 4)
            self.col(cr, "accent" if ws["focused"] else "surface2", 1 if ws["focused"] else 0.7)
            cr.set_line_width(2.2 if ws["focused"] else 1)
            cr.stroke()
            label = ws["name"] + (f" · {len(ws['windows'])}" if ws["windows"] else "")
            self.text(cr, mx, h - 9, label, 11, "accent" if ws["focused"] else "subtext", bold=ws["focused"], maxw=bw)
            areas[ws["name"]] = (mx, my, mw, mh + 14)
            x += bw + gap
        return areas

    def image(self, cr, path: Path, x: float, y: float, w: float, h: float) -> bool:
        import cairo
        try:
            img = cairo.ImageSurface.create_from_png(str(path))
        except Exception:                          # noqa: BLE001 – a half-written picture is fine to skip
            return False
        iw, ih = img.get_width(), img.get_height()
        if not iw or not ih:
            return False
        cr.save()
        rounded(cr, x, y, w, h, 4)
        cr.clip()
        sc = max(w / iw, h / ih)
        cr.translate(x + (w - iw * sc) / 2, y + (h - ih * sc) / 2)
        cr.scale(sc, sc)
        cr.set_source_surface(img, 0, 0)
        cr.paint()
        cr.restore()
        return True

    # — calendar —
    def calendar(self, cr, w: float, h: float, now: time.struct_time) -> None:
        import calendar as cal
        self.card(cr, w, h)
        self.text(cr, 18, 30, time.strftime("%B %Y", now), 15, "text", bold=True)
        cw = (w - 36) / 7
        for i, d in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            self.text(cr, 18 + i * cw + cw / 2 - 8, 54, d, 11, "red" if i >= 5 else "subtext", bold=True)
        weeks = cal.Calendar(firstweekday=0).monthdayscalendar(now.tm_year, now.tm_mon)
        rh = (h - 72) / max(5, len(weeks))
        for r_, week in enumerate(weeks):
            for i, day in enumerate(week):
                if not day:
                    continue
                cx, cy = 18 + i * cw + cw / 2, 72 + r_ * rh + rh / 2
                if day == now.tm_mday:
                    cr.arc(cx, cy - 4, min(cw, rh) * 0.46, 0, 2 * math.pi)
                    self.col(cr, "accent")
                    cr.fill()
                txt = str(day)
                self.text(cr, cx - (3.5 if day < 10 else 7.5), cy + 1, txt, 12,
                          "crust" if day == now.tm_mday else "red" if i >= 5 else "text", bold=day == now.tm_mday)

    # — weather —
    def wicon(self, cr, x: float, y: float, s: float, kind: str) -> None:
        """Small weather symbol in a box s×s at x,y."""
        def cloud(cx, cy, k, key="subtext", a=1.0):
            self.col(cr, key, a)
            for dx, dy, r in ((-0.22, 0.05, 0.2), (0.0, -0.08, 0.27), (0.24, 0.04, 0.2)):
                cr.arc(cx + dx * k, cy + dy * k, r * k, 0, 2 * math.pi)
                cr.fill()
            rounded(cr, cx - 0.42 * k, cy + 0.02 * k, 0.84 * k, 0.24 * k, 0.12 * k)
            cr.fill()
        cx, cy = x + s / 2, y + s / 2
        if kind in ("sun", "partly"):
            sx, sy, r = (cx, cy, s * 0.2) if kind == "sun" else (cx - s * 0.14, cy - s * 0.14, s * 0.16)
            self.col(cr, "yellow")
            cr.arc(sx, sy, r, 0, 2 * math.pi)
            cr.fill()
            cr.set_line_width(max(1.5, s * 0.05))
            cr.set_line_cap(1)
            for i in range(8):
                a = i * math.pi / 4
                cr.move_to(sx + math.cos(a) * r * 1.45, sy + math.sin(a) * r * 1.45)
                cr.line_to(sx + math.cos(a) * r * 1.95, sy + math.sin(a) * r * 1.95)
                cr.stroke()
            if kind == "partly":
                cloud(cx + s * 0.08, cy + s * 0.12, s * 0.8, "text")
            return
        if kind == "fog":
            self.col(cr, "subtext")
            cr.set_line_width(max(1.5, s * 0.06))
            for i in range(4):
                cr.move_to(x + s * 0.15 + (i % 2) * s * 0.08, y + s * (0.3 + i * 0.14))
                cr.line_to(x + s * 0.85 - (i % 2) * s * 0.08, y + s * (0.3 + i * 0.14))
                cr.stroke()
            return
        cloud(cx, cy - s * 0.1, s * 0.85, "subtext" if kind != "cloud" else "text")
        if kind == "rain":
            self.col(cr, "blue")
            cr.set_line_width(max(1.5, s * 0.05))
            for i in range(3):
                cr.move_to(cx - s * 0.2 + i * s * 0.2, cy + s * 0.22)
                cr.line_to(cx - s * 0.26 + i * s * 0.2, cy + s * 0.38)
                cr.stroke()
        elif kind == "snow":
            self.col(cr, "text")
            for i in range(3):
                cr.arc(cx - s * 0.2 + i * s * 0.2, cy + s * 0.3, s * 0.045, 0, 2 * math.pi)
                cr.fill()
        elif kind == "storm":
            self.col(cr, "yellow")
            cr.move_to(cx + s * 0.02, cy + s * 0.12)
            cr.line_to(cx - s * 0.12, cy + s * 0.32)
            cr.line_to(cx, cy + s * 0.3)
            cr.line_to(cx - s * 0.08, cy + s * 0.46)
            cr.line_to(cx + s * 0.14, cy + s * 0.22)
            cr.line_to(cx + s * 0.02, cy + s * 0.24)
            cr.close_path()
            cr.fill()

    def weather(self, cr, w: float, h: float, wx: dict | None) -> None:
        self.card(cr, w, h)
        if not wx:
            self.text(cr, 18, h / 2, "Weather: offline or loading …", 13, "subtext")
            return
        self.wicon(cr, 14, 12, 58, weather_kind(wx["code"]))
        self.text(cr, 84, 50, f"{wx['temp']}°", 34, "text", bold=True)
        self.text(cr, 160, 34, wx["desc"], 12.5, "text", maxw=w - 172)
        self.text(cr, 160, 52, f"feels {wx['feels']}° · {wx['place']}", 11, "subtext", maxw=w - 172)
        dw = (w - 28) / max(1, len(wx["days"]))
        for i, (wd, lo, hi, code) in enumerate(wx["days"]):
            x = 14 + i * dw
            self.text(cr, x, h - 44, wd, 11, "subtext", bold=True)
            self.wicon(cr, x + 30, h - 62, 26, weather_kind(code))
            self.text(cr, x, h - 18, f"{hi}° / {lo}°", 11.5, "text")

    # — network —
    def network(self, cr, w: float, h: float, hist: list[tuple[float, float]]) -> None:
        self.card(cr, w, h)
        down, up = hist[-1] if hist else (0.0, 0.0)
        self.text(cr, 18, 30, "↓ " + rate(down), 15, "green", bold=True)
        self.text(cr, w / 2 + 6, 30, "↑ " + rate(up), 15, "accent", bold=True)
        top = max([max(d, u) for d, u in hist] + [1024.0])
        gx, gy, gw, gh = 18, 44, w - 36, h - 60
        for idx, key in ((0, "green"), (1, "accent")):
            cr.move_to(gx, gy + gh)
            for i, sample in enumerate(hist):
                cr.line_to(gx + gw * (i + 60 - len(hist)) / 59, gy + gh - gh * sample[idx] / top)
            cr.line_to(gx + gw, gy + gh)
            self.col(cr, key, 0.25)
            cr.fill_preserve()
            self.col(cr, key, 0.9)
            cr.set_line_width(1.2)
            cr.stroke()
        self.text(cr, 18, h - 6, "last 2 minutes · peak " + rate(top), 9.5, "overlay")

    # — free space —
    def disks(self, cr, w: float, h: float, ds: list[tuple[str, float, int]]) -> None:
        from .apps import human
        self.card(cr, w, h)
        for i, (lab, used, free) in enumerate(ds):
            y = 30 + i * 28
            self.text(cr, 18, y, lab, 12, "subtext", bold=True, maxw=70)
            rounded(cr, 92, y - 9, w - 190, 8, 4)
            self.col(cr, "surface2", 0.7)
            cr.fill()
            rounded(cr, 92, y - 9, (w - 190) * used, 8, 4)
            self.col(cr, "red" if used > 0.92 else "yellow" if used > 0.8 else "accent")
            cr.fill()
            self.text(cr, w - 90, y, human(free) + " free", 11, "text", maxw=82)

    # — battery —
    def battery(self, cr, w: float, h: float, b: dict | None) -> None:
        self.card(cr, w, h)
        if not b:
            self.text(cr, 18, h / 2 + 5, "No battery", 13, "subtext")
            return
        p = max(0, min(100, b["percent"])) / 100
        bx, by, bw, bh = 18, h / 2 - 16, 70, 32
        rounded(cr, bx, by, bw, bh, 5)
        self.col(cr, "text", 0.85)
        cr.set_line_width(2)
        cr.stroke()
        cr.rectangle(bx + bw + 1, by + 10, 5, 12)
        cr.fill()
        rounded(cr, bx + 4, by + 4, (bw - 8) * p, bh - 8, 3)
        self.col(cr, "red" if p < 0.15 else "yellow" if p < 0.3 else "green")
        cr.fill()
        self.text(cr, 104, h / 2 + 2, f"{b['percent']}%", 22, "text", bold=True)
        self.text(cr, 104, h / 2 + 20, b["status"].lower(), 11, "subtext")

    # — notes —
    def notes(self, cr, w: float, h: float, txt: str) -> None:
        rounded(cr, 0.5, 0.5, w - 1, h - 1, self.radius + 2)
        self.col(cr, "yellow", min(1.0, self.alpha + 0.05))
        cr.fill()
        self.col(cr, "crust", 0.15)
        cr.rectangle(0, 0, w, 16)
        cr.fill()
        import cairo
        cr.select_font_face(self.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(13)
        y = 36
        for para in txt.splitlines() or [""]:
            line = ""
            for word in para.split(" "):
                test = (line + " " + word).strip() if line else word
                if cr.text_extents(test).x_advance > w - 30 and line:
                    self.col(cr, "crust")
                    cr.move_to(14, y)
                    cr.show_text(line)
                    line, y = word, y + 17
                else:
                    line = test
            self.col(cr, "crust")
            cr.move_to(14, y)
            cr.show_text(line)
            y += 17
            if y > h - 10:
                break

    # — focus timer —
    def timer(self, cr, w: float, h: float, t: "Timer") -> None:
        self.card(cr, w, h)
        total = t.WORK if t.phase == "work" else t.BREAK
        frac = 1 - t.left / total
        cx, cy, R = 58, h / 2, 38
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        self.col(cr, "surface2", 0.6)
        cr.set_line_width(7)
        cr.stroke()
        cr.arc(cx, cy, R, -math.pi / 2, -math.pi / 2 + 2 * math.pi * frac)
        self.col(cr, "accent" if t.phase == "work" else "green")
        cr.stroke()
        m, sec = divmod(int(max(0, t.left)), 60)
        self.text(cr, cx - 24, cy + 7, f"{m:02d}:{sec:02d}", 17, "text", bold=True)
        self.text(cr, 112, cy - 6, "Focus" if t.phase == "work" else "Break", 16, "text", bold=True)
        self.text(cr, 112, cy + 14, "running" if t.running else "click to start", 11, "subtext")

    def wrap(self, cr, x: float, y: float, maxw: float, s: str, size: float) -> None:
        import cairo
        cr.select_font_face(self.font, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size)
        line, ly = "", y
        for word in s.split():
            test = (line + " " + word).strip()
            if cr.text_extents(test).x_advance > maxw and line:
                self.col(cr, "text")
                cr.move_to(x, ly)
                cr.show_text(line)
                line, ly = word, ly + size * 1.35
            else:
                line = test
        if line:
            self.col(cr, "text")
            cr.move_to(x, ly)
            cr.show_text(line)


# ── GTK runner ───────────────────────────────────────────────────────
def theme_now() -> tuple[dict, dict]:
    from . import render
    from .cyberdeck import effective
    s = effective(settings.load())
    ctx = render.make_ctx(s)
    return ({"colors": ctx.c, "font": s["theme"]["font"], "radius": s["look"]["radius"]}, dict(s.get("widgets", {})))


DEPS_CMD = "sudo dnf install gtk3 gtk-layer-shell python3-gobject python3-cairo"


def check() -> list[tuple[bool, str, str]]:
    """What the widgets need, one by one: [(ok, what, how to fix)]."""
    out: list[tuple[bool, str, str]] = []

    def probe(code: str) -> str:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
        return "" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["failed"])[-1]
    err = probe("import gi")
    out.append((not err, "Python GObject (python3-gobject)", "sudo dnf install python3-gobject"))
    err = probe("import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk")
    out.append((not err, "GTK 3", "sudo dnf install gtk3"))
    err = probe("import gi; gi.require_version('GtkLayerShell', '0.1'); from gi.repository import GtkLayerShell")
    out.append((not err, "gtk-layer-shell (puts widgets on the desktop)", "sudo dnf install gtk-layer-shell"))
    err = probe("import cairo, gi; gi.require_foreign('cairo')")
    out.append((not err, "pycairo (draws the widgets)", "sudo dnf install python3-cairo python3-gobject"))
    out.append((bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("SWAYSOCK")), "running inside Sway",
                "widgets only run in a Sway session"))
    try:
        enabled = bool(settings.load()["widgets"].get("enabled"))
    except Exception:                               # noqa: BLE001
        enabled = False
    out.append((enabled, "switched on (Settings → Desktop widgets)", "turn on “Show desktop widgets”, then Apply"))
    running = subprocess.run(["pgrep", "-f", "m [s]wayforge widgets run"], capture_output=True).returncode == 0
    out.append((running, "widgets process running", "swayforge widgets restart   (errors: ~/.local/share/swayforge/widgets.log)"))
    from shutil import which
    out.append((bool(which("playerctl")), "playerctl (music player widget)", "sudo dnf install playerctl"))
    out.append((bool(which("grim")), "grim (workspace pictures)", "sudo dnf install grim"))
    return out


def last_log(n: int = 8) -> list[str]:
    try:
        return LOG.read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def check_main() -> int:
    bad = 0
    for ok, what, fix in check():
        print(("  ✓ " if ok else "  ✗ ") + what + ("" if ok else f"\n      → {fix}"))
        bad += not ok
    lines = last_log()
    if lines:
        print("\nLast lines of the widgets log:\n  " + "\n  ".join(lines))
    return 1 if bad else 0


def _notify(title: str, body: str) -> None:
    try:
        subprocess.Popen(["notify-send", "-a", "swayforge", title, body], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _gtk():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell
    import cairo  # noqa: F401
    return Gdk, GLib, Gtk, GtkLayerShell


def _place(GtkLayerShell, win, corner: str, off: int, gap: int = 18) -> None:
    """Anchor a layer-shell window in a corner (or centred along an edge), stacked by off pixels."""
    if corner == "center":
        return                                          # no anchors = centred
    v, hz = corner.split("-")
    edge_v = GtkLayerShell.Edge.TOP if v == "top" else GtkLayerShell.Edge.BOTTOM
    GtkLayerShell.set_anchor(win, edge_v, True)
    GtkLayerShell.set_margin(win, edge_v, gap + off)
    if hz != "center":
        edge_h = GtkLayerShell.Edge.LEFT if hz == "left" else GtkLayerShell.Edge.RIGHT
        GtkLayerShell.set_anchor(win, edge_h, True)
        GtkLayerShell.set_margin(win, edge_h, gap)


def run() -> int:
    try:
        Gdk, GLib, Gtk, GtkLayerShell = _gtk()
    except (ImportError, ValueError) as e:
        msg = f"Widgets need GTK 3, gtk-layer-shell and pycairo ({e}). Install: {DEPS_CMD}"
        print(msg)
        log(msg)
        _notify("Desktop widgets can't start", f"Missing parts – run:\n{DEPS_CMD}")
        return 1
    if not os.environ.get("WAYLAND_DISPLAY"):
        print("Widgets only run inside Sway (Wayland).")
        return 1
    try:
        return _run(Gdk, GLib, Gtk, GtkLayerShell)
    except Exception as e:                          # noqa: BLE001 – say why instead of vanishing
        import traceback
        log("crashed:\n" + traceback.format_exc())
        _notify("Desktop widgets crashed", f"{type(e).__name__}: {e}\nDetails: swayforge widgets check")
        return 1


def _run(Gdk, GLib, Gtk, GtkLayerShell) -> int:
    import threading
    theme, cfg = theme_now()
    if not cfg.get("enabled"):
        return 0
    painter = Painter(theme, cfg)
    stamp = paths.SETTINGS_FILE.stat().st_mtime if paths.SETTINGS_FILE.exists() else 0
    cpu, net, timer = CpuMeter(), NetMeter(), Timer()
    state = {"player": None, "cpu": 0.0, "mem": 0.0, "temp": None, "tip": random.choice(TIPS), "areas": {},
             "ws": [], "ws_areas": {}, "weather": None, "disks": disks(), "battery": battery(),
             "notes": notes_text(), "notes_m": 0.0}
    t0 = time.monotonic()
    windows = []
    stack: dict[str, int] = {}
    stop = threading.Event()
    kinds = layout_widgets(cfg)

    for kind, corner in kinds:
        w, h = size_of(kind, cfg)
        win = Gtk.Window(title=f"swayforge {kind}")
        vis = win.get_screen().get_rgba_visual()
        if vis:
            win.set_visual(vis)
        win.set_app_paintable(True)
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "swayforge-widgets")
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.TOP if cfg.get("layer") == "top" else GtkLayerShell.Layer.BOTTOM)
        try:
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        except AttributeError:
            GtkLayerShell.set_keyboard_interactivity(win, False)
        off = stack.get(corner, 0)
        _place(GtkLayerShell, win, corner, off)
        stack[corner] = off + h + 12
        area = Gtk.DrawingArea()
        area.set_size_request(w, h)
        win.add(area)

        def draw(widget, cr, kind=kind, w=w, h=h):
            try:
                k = float(cfg.get("scale", 1.0) or 1.0)
                cr.scale(k, k)
                W, H = w / k, h / k
                now_f = time.time()
                if kind == "clock":
                    painter.clock(cr, W, H, time.localtime(now_f), now_f % 1)
                elif kind == "player":
                    areas = painter.player(cr, W, H, state["player"])
                    state["areas"] = {n: tuple(v * k for v in a) for n, a in areas.items()}
                elif kind == "sysmon":
                    painter.sysmon(cr, W, H, state["cpu"], state["mem"], state["temp"])
                elif kind == "clippy":
                    painter.clippy(cr, W, H, state["tip"], time.monotonic() - t0)
                elif kind == "workspaces":
                    areas = painter.workspaces(cr, W, H, state["ws"], bool(cfg.get("ws_thumbs", True)))
                    state["ws_areas"] = {n: tuple(v * k for v in a) for n, a in areas.items()}
                elif kind == "calendar":
                    painter.calendar(cr, W, H, time.localtime(now_f))
                elif kind == "weather":
                    painter.weather(cr, W, H, state["weather"])
                elif kind == "network":
                    painter.network(cr, W, H, net.hist)
                elif kind == "disks":
                    painter.disks(cr, W, H, state["disks"])
                elif kind == "battery":
                    painter.battery(cr, W, H, state["battery"])
                elif kind == "notes":
                    painter.notes(cr, W, H, state["notes"])
                elif kind == "timer":
                    painter.timer(cr, W, H, timer)
            except Exception as e:                  # noqa: BLE001 – one bad frame must not kill the desktop widgets
                log(f"{kind}: {type(e).__name__}: {e}")
            return False

        area.connect("draw", draw)
        if kind in ("player", "clippy", "timer", "notes", "workspaces", "weather"):
            area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

            def click(_w, ev, kind=kind, area=area):
                if kind == "clippy":
                    state["tip"] = random.choice([t for t in TIPS if t != state["tip"]])
                elif kind == "timer":
                    timer.reset() if ev.button == 3 else timer.toggle()
                elif kind == "notes":
                    if not NOTES.exists():
                        NOTES.parent.mkdir(parents=True, exist_ok=True)
                        NOTES.write_text("Click to write a note.\n")
                    subprocess.Popen(["xdg-open", str(NOTES)], start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif kind == "weather":
                    WEATHER_CACHE.unlink(missing_ok=True)
                    threading.Thread(target=load_weather, daemon=True).start()
                else:
                    hits = state["areas"] if kind == "player" else state["ws_areas"]
                    for name, (x, y, bw, bh) in hits.items():
                        if x <= ev.x <= x + bw and y <= ev.y <= y + bh:
                            cmd = ["playerctl", name] if kind == "player" else ["swaymsg", "workspace", name]
                            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                area.queue_draw()
                return True
            area.connect("button-press-event", click)
        win.show_all()
        windows.append((kind, area))

    if not windows:
        log("switched on, but every widget is off")
        return 0
    log(f"running: {', '.join(k for k, _ in kinds)}")
    on = {k for k, _ in kinds}

    def redraw(*which):
        for kind, area in windows:
            if kind in which:
                area.queue_draw()
        return False

    def load_weather():
        state["weather"] = fetch_weather(str(cfg.get("weather_city", "")))
        GLib.idle_add(redraw, "weather")

    def load_ws():
        state["ws"] = sway_workspaces()
        GLib.idle_add(redraw, "workspaces")

    def ws_events():
        """Workspace/window changes → redraw the mini map (no polling)."""
        try:
            p = subprocess.Popen(["swaymsg", "-m", "-t", "subscribe", '["workspace","window"]'],
                                 stdout=subprocess.PIPE, text=True)
        except OSError:
            return
        for _line in p.stdout:
            if stop.is_set():
                break
            load_ws()
        p.terminate()

    def tick_fast():
        ended = timer.tick() if "timer" in on else None
        if ended:
            subprocess.Popen(["notify-send", "-a", "swayforge", "Focus timer",
                              "Time for a break!" if ended == "work" else "Break over – back to work."],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        redraw("clock", "clippy", "timer", "network")
        return True

    slow_n = {"n": 0}

    def tick_slow():
        nonlocal stamp
        slow_n["n"] += 1
        if "player" in on:
            state["player"] = player_state()
        if "sysmon" in on:
            state["cpu"], state["mem"], state["temp"] = cpu.load(), memory(), temperature()
        if "network" in on:
            net.sample()
        if "battery" in on:
            state["battery"] = battery()
        if "disks" in on and slow_n["n"] % 30 == 0:
            state["disks"] = disks()
        if "notes" in on:
            try:
                m = NOTES.stat().st_mtime
            except OSError:
                m = 0.0
            if m != state["notes_m"]:
                state["notes_m"], state["notes"] = m, notes_text()
        if "weather" in on and slow_n["n"] % 900 == 0:           # every 30 minutes
            threading.Thread(target=load_weather, daemon=True).start()
        redraw("player", "sysmon", "battery", "disks", "notes")
        # settings changed (theme, positions …)? start again with the new ones
        try:
            m = paths.SETTINGS_FILE.stat().st_mtime
        except OSError:
            m = stamp
        if m != stamp:
            log("settings changed – restarting")
            stop.set()
            os.execv(sys.executable, [sys.executable, "-m", "swayforge", "widgets", "run"])
        return True

    def tip_timer():
        state["tip"] = random.choice(TIPS)
        return True

    fast = 100 if cfg.get("clock") == "analog" or "clippy" in on else 1000
    GLib.timeout_add(fast, tick_fast)
    GLib.timeout_add(2000, tick_slow)
    GLib.timeout_add(10 * 60 * 1000, tip_timer)
    if "weather" in on:
        threading.Thread(target=load_weather, daemon=True).start()
    if "workspaces" in on:
        load_ws()
        threading.Thread(target=ws_events, daemon=True).start()
    if cfg.get("ws_thumbs", True):                  # pictures for the mini map and Super+O
        threading.Thread(target=thumb_watcher, args=(stop, lambda: GLib.idle_add(redraw, "workspaces")),
                         daemon=True).start()
    tick_slow()
    Gtk.main()
    return 0


def overview() -> int:
    """Super+O: every workspace big (with the picture from your last visit), click or 1–9 to go there."""
    try:
        Gdk, GLib, Gtk, GtkLayerShell = _gtk()
    except (ImportError, ValueError) as e:
        print(f"Needs GTK 3, gtk-layer-shell and pycairo ({e})")
        return 1
    if subprocess.run(["pgrep", "-f", "m [s]wayforge widgets overview"], capture_output=True).stdout.count(b"\n") > 1:
        subprocess.run(["pkill", "-f", "m [s]wayforge widgets overview"])      # pressed again → close
        return 0
    theme, cfg = theme_now()
    if cfg.get("ws_thumbs", True):
        from shutil import which
        if which("grim"):
            capture_visible()                       # the current one is always fresh
    wss = sway_workspaces()
    painter = Painter(theme, dict(cfg, opacity=0.96))
    win = Gtk.Window(title="swayforge overview")
    vis = win.get_screen().get_rgba_visual()
    if vis:
        win.set_visual(vis)
    win.set_app_paintable(True)
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, "swayforge-overview")
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    for e in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
        GtkLayerShell.set_anchor(win, e, True)
    GtkLayerShell.set_exclusive_zone(win, -1)
    try:
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
    except AttributeError:
        GtkLayerShell.set_keyboard_interactivity(win, True)
    area = Gtk.DrawingArea()
    win.add(area)
    sel = {"i": next((i for i, w in enumerate(wss) if w["focused"]), 0), "areas": []}

    def draw(widget, cr):
        W, H = widget.get_allocated_width(), widget.get_allocated_height()
        painter.col(cr, "crust", 0.82)
        cr.paint()
        n = max(1, len(wss))
        cols = min(n, 3 if n <= 6 else 4 if n <= 8 else 5)
        rows = math.ceil(n / cols)
        pad = 48
        cw, ch = (W - pad * (cols + 1)) / cols, (H - 90 - pad * (rows + 1)) / rows
        ratio = 16 / 9
        bw, bh = (cw, cw / ratio) if cw / ratio <= ch - 30 else ((ch - 30) * ratio, ch - 30)
        sel["areas"] = []
        painter.text(cr, pad, 52, "Workspaces", 26, "text", bold=True)
        painter.text(cr, pad + 190, 52, "click or 1–9 · arrows + Enter · Esc closes", 14, "subtext")
        for i, ws in enumerate(wss):
            c, r_ = i % cols, i // cols
            x = pad + c * (cw + pad) + (cw - bw) / 2
            y = 90 + pad + r_ * (ch + pad) + (ch - 30 - bh) / 2
            rounded(cr, x - 6, y - 6, bw + 12, bh + 40, 12)
            painter.col(cr, "accent" if i == sel["i"] else "base", 0.95 if i == sel["i"] else 0.75)
            cr.fill()
            rounded(cr, x, y, bw, bh, 8)
            painter.col(cr, "mantle")
            cr.fill()
            tp = thumb_path(ws["name"])
            if not (cfg.get("ws_thumbs", True) and tp.exists() and painter.image(cr, tp, x, y, bw, bh)):
                rr = ws["rect"] or {"x": 0, "y": 0, "width": 1920, "height": 1080}
                sc = min(bw / max(1, rr.get("width", 1)), bh / max(1, rr.get("height", 1)))
                for wn in ws["windows"]:
                    q = wn["rect"]
                    wx, wy = x + (q.get("x", 0) - rr.get("x", 0)) * sc, y + (q.get("y", 0) - rr.get("y", 0)) * sc
                    rounded(cr, wx + 2, wy + 2, max(4, q.get("width", 0) * sc - 4), max(4, q.get("height", 0) * sc - 4), 5)
                    painter.col(cr, "surface", 0.95)
                    cr.fill()
                    painter.text(cr, wx + 10, wy + 24, wn["app"].split(".")[-1], 14, "text", maxw=max(10, q.get("width", 0) * sc - 20))
                if not ws["windows"]:
                    painter.text(cr, x + bw / 2 - 24, y + bh / 2, "empty", 14, "overlay")
            apps = ", ".join(dict.fromkeys(wn["app"].split(".")[-1] for wn in ws["windows"]))
            painter.text(cr, x, y + bh + 24, f"{ws['name']}", 16, "crust" if i == sel["i"] else "text", bold=True)
            painter.text(cr, x + 40, y + bh + 24, apps or "—", 13, "crust" if i == sel["i"] else "subtext", maxw=bw - 44)
            sel["areas"].append((x, y, bw, bh + 30))
        return False

    def go(i: int) -> None:
        if 0 <= i < len(wss):
            subprocess.Popen(["swaymsg", "workspace", wss[i]["name"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Gtk.main_quit()

    def key(_w, ev):
        name = Gdk.keyval_name(ev.keyval) or ""
        cols = min(max(1, len(wss)), 3 if len(wss) <= 6 else 4 if len(wss) <= 8 else 5)
        if name in ("Escape", "q", "o"):
            Gtk.main_quit()
        elif name in ("Return", "KP_Enter", "space"):
            go(sel["i"])
        elif name.isdigit():
            hit = next((i for i, w in enumerate(wss) if w["name"] == name or str(w["num"]) == name), None)
            go(hit if hit is not None else int(name) - 1)
        else:
            step = {"Right": 1, "l": 1, "Left": -1, "h": -1, "Down": cols, "j": cols, "Up": -cols, "k": -cols,
                    "Tab": 1, "ISO_Left_Tab": -1}.get(name, 0)
            if step:
                sel["i"] = (sel["i"] + step) % max(1, len(wss))
                area.queue_draw()
        return True

    def click(_w, ev):
        for i, (x, y, bw, bh) in enumerate(sel["areas"]):
            if x <= ev.x <= x + bw and y <= ev.y <= y + bh:
                go(i)
                return True
        Gtk.main_quit()
        return True

    area.connect("draw", draw)
    area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    area.connect("button-press-event", click)
    win.connect("key-press-event", key)
    win.show_all()
    Gtk.main()
    return 0


def main(action: str = "run") -> int:
    if action == "overview":
        return overview()
    if action == "check":
        return check_main()
    if action == "stop":
        subprocess.run(["pkill", "-f", "m [s]wayforge widgets run"])
        return 0
    if action == "restart":
        subprocess.run(["pkill", "-f", "m [s]wayforge widgets run"])
        subprocess.Popen([sys.executable, "-m", "swayforge", "widgets", "run"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    return run()
