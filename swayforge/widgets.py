"""Desktop widgets: dot-matrix clock, digital clock, analog clock, music player, system monitor
and Clippy – drawn on the desktop (below your windows) in the colours of your theme.

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
    "clippy": "Clippy",
}
CLOCKS = {"dots": "Dot matrix", "digital": "Digital", "analog": "Analog", "off": "Off"}
CORNERS = {"top-left": "Top left", "top-right": "Top right", "bottom-left": "Bottom left",
           "bottom-right": "Bottom right", "center": "Centre"}
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


def layout_widgets(cfg: dict) -> list[tuple[str, str]]:
    """[(kind, corner)] in drawing order – what Settings switched on."""
    out = []
    if cfg.get("clock", "dots") != "off":
        out.append(("clock", cfg.get("clock_pos", "top-right")))
    for k in ("player", "sysmon", "clippy"):
        if cfg.get(k):
            out.append((k, cfg.get(f"{k}_pos", "top-right")))
    return out


def size_of(kind: str, cfg: dict) -> tuple[int, int]:
    k = float(cfg.get("scale", 1.0) or 1.0)
    base = {"clock": {"dots": (372, 150), "digital": (330, 140), "analog": (210, 230)}.get(cfg.get("clock", "dots"), (330, 140)),
            "player": (340, 118), "sysmon": (280, 120), "clippy": (330, 190)}[kind]
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
    s = settings.load()
    ctx = render.make_ctx(s)
    return ({"colors": ctx.c, "font": s["theme"]["font"], "radius": s["look"]["radius"]}, dict(s.get("widgets", {})))


def run() -> int:
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import Gdk, GLib, Gtk, GtkLayerShell
        import cairo  # noqa: F401
    except (ImportError, ValueError) as e:
        print(f"Widgets need GTK 3, gtk-layer-shell and pycairo: sudo dnf install python3-gobject gtk-layer-shell python3-cairo ({e})")
        return 1
    if not os.environ.get("WAYLAND_DISPLAY"):
        print("Widgets only run inside Sway (Wayland).")
        return 1
    theme, cfg = theme_now()
    if not cfg.get("enabled"):
        return 0
    painter = Painter(theme, cfg)
    stamp = paths.SETTINGS_FILE.stat().st_mtime if paths.SETTINGS_FILE.exists() else 0
    cpu = CpuMeter()
    state = {"player": None, "cpu": 0.0, "mem": 0.0, "temp": None, "tip": random.choice(TIPS), "areas": {}}
    t0 = time.monotonic()
    windows = []
    stack: dict[str, int] = {}

    for kind, corner in layout_widgets(cfg):
        w, h = size_of(kind, cfg)
        win = Gtk.Window(title=f"swayforge {kind}")
        vis = win.get_screen().get_rgba_visual()
        if vis:
            win.set_visual(vis)
        win.set_app_paintable(True)
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "swayforge-widgets")
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.BOTTOM)
        try:
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        except AttributeError:
            GtkLayerShell.set_keyboard_interactivity(win, False)
        gap = 18
        off = stack.get(corner, 0)
        if corner == "center":
            pass                                            # no anchors = centred
        else:
            v, hz = corner.split("-")
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP if v == "top" else GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT if hz == "left" else GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP if v == "top" else GtkLayerShell.Edge.BOTTOM, gap + off)
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT if hz == "left" else GtkLayerShell.Edge.RIGHT, gap)
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
            except Exception as e:                  # noqa: BLE001 – one bad frame must not kill the desktop widgets
                log(f"{kind}: {type(e).__name__}: {e}")
            return False

        area.connect("draw", draw)
        if kind in ("player", "clippy"):
            area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

            def click(_w, ev, kind=kind):
                if kind == "clippy":
                    state["tip"] = random.choice([t for t in TIPS if t != state["tip"]])
                else:
                    for name, (x, y, bw, bh) in state["areas"].items():
                        if x <= ev.x <= x + bw and y <= ev.y <= y + bh:
                            subprocess.Popen(["playerctl", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            area.connect("button-press-event", click)
        win.show_all()
        windows.append((kind, area))

    if not windows:
        return 0

    def tick_fast():
        for kind, area in windows:
            if kind in ("clock", "clippy"):
                area.queue_draw()
        return True

    def tick_slow():
        nonlocal stamp
        state["player"] = player_state()
        state["cpu"], state["mem"], state["temp"] = cpu.load(), memory(), temperature()
        for kind, area in windows:
            if kind in ("player", "sysmon"):
                area.queue_draw()
        # settings changed (theme, positions …)? start again with the new ones
        try:
            m = paths.SETTINGS_FILE.stat().st_mtime
        except OSError:
            m = stamp
        if m != stamp:
            log("settings changed – restarting")
            os.execv(sys.executable, [sys.executable, "-m", "swayforge", "widgets", "run"])
        return True

    def tip_timer():
        state["tip"] = random.choice(TIPS)
        return True

    fast = 1000 if cfg.get("clock") != "analog" and not cfg.get("clippy") else 100
    GLib.timeout_add(fast, tick_fast)
    GLib.timeout_add(2000, tick_slow)
    GLib.timeout_add(10 * 60 * 1000, tip_timer)
    tick_slow()
    Gtk.main()
    return 0


def main(action: str = "run") -> int:
    if action == "stop":
        subprocess.run(["pkill", "-f", "m [s]wayforge widgets run"])
        return 0
    if action == "restart":
        subprocess.run(["pkill", "-f", "m [s]wayforge widgets run"])
        subprocess.Popen([sys.executable, "-m", "swayforge", "widgets", "run"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    return run()
