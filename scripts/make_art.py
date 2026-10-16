#!/usr/bin/env python3
"""Generate swayforge's ASCII art: shaded character-ramp pictures + a banner font.

Dev tool only (needs numpy, scipy, Pillow) – the results are plain text files that
ship in the package, so swayforge itself needs none of these at runtime.

Every motif is drawn from scratch here out of simple shapes (circles, polygons,
lines). Each shape is "pillowed" into a height field, lit from the top left and
turned into characters from a density ramp: dense letters for lit faces, dots and
commas for shadows and edges – the classic newsprint ASCII-art look.

    python3 scripts/make_art.py            # writes swayforge/data/art/*.txt + banner.json
    python3 scripts/make_art.py --preview  # also writes PNG previews to /tmp/art-preview
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "swayforge" / "data" / "art"
# light → dense. No $ (fastfetch colour escapes), no \ " < > & (escaping trouble).
RAMP = " .`'^,:;Il!i~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW8%B@"
SS = 6                       # supersampling per character column (rows get 2×)
LIGHT = np.array([-0.55, -0.65, 0.52])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


class Canvas:
    """Square drawing units: x in 0..cols, y in 0..rows*2 (a character cell is 1×2)."""

    def __init__(self, cols: int, rows: int, k: float = 1.0):
        # cols/rows = design size in units; k scales the output (k=1.3 → 30% more characters)
        self.cols, self.rows = cols, rows
        self.u = SS * k                                  # pixels per drawing unit
        self.ocols, self.orows = round(cols * k), round(rows * k)
        self.w, self.h = self.ocols * SS, self.orows * SS * 2
        self.height = np.zeros((self.h, self.w))
        self.albedo = np.zeros((self.h, self.w))
        self.fg = np.zeros((self.h, self.w), bool)
        self.glow = np.zeros((self.h, self.w))
        self.flat = np.zeros((self.h, self.w))         # unlit brightness (screens, text)
        self.chars: dict[tuple[int, int], str] = {}    # literal characters on top (text, sparks)

    # ── drawing helpers (units → pixels) ────────────────────────────
    def _img(self):
        img = Image.new("L", (self.w, self.h), 0)
        return img, ImageDraw.Draw(img)

    def P(self, pts):
        return [(x * self.u, y * self.u) for x, y in pts]

    def mask(self, fn) -> np.ndarray:
        img, d = self._img()
        fn(d, self)
        return np.array(img) > 127

    def ellipse(self, cx, cy, rx, ry):
        return self.mask(lambda d, c: d.ellipse([(cx - rx) * c.u, (cy - ry) * c.u, (cx + rx) * c.u, (cy + ry) * c.u], fill=255))

    def poly(self, pts):
        return self.mask(lambda d, c: d.polygon(self.P(pts), fill=255))

    def rect(self, x0, y0, x1, y1, r=0):
        return self.mask(lambda d, c: d.rounded_rectangle([x0 * c.u, y0 * c.u, x1 * c.u, y1 * c.u], radius=r * c.u, fill=255))

    def line(self, pts, width):
        return self.mask(lambda d, c: d.line(self.P(pts), fill=255, width=max(1, int(width * c.u)), joint="curve"))

    def text(self, x, y, s, size, font="DejaVuSansMono-Bold"):
        f = ImageFont.truetype(_font(font), int(size * self.u))
        return self.mask(lambda d, c: d.text((x * c.u, y * c.u), s, font=f, fill=255))

    # ── painting (later shapes sit on top) ───────────────────────────
    def add(self, m, albedo=1.0, z=0.0, round_=1.2, profile="dome"):
        """Pillow a mask into a raised shape. round_ = edge radius in units."""
        if not m.any():
            return
        dist = ndimage.distance_transform_edt(m) / self.u
        t = np.clip(dist / max(round_, 1e-3), 0, 1)
        if profile == "dome":
            h = np.sqrt(1 - (1 - t) ** 2) * round_
        elif profile == "cone":
            h = t * round_
        else:                                   # flat with a slight bevel
            h = np.minimum(t * 4, 1) * round_ * 0.3
        self.height[m] = z + h[m]
        self.albedo[m] = albedo
        self.fg[m] = True
        self.flat[m] = 0

    def cut(self, m):
        self.fg[m] = False
        self.height[m] = 0
        self.albedo[m] = 0
        self.flat[m] = 0

    def paint(self, m, value):
        """Unlit area with a fixed brightness (screen text, slits, pupils)."""
        self.fg[m] = True
        self.flat[m] = value
        self.albedo[m] = -1

    def shine(self, m, strength=1.0, spread=2.5):
        g = ndimage.gaussian_filter(m.astype(float), spread * self.u)
        self.glow += g * strength

    def write(self, x, y, text):
        """Literal text at unit position (x, y) – real letters on screens, sparks as * etc."""
        k = self.u / SS
        r, c0 = int(round(y * k / 2)), int(round(x * k))
        for i, ch in enumerate(text):
            self.chars[(r, c0 + i)] = ch

    def radial(self, m, cx, cy, r, inner, outer):
        """Unlit area brightening towards (cx, cy) – lit glass, glowing screens."""
        yy, xx = np.mgrid[0:self.h, 0:self.w] / self.u
        d = np.clip(np.hypot(xx - cx, yy - cy) / r, 0, 1)
        self.fg[m] = True
        self.albedo[m] = -1
        self.flat[m] = (inner + (outer - inner) * d)[m]

    # ── output ───────────────────────────────────────────────────────
    def luminance(self) -> np.ndarray:
        hgt = ndimage.gaussian_filter(self.height, self.u * 0.35)
        gy, gx = np.gradient(hgt)
        gx, gy = gx * self.u, gy * self.u                     # slope per drawing unit
        n = np.dstack([-gx, -gy, np.ones_like(gx)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        lam = np.clip(n @ LIGHT, 0, 1)
        spec = np.clip(n @ np.array([0, 0, 1.0]), 0, 1) ** 24 * 0.15
        lum = self.albedo * (0.08 + 0.92 * lam) + spec
        # broad light falloff from the top left + a little grain: no flat runs of one letter
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        fall = 1.0 - 0.45 * (xx / self.w * 0.6 + yy / self.h * 0.4)
        grain = ndimage.gaussian_filter(np.random.default_rng(3).normal(0, 1, lum.shape), self.u * 0.6)
        grain = grain / (np.abs(grain).max() or 1) * 0.10
        lum = lum * fall + grain * (self.albedo > 0)
        lum = np.where(self.albedo < 0, self.flat, lum)
        lum = np.where(self.fg, np.maximum(lum, 0.09), 0)
        # dark outline along every silhouette, like an inked edge
        edge = self.fg & ~ndimage.binary_erosion(self.fg, iterations=max(1, int(self.u // 3)))
        lum = np.where(edge, lum * 0.55, lum)
        lum = np.clip(lum + self.glow * (~self.fg) * 0.55, 0, 1)
        top = np.percentile(lum[self.fg], 97) if self.fg.any() else 1
        return np.clip(lum / max(top, 0.3), 0, 1)       # stretch: brightest faces reach '@'

    def to_text(self, gamma=0.85) -> list[str]:
        lum = self.luminance()
        cov = self.fg.astype(float) + np.clip(self.glow, 0, 1) * 0.6
        cells = lum.reshape(self.orows, SS * 2, self.ocols, SS).mean(axis=(1, 3))
        cover = cov.reshape(self.orows, SS * 2, self.ocols, SS).mean(axis=(1, 3))
        out = []
        n = len(RAMP) - 1
        for r in range(self.orows):
            row = []
            for c in range(self.ocols):
                if (r, c) in self.chars:
                    row.append(self.chars[(r, c)])
                    continue
                v = cells[r, c]
                if cover[r, c] < 0.18 or v < 0.025:
                    row.append(" ")
                    continue
                v = v / max(cover[r, c], 0.35)              # partial cells: keep their tone
                idx = int(round((min(v, 1) ** gamma) * (n - 1))) + 1
                row.append(RAMP[min(idx, n)])
            out.append("".join(row).rstrip())
        while out and not out[0].strip():
            out.pop(0)
        while out and not out[-1].strip():
            out.pop()
        pad = min((len(l) - len(l.lstrip()) for l in out if l.strip()), default=0)
        return [l[pad:] for l in out]


def _font(name: str) -> str:
    for base in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",
                 "/usr/share/fonts/dejavu-sans-mono-fonts", "/usr/share/fonts/dejavu-sans-fonts"):
        p = Path(base) / f"{name}.ttf"
        if p.exists():
            return str(p)
    raise SystemExit(f"font {name} not found")


def stars(c: Canvas, pts, size=0.5):
    for i, (x, y) in enumerate(pts):
        c.write(x, y, "*+.'"[i % 4] if size >= 0.35 else ".+'*"[i % 4])


# ── Motifs ───────────────────────────────────────────────────────────
def m_bat(c: Canvas):
    cx = c.cols / 2
    wing = [(cx, 9), (cx - 4, 7.5), (cx - 9, 5), (cx - 15, 4), (cx - 19.5, 7), (cx - 17, 9),
            (cx - 18, 13.5), (cx - 14, 12), (cx - 13, 17), (cx - 9.5, 14.5), (cx - 7, 19.5),
            (cx - 4, 16), (cx, 23)]
    full = wing + [(2 * cx - x, y) for x, y in reversed(wing)]
    c.add(c.poly(full), 0.85, round_=1.4)
    # wing bones
    for side in (-1, 1):
        for tip in ((15, 4.6), (17.5, 9.5), (13.2, 15.5), (7.2, 18.5)):
            c.add(c.line([(cx + side * 3, 10), (cx + side * tip[0], tip[1])], 0.45), 1.0, z=1.3, round_=0.3)
    c.add(c.ellipse(cx, 13, 3.2, 6.5), 1.0, z=0.6, round_=3)                 # body
    c.add(c.ellipse(cx, 6.5, 3.0, 3.0), 1.0, z=1.0, round_=2.5)              # head
    c.add(c.poly([(cx - 2.8, 6), (cx - 2.6, 1.6), (cx - 0.9, 4.2)]), 1.0, z=1.0, round_=0.6)
    c.add(c.poly([(cx + 2.8, 6), (cx + 2.6, 1.6), (cx + 0.9, 4.2)]), 1.0, z=1.0, round_=0.6)
    for s in (-1, 1):
        c.cut(c.ellipse(cx + s * 1.15, 6.4, 0.65, 0.6))
    stars(c, [(4, 20.5), (35, 21.5), (31, 1.5), (7, 1.0)], 0.35)


def m_moon(c: Canvas):
    cx, cy, r = c.cols / 2 - 2, 15, 13.5
    disc = c.ellipse(cx, cy, r, r)
    c.add(disc, 0.95, round_=r)
    for x, y, rr in ((-4, -5, 2.6), (3.5, 2, 3.4), (-6, 5, 1.8), (5, -7, 1.5), (-1, 9, 2.0), (8, 6, 1.2)):
        crater = c.ellipse(cx + x, cy + y, rr, rr) & disc
        rim = c.ellipse(cx + x, cy + y, rr + 0.5, rr + 0.5) & disc
        c.add(rim, 1.0, z=c.height[rim].mean() if rim.any() else 0, round_=0.4)
        c.add(crater, 0.6, z=c.height[crater].mean() - 0.6 if crater.any() else 0, round_=-0.1 + 0.6, profile="cone")
    shadow = c.ellipse(cx + 7.5, cy - 3, r * 0.95, r * 0.95) & disc
    c.albedo[shadow] *= 0.18
    stars(c, [(c.cols - 4, 5), (c.cols - 7, 23), (c.cols - 2, 15), (3, 27)], 0.4)


def m_rose(c: Canvas):
    cx, cy = c.cols / 2, 11
    # leaves and stem first (behind)
    stem = c.line([(cx, cy + 6), (cx - 1, cy + 14), (cx + 0.5, cy + 22), (cx - 0.5, cy + 28)], 1.1)
    c.add(stem, 0.75, round_=0.6)
    c.add(c.poly([(cx - 0.5, cy + 15), (cx - 6, cy + 12.5), (cx - 11, cy + 14.5), (cx - 6, cy + 17.5)]), 0.8, round_=1.6)
    c.add(c.poly([(cx + 0.3, cy + 20), (cx + 6, cy + 17), (cx + 11, cy + 18.5), (cx + 5.5, cy + 22)]), 0.8, round_=1.6)
    for x, y in ((cx - 0.8, cy + 9), (cx + 0.6, cy + 24)):
        c.add(c.poly([(x, y), (x - 1.6, y - 0.4), (x - 0.2, y - 1.4)]), 0.9, z=0.6, round_=0.3)
    # outer petals
    for ang in range(0, 360, 60):
        a = math.radians(ang + 15)
        px, py = cx + math.cos(a) * 5.0, cy + math.sin(a) * 4.0
        c.add(c.ellipse(px, py, 5.2, 4.3), 0.9, z=0.5, round_=3.5)
    # inner spiral of petals
    for i, (rr, ang) in enumerate(((3.8, 40), (3.2, 160), (2.8, 280), (2.2, 20), (1.7, 150), (1.2, 260))):
        a = math.radians(ang)
        px, py = cx + math.cos(a) * rr * 0.6, cy + math.sin(a) * rr * 0.5
        m = c.ellipse(px, py, rr + 1.2, rr + 0.6)
        c.add(m, 1.0, z=1.8 + i * 0.5, round_=rr * 0.9)
    c.cut(c.line([(cx - 1.4, cy - 0.6), (cx + 1.0, cy - 1.4), (cx + 1.6, cy + 0.6)], 0.35))


def m_skull(c: Canvas):
    cx = c.cols / 2
    c.add(c.ellipse(cx, 12, 12.5, 11.5), 0.95, round_=9)                       # cranium
    c.add(c.rect(cx - 7.5, 16, cx + 7.5, 26, r=3), 0.9, z=1.0, round_=3)        # jaw
    c.add(c.ellipse(cx - 8.6, 18.5, 3.3, 3.8), 0.9, z=1.0, round_=2.5)         # cheekbones
    c.add(c.ellipse(cx + 8.6, 18.5, 3.3, 3.8), 0.9, z=1.0, round_=2.5)
    for s in (-1, 1):
        eye = c.ellipse(cx + s * 4.8, 14.5, 3.6, 3.4)
        c.cut(eye)
        c.paint(c.ellipse(cx + s * 4.8, 14.8, 0.9, 0.9) & eye, 0.35)
    c.cut(c.poly([(cx, 17.8), (cx - 1.6, 21.3), (cx + 1.6, 21.3)]))            # nose
    for i in range(-3, 4):                                                     # teeth gaps
        c.cut(c.rect(cx + i * 1.9 - 0.18, 22.5, cx + i * 1.9 + 0.18, 26.4))
    c.cut(c.rect(cx - 7.5, 24.2, cx + 7.5, 24.6))


def m_anvil(c: Canvas):
    cx = c.cols / 2
    top = [(2, 7), (8, 6), (c.cols - 3, 6), (c.cols - 3, 10), (cx + 7, 11), (cx + 4.5, 14),
           (cx - 4.5, 14), (cx - 7, 11), (9, 10), (4, 9)]
    c.add(c.poly(top), 0.95, round_=1.5)
    c.add(c.poly([(cx - 4.5, 13.5), (cx + 4.5, 13.5), (cx + 3.2, 20), (cx - 3.2, 20)]), 0.8, round_=1.2)
    c.add(c.poly([(cx - 9, 25), (cx - 6, 20), (cx + 6, 20), (cx + 9, 25)]), 0.9, round_=1.2)
    c.add(c.rect(cx - 13, 25, cx + 13, 27.5, r=0.5), 0.7, round_=0.8)
    c.add(c.rect(c.cols - 8, 6.4, c.cols - 6.6, 7.4), 0.3, z=1.6, round_=0.2)  # hardy hole


def m_forge(c: Canvas):
    cx = c.cols / 2
    m_anvil_small(c, cx + 3, 18)
    # hammer coming down: thick handle, heavy head
    c.add(c.line([(cx - 15, 14), (cx - 2.5, 5.5)], 2.0), 0.75, round_=1.0)
    c.add(c.poly([(cx - 4.5, 1.0), (cx + 3.5, 1.0), (cx + 3.5, 7.0), (cx - 4.5, 7.0)]), 1.0, z=1.2, round_=1.6)
    c.add(c.rect(cx + 3.3, 1.6, cx + 5.0, 6.4, r=0.4), 0.9, z=1.4, round_=0.6)      # striking face
    hot = c.ellipse(cx + 5, 16.2, 4.0, 1.0)
    c.radial(hot, cx + 5, 16.2, 4, 1.0, 0.7)
    # sparks flying off the hot metal
    rnd = np.random.default_rng(11)
    for _ in range(26):
        a = rnd.uniform(-2.9, -0.25)
        d = rnd.uniform(2.5, 17)
        x, y = cx + 5 + math.cos(a) * d * 1.25, 15 + math.sin(a) * d * 0.75
        if c.fg[int(min(y, c.rows * 2 - 1) * c.u), int(min(max(x, 0), c.cols - 1) * c.u)]:
            continue
        c.write(x, y, rnd.choice(list("*'.+`*.")))


def m_anvil_small(c: Canvas, cx, y):
    top = [(cx - 15, y + 0.5), (cx - 10, y - 1), (cx + 14, y - 1), (cx + 14, y + 2.5),
           (cx + 6, y + 3.5), (cx + 4, y + 6), (cx - 4, y + 6), (cx - 6, y + 3.5), (cx - 9.5, y + 2.5)]
    c.add(c.poly(top), 0.95, round_=1.3)
    c.add(c.poly([(cx - 4, y + 5.5), (cx + 4, y + 5.5), (cx + 3, y + 9), (cx - 3, y + 9)]), 0.8, round_=1)
    c.add(c.poly([(cx - 7.5, y + 12.5), (cx - 5, y + 9), (cx + 5, y + 9), (cx + 7.5, y + 12.5)]), 0.9, round_=1)


def m_lantern(c: Canvas):
    cx = c.cols / 2
    c.add(c.line([(cx, 0), (cx, 3)], 0.6), 0.8, round_=0.3)
    ring = c.ellipse(cx, 4, 2.2, 1.7) & ~c.ellipse(cx, 4, 1.1, 0.8)
    c.add(ring, 1.0, round_=0.6)
    c.add(c.poly([(cx - 3, 6), (cx + 3, 6), (cx + 7, 10), (cx - 7, 10)]), 0.9, round_=1.4)   # roof
    c.add(c.rect(cx - 6, 10, cx + 6, 11.5, r=0.5), 0.8, z=0.4, round_=0.6)
    glass = c.poly([(cx - 5.2, 11.5), (cx + 5.2, 11.5), (cx + 6.2, 23), (cx - 6.2, 23)])
    c.radial(glass, cx, 18, 7, 0.32, 0.03)
    flame = c.poly([(cx, 13.0), (cx + 1.8, 17.5), (cx + 1.4, 19.8), (cx, 20.8), (cx - 1.4, 19.8), (cx - 1.8, 17.5)])
    c.paint(flame, 1.0)
    c.paint(c.ellipse(cx, 19.2, 0.6, 1.0), 0.5)
    c.shine(glass, 0.5, 2.0)
    for x0, x1 in ((-5.6, -6.6), (5.6, 6.6)):
        c.add(c.line([(cx + x0, 11.5), (cx + x1, 23)], 0.9), 0.85, z=0.6, round_=0.4)
    c.add(c.rect(cx - 7.2, 23, cx + 7.2, 25, r=0.5), 0.9, round_=0.8)
    c.add(c.poly([(cx - 5, 25), (cx + 5, 25), (cx + 3.5, 26.5), (cx - 3.5, 26.5)]), 0.8, round_=0.6)


def m_crt(c: Canvas):
    cx = c.cols / 2
    c.add(c.rect(1, 1, c.cols - 1, 22, r=3), 0.85, round_=1.6)                 # case
    scr = c.rect(4, 3.2, c.cols - 4, 19, r=2.4)
    c.cut(scr)
    c.write(c.cols - 9, 4.5, ".")
    c.write(c.cols - 8, 4.5, "'")
    c.write(c.cols - 7, 6.5, ".")
    c.write(7, 6, "READY.")
    c.write(7, 10, "RUN")
    c.write(7, 14, "> _")
    c.add(c.ellipse(c.cols - 3.2, 20.3, 0.7, 0.7), 1.0, z=1.0, round_=0.5)   # knob
    c.add(c.poly([(cx - 5, 22), (cx + 5, 22), (cx + 7, 25.5), (cx - 7, 25.5)]), 0.8, round_=1.2)
    c.add(c.rect(cx - 11, 25.5, cx + 11, 27, r=0.6), 0.7, round_=0.6)


def m_terminal(c: Canvas):
    c.add(c.rect(1, 2, c.cols - 1, 25, r=1.5), 0.85, round_=1.0)
    c.add(c.rect(1, 2, c.cols - 1, 5.2, r=1.5), 1.0, z=0.4, round_=0.6)       # title bar
    for i in range(3):
        c.add(c.ellipse(4 + i * 2.8, 3.6, 0.8, 0.8), 0.3, z=0.8, round_=0.5)
    body = c.rect(2.6, 6.4, c.cols - 2.6, 23.6, r=0.6)
    c.cut(body)
    c.write(5, 8, "~ swayforge")
    c.write(5, 12, "forging ....... ok")
    c.write(5, 16, "theme ......... ok")
    c.write(5, 20, "> _")


def m_gamepad(c: Canvas):
    cx = c.cols / 2
    body = c.rect(5, 5, c.cols - 5, 16, r=5) | c.ellipse(7.5, 16.5, 6, 9.5) | c.ellipse(c.cols - 7.5, 16.5, 6, 9.5)
    c.add(body, 0.8, round_=4.5)
    c.add(c.rect(6.0, 10.0, 13.0, 12.4, r=0.4), 0.35, z=4.0, round_=0.4)        # d-pad (dark)
    c.add(c.rect(8.3, 7.7, 10.7, 14.7, r=0.4), 0.35, z=4.0, round_=0.4)
    for dx, dy in ((0, -2.6), (2.8, 0), (0, 2.6), (-2.8, 0)):
        c.add(c.ellipse(c.cols - 9.5 + dx, 11.2 + dy, 1.2, 1.2), 1.0, z=4.6, round_=1.0)
    for x in (cx - 5, cx + 5):
        c.add(c.ellipse(x, 17, 2.8, 2.8), 0.3, z=3.0, round_=0.4)
        c.add(c.ellipse(x, 17, 2.0, 2.0), 1.0, z=3.6, round_=1.8)
    c.add(c.rect(cx - 2.6, 9.6, cx - 0.8, 10.6, r=0.4), 0.4, z=4.2, round_=0.3)
    c.add(c.rect(cx + 0.8, 9.6, cx + 2.6, 10.6, r=0.4), 0.4, z=4.2, round_=0.3)


def m_cyberdeck(c: Canvas):
    # tilted screen on a hinged keyboard slab
    c.add(c.poly([(6, 1), (c.cols - 6, 1), (c.cols - 4, 13), (4, 13)]), 0.85, round_=1.0)
    scr = c.poly([(8, 2.6), (c.cols - 8, 2.6), (c.cols - 6.5, 11.6), (6.5, 11.6)])
    c.cut(scr)
    for i, y in enumerate((3.6, 5.6, 7.6, 9.6)):
        w = (14, 22, 9, 18)[i]
        c.paint(c.rect(9 + i * 0.3, y, 9 + i * 0.3 + w, y + 0.8), (0.9, 0.6, 1.0, 0.7)[i])
    c.shine(scr, 0.25, 1.5)
    slab = c.poly([(3, 14), (c.cols - 3, 14), (c.cols, 26), (0, 26)])
    c.add(slab, 0.8, round_=1.2)
    for r in range(4):
        y = 15.4 + r * 2.5
        inset = 3.3 - r * 0.75
        n = 12
        x0, x1 = inset + 1.2, c.cols - inset - 1.2
        step = (x1 - x0) / n
        for k in range(n):
            if r == 3 and 3 <= k <= 8:
                continue
            c.add(c.rect(x0 + k * step + 0.25, y, x0 + (k + 1) * step - 0.25, y + 1.6, r=0.3), 1.0, z=1.3, round_=0.45)
    c.add(c.rect(x0 + 3 * step + 0.25, 15.4 + 7.5, x0 + 9 * step - 0.25, 15.4 + 9.1, r=0.3), 1.0, z=1.3, round_=0.45)


def m_wired(c: Canvas):
    # utility pole with crossbars; the wires run off to the right as plain line characters
    px = 10
    c.add(c.rect(px - 1.5, 1, px + 1.5, 29), 0.8, round_=1.4)
    tops = []
    for y, w in ((4, 8), (10, 6.5)):
        c.add(c.rect(px - w, y, px + w, y + 1.6), 0.9, z=1.5, round_=0.7)
        for x in (px - w + 1, px - w / 2, px + w / 2, px + w - 1):
            c.add(c.ellipse(x, y - 0.7, 0.7, 1.0), 1.0, z=2.2, round_=0.6)
            tops.append((x, y - 1.4))
    c.add(c.rect(px - 2.6, 15, px + 2.6, 20, r=0.8), 0.95, z=1.6, round_=1.2)  # transformer
    for i, (x, y) in enumerate(tops):
        if x < px:
            continue
        sag = 3 + i % 3
        for xx in range(int(x) + 1, c.cols):
            t = (xx - x) / (c.cols - x)
            yy = (y + t * 5 + math.sin(t * math.pi) * sag) / 2          # in character rows
            r, sub = int(yy), yy - int(yy)
            c.chars[(r, xx)] = "'" if sub < 0.25 else "-" if sub < 0.6 else "_"
    c.write(c.cols - 13, 26, "connected_")


def m_rosewindow(c: Canvas):
    """Gothic rose window: stone ring, 12 lancet petals, foils, a hub – under a pointed arch."""
    cx, cy, R = c.cols / 2, 16, 13
    # pointed arch frame around it
    arch = c.mask(lambda d, k: (d.rectangle([(cx - 17) * k.u, 15 * k.u, (cx + 17) * k.u, 31 * k.u], fill=255),
                                d.pieslice([(cx - 17 - 17) * k.u, (15 - 17) * k.u, (cx + 17) * k.u, (15 + 17) * k.u],
                                           270, 360, fill=255),
                                d.pieslice([(cx - 17) * k.u, (15 - 17) * k.u, (cx + 17 + 17) * k.u, (15 + 17) * k.u],
                                           180, 270, fill=255)))
    inner = c.mask(lambda d, k: (d.rectangle([(cx - 15) * k.u, 15 * k.u, (cx + 15) * k.u, 31 * k.u], fill=255),
                                 d.pieslice([(cx - 15 - 15) * k.u, (15 - 15) * k.u, (cx + 15) * k.u, (15 + 15) * k.u],
                                            270, 360, fill=255),
                                 d.pieslice([(cx - 15) * k.u, (15 - 15) * k.u, (cx + 15 + 15) * k.u, (15 + 15) * k.u],
                                            180, 270, fill=255)))
    c.add(arch & ~inner, 0.85, round_=0.9)
    c.cut(inner)                                                   # open sky behind the tracery
    ring = c.ellipse(cx, cy, R, R) & ~c.ellipse(cx, cy, R - 1.6, R - 1.6)
    c.add(ring, 1.0, z=1.0, round_=0.9)
    for i in range(12):
        a = math.tau * i / 12
        x1, y1 = cx + math.cos(a) * 3.2, cy + math.sin(a) * 3.2
        x2, y2 = cx + math.cos(a) * (R - 1.4), cy + math.sin(a) * (R - 1.4)
        c.add(c.line([(x1, y1), (x2, y2)], 0.55), 0.9, z=0.8, round_=0.3)          # tracery spokes
        mx, my = cx + math.cos(a + math.tau / 24) * (R - 3.6), cy + math.sin(a + math.tau / 24) * (R - 3.6)
        c.add(c.ellipse(mx, my, 1.25, 1.25) & ~c.ellipse(mx, my, 0.6, 0.6), 1.0, z=0.9, round_=0.4)
        gx, gy = cx + math.cos(a + math.tau / 24) * (R - 7.5), cy + math.sin(a + math.tau / 24) * (R - 7.5)
        c.paint(c.ellipse(gx, gy, 1.5, 1.5), 0.55 if i % 2 else 0.35)               # stained glass
    hub = c.ellipse(cx, cy, 3.4, 3.4)
    c.add(hub & ~c.ellipse(cx, cy, 1.6, 1.6), 1.0, z=1.2, round_=0.8)
    c.paint(c.ellipse(cx, cy, 1.4, 1.4), 1.0)
    c.shine(c.ellipse(cx, cy, 1.4, 1.4), 0.4, 1.5)


MOTIFS = {   # name: (draw, design cols, design rows, output scale)
    "forge": (m_forge, 40, 15, 1.0), "anvil": (m_anvil, 40, 14, 1.0), "bat": (m_bat, 40, 12, 1.0),
    "moon": (m_moon, 38, 15, 1.05), "rose": (m_rose, 30, 20, 1.2), "skull": (m_skull, 34, 14, 1.15),
    "lantern": (m_lantern, 26, 14, 1.4), "crt": (m_crt, 38, 14, 1.0), "terminal": (m_terminal, 38, 13, 1.0),
    "gamepad": (m_gamepad, 40, 14, 1.05), "rosewindow": (m_rosewindow, 36, 16, 1.1), "cyberdeck": (m_cyberdeck, 40, 13, 1.0), "wired": (m_wired, 40, 15, 1.0),
}


# ── Banner font ──────────────────────────────────────────────────────
# Letters need crisp edges to stay readable, so they use a short ramp: soft edge
# characters by pixel coverage, and a solid core that gets lighter towards the bottom.
EDGE = " .:-=+*"
CORE = "@@%%##**"
BANNER_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/!?>#+=[]()<@ "
BANNER_ROWS = (8, 7, 6, 5, 4)


def glyph_rows(ch: str, rows: int, font: str = "DejaVuSansCondensed-Bold") -> list[str]:
    """Capital letters scaled so the cap height fills all rows."""
    ss = 8
    cols = rows * 2
    w, h = cols * ss, rows * ss * 2
    probe = ImageFont.truetype(_font(font), 100)
    cap = probe.getbbox("H", anchor="ls")
    f = ImageFont.truetype(_font(font), int(round(h * 100 / (cap[3] - cap[1]))))
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((ss, h), ch, font=f, fill=255, anchor="ls")
    cov = (np.array(img) / 255).reshape(rows, ss * 2, cols, ss).mean(axis=(1, 3))
    grid = []
    for r in range(rows):
        row = ""
        for col in range(cols):
            v = cov[r, col]
            if v < 0.1:
                row += " "
            elif v < 0.8:
                row += EDGE[1 + min(5, int(v / 0.8 * 6))]
            else:
                row += CORE[int(r / rows * len(CORE))]
        grid.append(row)
    used = [i for i in range(cols) if any(g[i] != " " for g in grid)]
    if not used:
        return [" " * max(2, rows // 2)] * rows
    return [g[used[0]:used[-1] + 1] for g in grid]


def banner_font() -> dict:
    return {str(rows): {ch: glyph_rows(ch, rows) for ch in BANNER_CHARS} for rows in BANNER_ROWS}


def preview(name: str, lines: list[str], path: Path):
    f = ImageFont.truetype(_font("DejaVuSansMono"), 14)
    w = max(map(len, lines)) * 9 + 20
    img = Image.new("RGB", (w, len(lines) * 17 + 20), (10, 14, 10))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((10, 10 + i * 17), l, font=f, fill=(185, 220, 178))
    img.save(path / f"{name}.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pv = Path("/tmp/art-preview") if "--preview" in sys.argv else None
    if pv:
        pv.mkdir(parents=True, exist_ok=True)
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    for name, (fn, cols, rows, k) in MOTIFS.items():
        if only and name not in only:
            continue
        c = Canvas(cols, rows, k)
        fn(c)
        lines = c.to_text()
        (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n")
        if pv:
            preview(name, lines, pv)
        print(f"{name:10} {max(map(len, lines))}×{len(lines)}")
    if not only:
        font = banner_font()
        (OUT / "banner.json").write_text(json.dumps(font, ensure_ascii=False, separators=(",", ":")) + "\n")
        if pv:
            for rows in ("7", "5"):
                g = [font[rows][ch] for ch in "SWAYFORGE"]
                lines = [" ".join(x[i] for x in g) for i in range(int(rows))]
                preview(f"banner{rows}", lines, pv)


if __name__ == "__main__":
    main()
