"""Animated fastfetch: a real animation plays next to your system info, then stays as the logo.

Animations (Settings → Terminal & prompt → Terminal greeting):
- spin   – your ASCII motif turns around in 3D like a coin, with depth,
- donut  – the famous spinning torus (donut.c), shaded in your theme colours,
- cube   – a solid shaded cube tumbling in space,
- fire   – flames rising from the bottom in theme colours,
- video  – any GIF or video file (needs ffmpeg for videos) turned into coloured block art,
- intro  – the motif ignites out of sparks and moves (the classic swayforge greeting).
Any key skips. The system info comes from fastfetch itself (`--logo none`), so its config
(modules, colours) still counts.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import select
import shutil
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path

from . import paths

ANIMS = {"intro": "Ignite + motion (classic)", "spin": "Your motif spins in 3D", "donut": "Spinning donut",
         "cube": "Tumbling cube", "fire": "Fire", "video": "Your own GIF / video", "off": "No animation"}
SHADES = " .,-~:;=!*#$@"
CACHE = paths.HOME / ".cache/swayforge/fetchanim"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


# ── colours ──────────────────────────────────────────────────────────
def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def ramp(a: str, b: str, n: int = 12) -> list[str]:
    """n truecolour codes from colour a to colour b."""
    pa, pb = _rgb(a), _rgb(b)
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        r, g, bb = (round(x + (y - x) * t) for x, y in zip(pa, pb))
        out.append(f"\033[38;2;{r};{g};{bb}m")
    return out


def visible_len(s: str) -> int:
    return len(ANSI.sub("", s))


# ── frame generators: each returns rows of (char, level 0..1) ─────────
Cell = tuple[str, float]


def _blank(w: int, h: int) -> list[list[Cell]]:
    return [[(" ", 0.0)] * w for _ in range(h)]


def donut(t: float, w: int, h: int) -> list[list[Cell]]:
    """donut.c by Andy Sloane, coarser so plain Python keeps up."""
    A, B = t * 1.1, t * 0.55
    out, zb = _blank(w, h), [[0.0] * w for _ in range(h)]
    cA, sA, cB, sB = math.cos(A), math.sin(A), math.cos(B), math.sin(B)
    K1 = min(w * 0.6, h * 2.2)
    j = 0.0
    while j < 6.28:
        cj, sj = math.cos(j), math.sin(j)
        i = 0.0
        while i < 6.28:
            ci, si = math.cos(i), math.sin(i)
            hh = cj + 2
            D = 1 / (si * hh * sA + sj * cA + 5)
            tt = si * hh * cA - sj * sA
            x = int(w / 2 + K1 * D * (ci * hh * cB - tt * sB))
            y = int(h / 2 + K1 * 0.5 * D * (ci * hh * sB + tt * cB))
            N = (sj * sA - si * cj * cA) * cB - si * cj * sA - sj * cA - ci * cj * sB
            if 0 <= y < h and 0 <= x < w and D > zb[y][x]:
                zb[y][x] = D
                lv = max(0.0, min(1.0, N / 1.5 + 0.08))
                out[y][x] = (SHADES[1 + int(lv * (len(SHADES) - 2))], lv)
            i += 0.045
        j += 0.11
    return out


def cube(t: float, w: int, h: int) -> list[list[Cell]]:
    ax, ay, az = t * 0.7, t * 1.0, t * 0.35
    out, zb = _blank(w, h), [[-1e9] * w for _ in range(h)]
    light = (0.4, -0.6, -0.7)
    ln = math.sqrt(sum(c * c for c in light))
    light = tuple(c / ln for c in light)

    def rot(v):
        x, y, z = v
        y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
        x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
        x, y = x * math.cos(az) - y * math.sin(az), x * math.sin(az) + y * math.cos(az)
        return x, y, z

    faces = [((0, 0, 1), lambda u, v: (u, v, 1)), ((0, 0, -1), lambda u, v: (u, v, -1)),
             ((1, 0, 0), lambda u, v: (1, u, v)), ((-1, 0, 0), lambda u, v: (-1, u, v)),
             ((0, 1, 0), lambda u, v: (u, 1, v)), ((0, -1, 0), lambda u, v: (u, -1, v))]
    size = min(w / 4, h / 2) * 0.72
    steps = 40
    for normal, fn in faces:
        n = rot(normal)
        if n[2] > 0.05:                         # faces pointing away
            continue
        lv = max(0.05, min(1.0, -(n[0] * light[0] + n[1] * light[1] + n[2] * light[2])))
        for a in range(steps + 1):
            for b in range(steps + 1):
                u, v = -1 + 2 * a / steps, -1 + 2 * b / steps
                x, y, z = rot(fn(u, v))
                p = 3.5 / (z + 3.5) * 0.72
                sx, sy = int(w / 2 + x * size * 2 * p), int(h / 2 + y * size * p)
                if 0 <= sx < w and 0 <= sy < h and -z > zb[sy][sx]:
                    zb[sy][sx] = -z
                    edge = abs(u) > 0.92 or abs(v) > 0.92
                    out[sy][sx] = ("#" if edge else SHADES[1 + int(lv * (len(SHADES) - 3))], 1.0 if edge else lv)
    return out


def spin(art: list[str], t: float, w: int, h: int) -> list[list[Cell]]:
    """The motif as a thick sign turning around its vertical axis."""
    out, zb = _blank(w, h), [[-1e9] * w for _ in range(h)]
    a = t * 1.3
    ca, sa = math.cos(a), math.sin(a)
    aw = max((len(l) for l in art), default=1)
    ah = len(art)
    oy = (h - ah) // 2
    depth = 1.6
    cx = (w - aw) // 2 + aw / 2 - 0.5                     # at rest every column lands where it was
    for layer, z0 in ((1, depth), (0, -depth)):          # back plate, then the front (nearer wins)
        if (layer == 1 and ca > 0.35) or (layer == 0 and ca < -0.35):
            continue                                     # that side is hidden anyway – no see-through noise
        for r, line in enumerate(art):
            for c, ch in enumerate(line):
                if ch == " ":
                    continue
                x = c - aw / 2 + 0.5
                xr = x * ca + z0 * sa
                z = -x * sa + z0 * ca
                p = (30 - depth) / (30 + z)                # the front plate at rest = 1:1
                sx = int(round(cx + xr * p))
                sy = oy + r
                if 0 <= sx < w and 0 <= sy < h and -z > zb[sy][sx]:
                    zb[sy][sx] = -z
                    facing = ca if layer == 0 else -ca          # how much this side looks at you
                    if facing > 0.2:
                        out[sy][sx] = (ch, 0.5 + 0.5 * facing)
                    else:                                   # edge or back: solid plate
                        out[sy][sx] = ("▓" if facing > -0.4 else "░", 0.3 + 0.3 * abs(sa))
    return out


class Fire:
    """Doom-style fire, heat 0..1 per cell."""

    def __init__(self, w: int, h: int) -> None:
        import random
        self.w, self.h, self.rnd = w, h, random.Random(7)
        self.heat = [[0.0] * w for _ in range(h)]

    def step(self) -> list[list[Cell]]:
        w, h, heat, rnd = self.w, self.h, self.heat, self.rnd
        for x in range(w):
            heat[h - 1][x] = 1.0 if rnd.random() < 0.82 else 0.55
        for y in range(h - 1):
            for x in range(w):
                sx = min(w - 1, max(0, x + rnd.randint(-1, 1)))
                heat[y][x] = max(0.0, heat[y + 1][sx] - rnd.random() * 2.2 / h)
        chars = " .:-=+*#%@"
        return [[(chars[min(len(chars) - 1, int(v * len(chars)))], v) for v in row] for row in heat]


# ── your own GIF / video → coloured half blocks ──────────────────────
def video_frames(path: str, w: int, h: int, fps: int = 12, max_frames: int = 180) -> list[list[str]]:
    """Frames as rows of ANSI text (▀ with fg = upper pixel, bg = lower pixel). Cached."""
    p = Path(os.path.expanduser(path))
    if not p.is_file():
        return []
    key = hashlib.sha1(f"{p}|{p.stat().st_mtime}|{w}x{h}|{fps}".encode()).hexdigest()[:16]
    cf = CACHE / f"video-{key}.json"
    try:
        return json.loads(cf.read_text())
    except (OSError, ValueError):
        pass
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        return []
    imgs = []
    if p.suffix.lower() in (".gif", ".webp", ".png", ".apng"):
        try:
            with Image.open(p) as im:
                for i, fr in enumerate(ImageSequence.Iterator(im)):
                    if i >= max_frames:
                        break
                    imgs.append(fr.convert("RGB"))
        except OSError:
            return []
    elif shutil.which("ffmpeg"):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-vf", f"fps={fps},scale={w}:-2",
                            "-frames:v", str(max_frames), f"{td}/%04d.png"], capture_output=True, timeout=120)
            for f in sorted(Path(td).glob("*.png")):
                with Image.open(f) as im:
                    imgs.append(im.convert("RGB"))
    frames = []
    for im in imgs:
        iw, ih = im.size
        cols = w
        rows = min(h, max(1, round(ih / iw * cols / 2)))
        im = im.resize((cols, rows * 2))
        px = im.load()
        lines = []
        for y in range(rows):
            s = []
            for x in range(cols):
                (r1, g1, b1), (r2, g2, b2) = px[x, 2 * y], px[x, 2 * y + 1]
                s.append(f"\033[38;2;{r1};{g1};{b1};48;2;{r2};{g2};{b2}m▀")
            lines.append("".join(s) + "\033[0m")
        frames.append(lines)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(frames))
    except OSError:
        pass
    return frames


# ── playback ─────────────────────────────────────────────────────────
def render_cells(rows: list[list[Cell]], colours: list[str]) -> list[str]:
    out = []
    for row in rows:
        s, last = [], ""
        for ch, lv in row:
            if ch == " ":
                s.append(" ")
                continue
            code = colours[min(len(colours) - 1, int(lv * (len(colours) - 1)))]
            if code != last:
                s.append(code)
                last = code
            s.append(ch)
        out.append("".join(s) + "\033[0m")
    return out


def fastfetch_info() -> list[str]:
    if not shutil.which("fastfetch"):
        return []
    try:
        r = subprocess.run(["fastfetch", "--logo", "none", "--pipe", "false"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return r.stdout.rstrip("\n").splitlines()


def _key(fd) -> bool:
    try:
        return fd is not None and bool(select.select([sys.stdin], [], [], 0)[0])
    except (OSError, ValueError):
        return False


def frames_for(kind: str, art: list[str], w: int, h: int, colours: dict, video: str = ""):
    """Generator of frames (list of ANSI rows) for an animation kind."""
    grad = ramp(colours["dark"], colours["bright"], 12)
    if kind == "video":
        frames = video_frames(video, w, h)
        if not frames:
            kind = "spin"
        else:
            i = 0
            while True:
                yield frames[i % len(frames)]
                i += 1
    fire = Fire(w, h) if kind == "fire" else None
    fire_grad = ramp(colours["fire0"], colours["fire1"], 6) + ramp(colours["fire1"], colours["fire2"], 6)
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        if kind == "donut":
            yield render_cells(donut(t, w, h), grad)
        elif kind == "cube":
            yield render_cells(cube(t, w, h), grad)
        elif kind == "fire":
            yield render_cells(fire.step(), fire_grad)
        else:
            yield render_cells(spin(art, t, w, h), grad)


def play(kind: str, art: list[str], colours: dict, seconds: float = 5.0, video: str = "",
         info: list[str] | None = None, fps: int = 20) -> None:
    """Animation on the left, fastfetch info on the right; the last frame stays."""
    info = fastfetch_info() if info is None else info
    cols, _rows = shutil.get_terminal_size((100, 30))
    art_w = max((len(l) for l in art), default=20)
    info_w = max((visible_len(l) for l in info), default=0)
    w = max(30, min(46, cols - info_w - 4, art_w + 8 if kind == "spin" else 46))
    h = max(len(info), len(art) + 2 if kind == "spin" else 18, 12)
    h = min(h, 24)
    if cols < w + 10:
        info = []
    fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    if fd is None and not seconds:
        seconds = 5.0                                   # no keyboard to stop it
    old = termios.tcgetattr(fd) if fd is not None else None
    gen = frames_for(kind, art, w, h, colours, video)
    frame: list[str] = []
    try:
        if fd is not None:
            tty.setcbreak(fd)
        sys.stdout.write("\033[?25l" + "\n" * h + f"\033[{h}A\0337")
        start = time.monotonic()
        while True:
            frame = next(gen)
            buf = ["\0338"]
            for r in range(h):
                left = frame[r] if r < len(frame) else ""
                pad = " " * max(0, w - visible_len(left))
                right = info[r] if r < len(info) else ""
                buf.append(f"\033[2K{left}{pad}   {right}\033[0m\n")
            sys.stdout.write("".join(buf))
            sys.stdout.flush()
            if (seconds and time.monotonic() - start >= seconds) or _key(fd):
                break
            time.sleep(1 / fps)
    finally:
        sys.stdout.write("\033[0m\033[?25h")
        sys.stdout.flush()
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            try:
                termios.tcflush(fd, termios.TCIFLUSH)
            except termios.error:
                pass


def run(kind: str | None = None, seconds: float | None = None, video: str | None = None) -> int:
    """`swayforge hello` for the non-classic animations."""
    from . import ascii as asc, settings, themes
    from .anim import mix
    s = settings.load()
    sh = s["shell"]
    kind = kind or sh.get("fetch_anim", "intro")
    t = themes.get(s["theme"]["name"])
    c = t.with_accent(s["theme"]["accent"])
    colours = {"dark": mix(c["accent2"], c["base"], 0.55), "bright": c["accent"],
               "fire0": c["red"], "fire1": c.get("orange", c["red"]), "fire2": c["yellow"]}
    if not sys.stdout.isatty():
        if shutil.which("fastfetch"):
            os.execvp("fastfetch", ["fastfetch"])
        return 0
    try:
        play(kind, asc.art(asc.resolve(s, t)), colours,
             float(sh.get("fetch_seconds", 5) or 0) if seconds is None else seconds,
             str(sh.get("fetch_video", "")) if video is None else video)
    except KeyboardInterrupt:
        pass
    return 0
