"""Screensavers: animated terminal full-screen scenes that start where the lock would, and lock when you come back.

How it works
  * swayidle starts `swayforge screensaver start` after "Lock after (minutes)".
  * start opens one full-screen terminal window per monitor that runs `swayforge screensaver run NAME`.
  * the first key press / mouse move makes swayidle call `swayforge screensaver wake`:
    it starts swaylock first, then closes the saver windows (so the desktop is never visible).
  * `swayforge screensaver preview NAME` shows a saver in the current terminal (any key quits).
The scenes below are plain Python (no packages), coloured with your theme. "cmatrix" uses the real
cmatrix program if it is installed (Apps page), otherwise the built-in matrix.
"""
from __future__ import annotations

import json
import os
import random
import select
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty

from . import paths, settings
from .system import have, run

APP_ID = "swayforge-saver"

# id -> label shown in the settings
SAVERS: dict[str, str] = {
    "off": "None (just lock)",
    "matrix": "Matrix rain (built in, theme colours)",
    "cmatrix": "cmatrix (the real program)",
    "starfield": "Starfield",
    "pipes": "Pipes",
    "fire": "Fire",
    "life": "Game of Life",
    "bounce": "Bouncing logo",
    "clock": "Big clock",
}


# ── scenes ───────────────────────────────────────────────────────────
def fg(rgb: tuple[int, int, int]) -> str:
    return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def scale(rgb: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * f))) for v in rgb)  # type: ignore[return-value]


class Screen:
    def __init__(self, accent: str, accent2: str, text: str) -> None:
        self.w, self.h = shutil.get_terminal_size((80, 24))
        self.a, self.b, self.t = hex_rgb(accent), hex_rgb(accent2), hex_rgb(text)
        self.out: list[str] = []

    def put(self, x: int, y: int, s: str, color: tuple[int, int, int] | None = None) -> None:
        if 0 <= y < self.h and 0 <= x < self.w:
            self.out.append(f"\x1b[{y + 1};{x + 1}H{fg(color) if color else ''}{s}")

    def flush(self) -> None:
        sys.stdout.write("".join(self.out))
        sys.stdout.flush()
        self.out = []


def scene_matrix(sc: Screen):
    chars = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾅﾆﾇﾈﾊﾋﾎﾏﾐﾑﾒﾓﾔﾕﾗﾘﾜ0123456789:.=*+-<>"
    cols = sc.w // 2                                  # wide characters take two cells
    drops = [random.randint(-sc.h, 0) for _ in range(cols)]
    speed = [random.choice((1, 1, 2)) for _ in range(cols)]
    tail = [random.randint(6, max(8, sc.h - 2)) for _ in range(cols)]
    tick = 0
    while True:
        tick += 1
        for i in range(cols):
            if tick % speed[i]:
                continue
            x, y = i * 2, drops[i]
            sc.put(x, y, random.choice(chars), (235, 255, 235))
            for k in range(1, 4):
                sc.put(x, y - k, random.choice(chars), scale(sc.a, 1.0 - k * 0.18))
            sc.put(x, y - tail[i], "  ")
            sc.put(x, y - tail[i] + 1, "  ")
            drops[i] += 1
            if drops[i] - tail[i] > sc.h:
                drops[i] = random.randint(-8, 0)
                tail[i] = random.randint(6, max(8, sc.h - 2))
        sc.flush()
        yield 0.045


def scene_starfield(sc: Screen):
    stars = [[random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.1, 1)] for _ in range(160)]
    prev: list[tuple[int, int]] = []
    while True:
        for x, y in prev:
            sc.put(x, y, " ")
        prev = []
        cx, cy = sc.w / 2, sc.h / 2
        for s in stars:
            s[2] -= 0.012
            if s[2] <= 0.02:
                s[:] = [random.uniform(-1, 1), random.uniform(-1, 1), 1.0]
            px, py = int(cx + s[0] / s[2] * cx * 0.35), int(cy + s[1] / s[2] * cy * 0.35)
            if 0 <= px < sc.w and 0 <= py < sc.h:
                z = 1 - s[2]
                sc.put(px, py, "·" if z < 0.4 else "•" if z < 0.75 else "✦", scale(sc.t, 0.35 + z * 0.65))
                prev.append((px, py))
        sc.flush()
        yield 0.04


def scene_pipes(sc: Screen):
    glyph = {(0, 1): "┃", (0, -1): "┃", (1, 0): "━", (-1, 0): "━",
             ((0, 1), (1, 0)): "┗", ((0, 1), (-1, 0)): "┛", ((0, -1), (1, 0)): "┏", ((0, -1), (-1, 0)): "┓",
             ((1, 0), (0, 1)): "┓", ((1, 0), (0, -1)): "┛", ((-1, 0), (0, 1)): "┏", ((-1, 0), (0, -1)): "┗"}
    pal = [sc.a, sc.b, sc.t, scale(sc.a, 0.6)]

    def new():
        return [random.randrange(sc.w), random.randrange(sc.h), random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)]),
                random.choice(pal), 0]
    pipes = [new() for _ in range(4)]
    while True:
        for p in pipes:
            x, y, d, col, n = p
            nd = d
            if random.random() < 0.15:
                nd = random.choice([v for v in [(1, 0), (-1, 0), (0, 1), (0, -1)] if v != d and v != (-d[0], -d[1])])
            sc.put(x, y, glyph.get((d, nd) if nd != d else d, "┃"), col)
            p[0], p[1], p[2] = (x + nd[0]) % sc.w, (y + nd[1]) % sc.h, nd
            p[4] += 1
            if p[4] > 400:
                p[:] = new()
                if random.random() < 0.3:
                    sc.out.append("\x1b[2J")
        sc.flush()
        yield 0.025


def scene_fire(sc: Screen):
    w, h = sc.w, sc.h
    heat = [[0.0] * w for _ in range(h + 1)]
    ramp = " .:-=+*#%@"
    while True:
        for x in range(w):
            heat[h][x] = random.choice((0.0, 0.6, 1.0, 1.0))
        for y in range(h):
            for x in range(w):
                s = (heat[y + 1][x] + heat[y + 1][(x - 1) % w] + heat[y + 1][(x + 1) % w]
                     + heat[min(h, y + 2)][x]) / 4.04
                heat[y][x] = max(0.0, s)
        for y in range(h):
            row = []
            for x in range(w):
                v = heat[y][x]
                row.append(fg(scale(sc.a, v * 1.2) if v < 0.5 else scale(sc.b, 0.6 + v * 0.5)) + ramp[min(9, int(v * 10))])
            sc.out.append(f"\x1b[{y + 1};1H" + "".join(row))
        sc.flush()
        yield 0.06


def scene_life(sc: Screen):
    w, h = sc.w // 2, sc.h
    cells = {(x, y) for x in range(w) for y in range(h) if random.random() < 0.22}
    gen = 0
    while True:
        out = ["\x1b[H"]
        for y in range(h):
            out.append("".join(("██" if (x, y) in cells else "  ") for x in range(w)) + ("\n" if y < h - 1 else ""))
        sys.stdout.write(fg(sc.a) + "".join(out))
        sys.stdout.flush()
        counts: dict[tuple[int, int], int] = {}
        for (x, y) in cells:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        k = ((x + dx) % w, (y + dy) % h)
                        counts[k] = counts.get(k, 0) + 1
        cells = {c for c, n in counts.items() if n == 3 or (n == 2 and c in cells)}
        gen += 1
        if gen % 250 == 0 or len(cells) < 12:
            cells = {(x, y) for x in range(w) for y in range(h) if random.random() < 0.22}
        yield 0.1


def scene_bounce(sc: Screen, text: str = "swayforge"):
    art = [text, "─" * len(text)]
    x, y, dx, dy = random.randrange(max(1, sc.w - len(text))), random.randrange(max(1, sc.h - 2)), 1, 1
    color = sc.a
    while True:
        for i, ln in enumerate(art):
            sc.put(x, y + i, " " * len(ln))
        x, y = x + dx, y + dy
        if x <= 0 or x + len(text) >= sc.w:
            dx = -dx
            color = random.choice((sc.a, sc.b, sc.t))
        if y <= 0 or y + 2 >= sc.h:
            dy = -dy
            color = random.choice((sc.a, sc.b, sc.t))
        for i, ln in enumerate(art):
            sc.put(x, y + i, ln, color)
        sc.flush()
        yield 0.08


DIGITS = {
    "0": ["███", "█ █", "█ █", "█ █", "███"], "1": ["  █", "  █", "  █", "  █", "  █"],
    "2": ["███", "  █", "███", "█  ", "███"], "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"], "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"], "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"], "9": ["███", "█ █", "███", "  █", "███"],
    ":": ["   ", " █ ", "   ", " █ ", "   "],
}


def scene_clock(sc: Screen):
    last = ""
    while True:
        now = time.strftime("%H:%M")
        if now != last:
            last = now
            sc.out.append("\x1b[2J")
            width = len(now) * 4 - 1
            x0, y0 = max(0, (sc.w - width) // 2), max(0, (sc.h - 5) // 2)
            for i, ch in enumerate(now):
                for r, row in enumerate(DIGITS[ch]):
                    sc.put(x0 + i * 4, y0 + r, row, sc.a)
            sc.put(max(0, (sc.w - 10) // 2), y0 + 7, time.strftime("%a %d %b"), sc.t)
            sc.flush()
        yield 1.0


SCENES = {"matrix": scene_matrix, "starfield": scene_starfield, "pipes": scene_pipes, "fire": scene_fire,
          "life": scene_life, "bounce": scene_bounce, "clock": scene_clock}


# ── running a scene ──────────────────────────────────────────────────
def _colors() -> tuple[str, str, str]:
    from . import render
    ctx = render.make_ctx(settings.load())
    return ctx.c["accent"], ctx.c.get("accent2", ctx.c["accent"]), ctx.c["text"]


def run_scene(name: str, any_key_quits: bool) -> int:
    """Draw `name` in this terminal until a key is pressed (preview) or until we are killed (real saver)."""
    if name == "cmatrix" and have("cmatrix"):
        a = _colors()[0]
        colour = min(("green", "red", "blue", "yellow", "cyan", "magenta", "white"),
                     key=lambda n: _dist(a, {"green": "#00ff00", "red": "#ff0000", "blue": "#0000ff", "yellow": "#ffff00",
                                              "cyan": "#00ffff", "magenta": "#ff00ff", "white": "#ffffff"}[n]))
        if any_key_quits:
            return subprocess.call(["cmatrix", "-s", "-b", "-C", colour])
        # real saver: cmatrix would quit on any key – feed it nothing, it just keeps running until killed
        return subprocess.call(["cmatrix", "-b", "-C", colour], stdin=subprocess.DEVNULL)
    scene = SCENES.get(name) or SCENES["matrix"]
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd) if sys.stdin.isatty() else None
    if old:
        tty.setcbreak(fd)
    if not any_key_quits:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    born = time.time()
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    if not any_key_quits:
        sys.stdout.write("\x1b[?1003h\x1b[?1006h")      # report mouse movement too
    try:
        colors = _colors()
        sc = Screen(*colors)
        gen = scene(sc)
        last_check = time.time()
        while True:
            size = shutil.get_terminal_size((80, 24))
            if (sc.w, sc.h) != (size.columns, size.lines):       # window became full-screen / changed monitor
                sys.stdout.write("\x1b[0m\x1b[2J")
                sc = Screen(*colors)
                gen = scene(sc)
            delay = next(gen)
            if any_key_quits and old and select.select([sys.stdin], [], [], delay)[0]:
                return 0
            elif not any_key_quits:
                if time.time() - last_check > 5:
                    last_check = time.time()
                    if run(["pgrep", "-x", "swayidle"]).returncode != 0:
                        return 0                  # nobody left to wake us: don't trap the screen
                if old and select.select([sys.stdin], [], [], 0)[0]:
                    os.read(fd, 1024)                 # key press / mouse move inside the saver window
                    if time.time() - born > GRACE + 1:
                        wake()                        # swayidle may have missed it: lock + close ourselves
                        return 0
                time.sleep(delay)
    finally:
        sys.stdout.write("\x1b[?1003l\x1b[?1006l\x1b[0m\x1b[?25h\x1b[?1049l")
        if old:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _dist(a: str, b: str) -> int:
    x, y = hex_rgb(a), hex_rgb(b)
    return sum((p - q) ** 2 for p, q in zip(x, y))


# ── start / wake (called by swayidle) ────────────────────────────────
def saver_name(s: dict) -> str:
    n = s["power"].get("screensaver", "off")
    return n if n in SAVERS else "off"


def _outputs() -> list[str]:
    r = run(["swaymsg", "-t", "get_outputs", "-r"])
    try:
        return [o["name"] for o in json.loads(r.stdout or "[]") if o.get("active", True)]
    except ValueError:
        return []


def running() -> bool:
    return run(["pgrep", "-f", "--", f"class {APP_ID}"]).returncode == 0


STATE = paths.STATE_DIR / "screensaver.state"
LOG = paths.STATE_DIR / "screensaver.log"
GRACE = 3.0          # seconds after the start in which "activity" is ignored (focus change / pointer warp)


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        if LOG.stat().st_size > 50_000:
            LOG.write_text("".join(LOG.read_text().splitlines(True)[-100:]))
    except OSError:
        pass


def _window_cmd(s: dict, cmd: str) -> list[str]:
    """Terminal command for a saver window: no padding, no transparency, plain black, no decorations."""
    import shlex
    term = s["general"]["terminal"]
    if term == "alacritty":
        return ["alacritty", "--class", APP_ID, "-o", "window.padding.x=0", "-o", "window.padding.y=0",
                "-o", "window.opacity=1", "-o", 'window.decorations="none"',
                "-o", 'colors.primary.background="#000000"', "-e", *shlex.split(cmd)]
    return ["kitty", "--class", APP_ID, "-o", "window_padding_width=0", "-o", "background_opacity=1",
            "-o", "background=#000000", "-o", "hide_window_decorations=yes", "-o", "confirm_os_window_close=0",
            "-o", "remember_window_size=no", "-o", "tab_bar_style=hidden", *shlex.split(cmd)]


def start(s: dict | None = None) -> int:
    from . import render
    s = s or settings.load()
    name = saver_name(s)
    if name == "off" or running():
        return 0
    cmd = f"{render.LAUNCHER} screensaver run {name}"
    outs = _outputs() or [""]
    log(f"start {name} on {outs}")
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(str(time.time()))
    except OSError:
        pass
    run(["swaymsg", "mouse_warping none"])        # focusing another monitor must not move the pointer = "activity"
    for o in outs:
        if o:
            run(["swaymsg", f"focus output {o}"])
        subprocess.Popen(_window_cmd(s, cmd), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.25)
    # belt and braces: a fullscreen window must not count as "something is being watched" (that cancels idle)
    for _ in range(8):
        run(["swaymsg", f'[app_id="{APP_ID}"] inhibit_idle none, border none, fullscreen enable'])
        time.sleep(0.25)
    try:
        STATE.write_text(str(time.time()))            # the grace period counts from "windows are up"
    except OSError:
        pass
    return 0


def wake(s: dict | None = None) -> int:
    """First input after the saver: lock (if locking is on), then close the saver windows."""
    s = s or settings.load()
    if not running():
        log("wake: nothing running")
        return 0
    try:
        age = time.time() - float(STATE.read_text())
    except (OSError, ValueError):
        age = 999.0
    if age < GRACE:
        log(f"wake ignored: only {age:.1f}s after start (focus/pointer noise)")
        return 0
    log(f"wake after {age:.0f}s: lock + close")
    run(["swaymsg", "mouse_warping output"])
    if s["power"]["lock_after"] > 0 and run(["pgrep", "-x", "swaylock"]).returncode != 0:
        subprocess.Popen(["swaylock", "-f"], start_new_session=True)
        time.sleep(0.4)
    run(["pkill", "-f", "--", f"class {APP_ID}"])
    run(["pkill", "-f", "--", "screensaver run"])
    return 0


def preview(name: str) -> int:
    return run_scene(name, True)
