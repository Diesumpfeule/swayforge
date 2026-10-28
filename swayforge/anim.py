"""Animated ASCII art – the same effect everywhere (apps, terminal greeting, LibreWolf).

The art itself moves (theme.motion):
- wave  – every row sways a little later than the one above, like a flag in the wind,
- float – the whole motif drifts up and down and side to side, slowly,
- drift – it glides sideways through its box and comes back in on the other side,
- glint – it stays put (only the light effects below).
Two layers on top of any motif, so your own art animates too:
- a band of light sweeps diagonally across it every few seconds ("glint"),
- sparks and stars (* + . ' `) twinkle on their own.
Intro: the motif ignites out of sparks (used by the terminal greeting and the installer).
"""
from __future__ import annotations

import os
import select
import shutil
import sys
import termios
import time
import tty

from .ascii import SHADE

SPARKS = set("*+.'`")
PERIOD = 6.0          # seconds between two glints
SWEEP = 1.4           # how long one glint takes to cross
BAND = 5.0            # glint width in columns


def _hash(*v: int) -> float:
    h = 2166136261
    for x in v:
        h = ((h ^ (x & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


MOTIONS = {"wave": "Wave like a flag", "float": "Float gently", "drift": "Drift sideways", "glint": "Stay put (only glint)"}
AMP = 2               # how far (columns) wave/float move – the box is that much wider on both sides


def move(lines: list[str], t: float, motion: str = "wave") -> list[str]:
    """The art displaced for time t. The result always has the same size, so nothing around it jumps."""
    import math
    if motion not in ("wave", "float", "drift") or not lines:
        return lines
    width = max(map(len, lines), default=0)
    rows = [l.ljust(width) for l in lines]
    if motion == "drift":
        span = width + 6
        off = int(t * 6) % span                                  # 6 columns per second
        return [(r + " " * 6)[off:] + (r + " " * 6)[:off] for r in rows]
    out = []
    if motion == "wave":
        for i, r in enumerate(rows):
            dx = round(AMP * math.sin(t * 2.2 - i * 0.55))
            out.append(" " * (AMP + dx) + r + " " * (AMP - dx))
        return out
    # float: sideways sway plus one row of vertical bob
    dx = round(AMP * math.sin(t * 0.9))
    up = math.sin(t * 1.3) > 0
    out = [" " * (AMP + dx) + r + " " * (AMP - dx) for r in rows]
    blank = " " * (width + 2 * AMP)
    return ([blank] + out) if up else (out + [blank])


def cells(lines: list[str], t: float, intro: float | None = None):
    """Yield (row, col, char, kind) – kind: face | shade | glint | hot | off.

    intro = seconds since the ignite started (None = no intro, fully lit)."""
    width = max(map(len, lines), default=1)
    diag = width + len(lines) * 2 + BAND * 2
    phase = (t % PERIOD) / SWEEP
    pos = -BAND + phase * diag if phase <= 1 else -1e9
    slot = int(t * 4)                                     # twinkle changes 4× a second
    for r, line in enumerate(lines):
        for c, ch in enumerate(line):
            if ch == " ":
                yield r, c, ch, "off"
                continue
            if intro is not None:
                k = _hash(r, c, 7)
                heat = intro / 0.8
                if heat < k:
                    yield r, c, " ", "off"
                    continue
                if heat < k + 0.22:
                    yield r, c, "*+'.`"[int(_hash(r, c, int(intro * 20)) * 5)], "hot"
                    continue
            lone = (c == 0 or line[c - 1] == " ") and (c + 1 >= len(line) or line[c + 1] == " ")
            if ch in SPARKS and lone and _hash(r, c, slot) < 0.35:      # only free-standing sparks
                yield r, c, ".+*'"[int(_hash(c, r, slot) * 4)], "hot"
                continue
            d = (c + r * 2) - pos
            if 0 <= d < BAND:
                yield r, c, ch, "glint"
            else:
                yield r, c, ch, "shade" if ch in SHADE else "face"


# ── Textual / Rich ───────────────────────────────────────────────────
def rich_frame(lines: list[str], t: float, styles: dict[str, str], intro: float | None = None,
               motion: str = "glint"):
    from rich.text import Text
    out = Text(no_wrap=True)
    row = 0
    for r, _c, ch, kind in cells(move(lines, t, motion), t, intro):
        while row < r:
            out.append("\n")
            row += 1
        out.append(ch, style=styles.get(kind, ""))
    return out


# ── Terminal greeting (before fastfetch) ─────────────────────────────
def _sgr(hexcol: str, bold: bool = False) -> str:
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"\033[{'1;' if bold else ''}38;2;{r};{g};{b}m"


def _key_pressed() -> bool:
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except (OSError, ValueError):
        return False


def greet(lines: list[str], colors: dict[str, str], duration: float = 1.1, fps: int = 30,
          motion: str = "glint") -> None:
    """Ignite the motif in the terminal, then clear it (fastfetch prints the final one).
    Any key skips. Nothing happens when output isn't a terminal."""
    if not sys.stdout.isatty() or not lines:
        return
    cols = shutil.get_terminal_size((80, 24)).columns
    lines = [l[:cols - 1] for l in lines]
    sty = {"face": _sgr(colors["face"], True), "shade": _sgr(colors["shade"]),
           "glint": _sgr(colors["glint"], True), "hot": _sgr(colors["hot"], True), "off": ""}
    orig = lines
    n = len(move(orig, 0.0, motion))                     # float needs one extra row to bob in
    fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    old = termios.tcgetattr(fd) if fd is not None else None
    try:
        if fd is not None:
            tty.setcbreak(fd)
        sys.stdout.write("\033[?25l" + "\n" * n + f"\033[{n}A")
        start = time.monotonic()
        while True:
            t = time.monotonic() - start
            buf, row = ["\0337"], 0
            for r, _c, ch, kind in cells(move(orig, t, motion), t / duration * SWEEP, intro=t):   # one glint during the intro
                while row < r:
                    buf.append("\033[0m\n")
                    row += 1
                buf.append(sty[kind] + ch)
            buf.append("\033[0m\0338")
            sys.stdout.write("".join(buf))
            sys.stdout.flush()
            if t >= duration or (fd is not None and _key_pressed()):
                break
            time.sleep(1 / fps)
    finally:
        sys.stdout.write("\033[0J\033[?25h")             # clear the area – fastfetch draws the real one
        sys.stdout.flush()
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            try:
                termios.tcflush(fd, termios.TCIFLUSH)    # the skip key doesn't end up in the prompt
            except termios.error:
                pass


def mix(a: str, b: str, t: float) -> str:
    pa, pb = (tuple(int(x.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for x in (a, b))
    return "#%02x%02x%02x" % tuple(round(p + (q - p) * t) for p, q in zip(pa, pb))


def hello() -> int:
    """`swayforge hello` – animated greeting, then fastfetch."""
    from . import ascii as asc, settings, themes
    s = settings.load()
    if s["theme"].get("animate", True):
        t = themes.get(s["theme"]["name"])
        c = t.with_accent(s["theme"]["accent"])
        try:
            motion = s["theme"].get("motion", "wave")
            greet(asc.art(asc.resolve(s, t)),
                  {"face": c["accent"], "shade": mix(c["accent"], c["base"], 0.45),
                   "glint": c["text"], "hot": c["yellow"]},
                  duration=1.1 if motion == "glint" else 1.8, motion=motion)
        except KeyboardInterrupt:
            pass
    if shutil.which("fastfetch"):
        os.execvp("fastfetch", ["fastfetch"])
    return 0
