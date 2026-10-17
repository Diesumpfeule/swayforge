"""Wallpapers drawn in code (too detailed for a hand-written template).

cathedral(): a gothic nave – rose window with stone tracery and stained glass, lancet
windows, ribbed columns, an ornamental frame, a wrought-iron fence and candles, over
faint pinstripes. Every colour comes from the theme. Original artwork of swayforge.
"""
from __future__ import annotations

import math

W, H = 3840, 2160


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def arch_h(w: float, k: float = 0.75) -> float:
    """Height of a pointed arch of width w whose two arcs have radius k·w (k=1: equilateral)."""
    r = k * w
    return math.sqrt(r * r - (r - w / 2) ** 2)


def _arch(x: float, y_base: float, w: float, top: float, k: float = 0.75) -> str:
    """Pointed arch with its apex at `top`, sides running down to y_base."""
    l, r, rad = x - w / 2, x + w / 2, k * w
    spring = top + arch_h(w, k)
    return (f"M{_f(l)} {_f(y_base)} V{_f(spring)} A{_f(rad)} {_f(rad)} 0 0 1 {_f(x)} {_f(top)} "
            f"A{_f(rad)} {_f(rad)} 0 0 1 {_f(r)} {_f(spring)} V{_f(y_base)}")


def _petal(cx: float, cy: float, r0: float, r1: float, w: float, angle: float) -> str:
    """One lancet of the rose window, pointing outwards at `angle` degrees."""
    spring = cy - r1 + w * 0.9
    d = (f"M{_f(cx - w / 2)} {_f(cy - r0)} V{_f(spring)} "
         f"A{_f(w)} {_f(w)} 0 0 1 {_f(cx)} {_f(cy - r1)} A{_f(w)} {_f(w)} 0 0 1 {_f(cx + w / 2)} {_f(spring)} "
         f"V{_f(cy - r0)} Z")
    return f'<path d="{d}" transform="rotate({_f(angle)} {_f(cx)} {_f(cy)})"/>'


def _foil(cx: float, cy: float, r: float, n: int, rr: float) -> str:
    """n-foil (trefoil, quatrefoil …): n circles on a ring."""
    out = []
    for i in range(n):
        a = math.tau * i / n - math.pi / 2
        out.append(f'<circle cx="{_f(cx + math.cos(a) * r)}" cy="{_f(cy + math.sin(a) * r)}" r="{_f(rr)}"/>')
    return "".join(out)


def _lancet(x: float, base: float, w: float, top: float) -> list[str]:
    """Tall lancet window: two lights with a quatrefoil above, glass + tracery."""
    spring = top + arch_h(w)
    outer = _arch(x, base, w, top)
    glass, stone = [], []
    glass.append(f'<path d="{outer} Z" fill="url(#glassV)"/>')
    stone.append(f'<path d="{outer}" class="st"/>')
    lw = w * 0.38
    for dx in (-w * 0.22, w * 0.22):
        sub = _arch(x + dx, base - 40, lw, spring + w * 0.42)
        stone.append(f'<path d="{sub}" class="st2"/>')
    stone.append(f'<g class="st2">{_foil(x, spring + w * 0.12, w * 0.11, 4, w * 0.085)}</g>')
    # leading of the stained glass
    for yy in range(int(spring + w * 0.9), int(base - 60), 70):
        stone.append(f'<path d="M{_f(x - w * 0.41)} {yy} H{_f(x - w * 0.03)} M{_f(x + w * 0.03)} {yy} '
                     f'H{_f(x + w * 0.41)}" class="lead"/>')
    return glass + stone


def cathedral(c: dict) -> str:
    cx, cy, R = W / 2, 880, 500
    acc, acc2, text, gold = c["accent"], c["accent2"], c["text"], c["yellow"]
    p: list[str] = []
    p.append(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="nave" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{c['crust']}"/><stop offset="0.55" stop-color="{c['base']}"/>
    <stop offset="1" stop-color="{c['crust']}"/>
  </linearGradient>
  <radialGradient id="halo" cx="0.5" cy="0.41" r="0.42">
    <stop offset="0" stop-color="{acc}" stop-opacity="0.22"/>
    <stop offset="0.5" stop-color="{acc}" stop-opacity="0.06"/>
    <stop offset="1" stop-color="{acc}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="glass" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{gold}" stop-opacity="0.35"/>
    <stop offset="0.35" stop-color="{acc}" stop-opacity="0.32"/>
    <stop offset="1" stop-color="{acc}" stop-opacity="0.10"/>
  </radialGradient>
  <linearGradient id="glassV" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{acc}" stop-opacity="0.26"/>
    <stop offset="0.6" stop-color="{acc2}" stop-opacity="0.14"/>
    <stop offset="1" stop-color="{acc}" stop-opacity="0.04"/>
  </linearGradient>
  <linearGradient id="shaft" x1="0" y1="0" x2="0.25" y2="1">
    <stop offset="0" stop-color="{text}" stop-opacity="0.06"/>
    <stop offset="1" stop-color="{text}" stop-opacity="0"/>
  </linearGradient>
  <radialGradient id="flame" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{gold}" stop-opacity="0.55"/>
    <stop offset="0.3" stop-color="{gold}" stop-opacity="0.12"/>
    <stop offset="1" stop-color="{gold}" stop-opacity="0"/>
  </radialGradient>
  <pattern id="stripes" width="28" height="28" patternUnits="userSpaceOnUse">
    <rect width="2" height="28" fill="{text}" fill-opacity="0.028"/>
  </pattern>
  <pattern id="grain" width="9" height="9" patternUnits="userSpaceOnUse">
    <circle cx="2" cy="3" r="0.8" fill="{text}" fill-opacity="0.035"/>
    <circle cx="7" cy="7" r="0.7" fill="#000" fill-opacity="0.3"/>
  </pattern>
  <style>
    .st {{ fill: none; stroke: {text}; stroke-opacity: 0.42; stroke-width: 6; }}
    .st2 {{ fill: none; stroke: {text}; stroke-opacity: 0.30; stroke-width: 3.5; }}
    .lead {{ fill: none; stroke: {c['crust']}; stroke-opacity: 0.55; stroke-width: 2.5; }}
    .rib {{ fill: none; stroke: {text}; stroke-opacity: 0.12; stroke-width: 3; }}
    .iron {{ fill: {c['crust']}; stroke: {c['overlay']}; stroke-opacity: 0.5; stroke-width: 2; }}
  </style>
</defs>
<rect width="{W}" height="{H}" fill="url(#nave)"/>
<rect width="{W}" height="{H}" fill="url(#stripes)"/>
<rect width="{W}" height="{H}" fill="url(#halo)"/>''')

    # light falling through the windows
    for x0, wdt in ((cx - 260, 520), (330, 160), (cx - 690, 160), (cx + 690, 160), (W - 330, 160)):
        p.append(f'<path d="M{_f(x0)} 300 h{_f(wdt)} l{_f(wdt * 1.3)} {H - 300} h{_f(-wdt * 2.2)} Z" fill="url(#shaft)"/>')

    # the great arch of the nave (stepped mouldings) + ribbed columns
    for i, (wd, cls) in enumerate(((2600, "st"), (2520, "st2"), (2440, "st2"))):
        p.append(f'<path d="{_arch(cx, H, wd, 150 + i * 34, 0.62)}" class="{cls}"/>')
    spring = 150 + arch_h(2600, 0.62)
    for x in (cx - 1300, cx + 1300):
        for k in range(-3, 4):
            p.append(f'<path d="M{_f(x + k * 14)} {_f(spring)} V{H}" class="rib"/>')
        p.append(f'<rect x="{_f(x - 70)}" y="{_f(spring - 20)}" width="140" height="40" class="st2"/>')   # capital
        p.append(f'<g class="st2">{_foil(x, spring - 60, 34, 3, 22)}</g>')

    # lancet windows, two on each side
    for x in (330, cx - 690, cx + 690, W - 330):
        p += _lancet(x, 1700, 230, 420 if abs(x - cx) > 1000 else 660)

    # rose window: glass, 16 lancet petals, foils, rings
    p.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{R}" fill="url(#glass)"/>')
    p.append('<g class="st2" fill="none">')
    for i in range(16):
        p.append(_petal(cx, cy, 150, R - 70, 118, i * 22.5))
    p.append("</g>")
    p.append('<g fill="{0}" fill-opacity="0.10">'.format(c["accent2"]))
    for i in range(16):
        if i % 2:
            p.append(_petal(cx, cy, 150, R - 70, 118, i * 22.5))
    p.append("</g>")
    p.append(f'<g class="st2">{_foil(cx, cy, R - 34, 32, 26)}</g>')               # ring of 32 roundels
    p.append(f'<g class="st2">{_foil(cx, cy, R - 120, 16, 30)}</g>')              # trefoil tips
    p.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{R}" class="st"/>')
    p.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{R + 30}" class="st2"/>')
    p.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{R - 70}" class="st2"/>')
    p.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="150" class="st"/>')
    p.append(f'<g class="st2">{_foil(cx, cy, 70, 6, 52)}</g>')                    # hexafoil hub
    p.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="36" fill="{gold}" fill-opacity="0.25" class="st2"/>')
    # spokes
    for i in range(16):
        a = math.tau * i / 16 + math.tau / 32
        p.append(f'<path d="M{_f(cx + math.cos(a) * 150)} {_f(cy + math.sin(a) * 150)} '
                 f'L{_f(cx + math.cos(a) * (R - 70))} {_f(cy + math.sin(a) * (R - 70))}" class="lead"/>')

    # candles on iron stands, both sides
    for x in (cx - 560, cx - 440, cx + 440, cx + 560):
        h = 140 if abs(x - cx) > 500 else 100
        top = 1790 - h
        p.append(f'<circle cx="{_f(x)}" cy="{_f(top - 26)}" r="120" fill="url(#flame)"/>')
        p.append(f'<rect x="{_f(x - 14)}" y="{_f(top)}" width="28" height="{h}" rx="4" fill="{text}" fill-opacity="0.55"/>')
        p.append(f'<path d="M{_f(x)} {_f(top - 48)} q14 22 0 40 q-14 -18 0 -40 Z" fill="{gold}" fill-opacity="0.9"/>')
        p.append(f'<path d="M{_f(x - 60)} 1790 h120 M{_f(x)} 1790 V1880 M{_f(x - 40)} 1880 h80" class="st2"/>')

    # wrought-iron fence with spear finials and scrolls
    p.append(f'<rect x="0" y="1930" width="{W}" height="12" class="iron"/>')
    p.append(f'<rect x="0" y="2080" width="{W}" height="12" class="iron"/>')
    for x in range(40, W, 64):
        p.append(f'<rect x="{x - 4}" y="1880" width="8" height="280" class="iron"/>')
        p.append(f'<path d="M{x} 1840 l16 40 h-32 Z" class="iron"/>')
        if (x // 64) % 2:
            p.append(f'<path d="M{x - 30} 2010 q30 -50 30 0 q0 50 30 0" fill="none" stroke="{c["overlay"]}" '
                     f'stroke-opacity="0.55" stroke-width="3"/>')

    # ornamental frame: double rule, corner rosettes, fleur-ish finials on the sides
    for inset, cls in ((56, "st2"), (76, "st2")):
        p.append(f'<rect x="{inset}" y="{inset}" width="{W - 2 * inset}" height="{H - 2 * inset}" class="{cls}"/>')
    for x, y in ((66, 66), (W - 66, 66), (66, H - 66), (W - 66, H - 66)):
        p.append(f'<g class="st2">{_foil(x, y, 26, 4, 18)}</g><circle cx="{x}" cy="{y}" r="9" fill="{acc}" fill-opacity="0.7"/>')
    for x in range(400, W - 300, 520):
        p.append(f'<g class="st2">{_foil(x, 66, 14, 3, 10)}</g>')
        p.append(f'<g class="st2">{_foil(x, H - 66, 14, 3, 10)}</g>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#grain)"/>')
    p.append("</svg>\n")
    return "\n".join(p)


# ── plague: ASCII-art wallpaper ──────────────────────────────────────
COLS, ROWS, CW, LH, FS = 212, 62, 18.06, 34.5, 30
_MIRROR = str.maketrans("/\\()[]{}<>", "\\/)(][}{><")


def _piece(name: str) -> list[str]:
    from . import ascii as asc
    return asc.art(name)


class _Grid:
    def __init__(self) -> None:
        self.g = [[(" ", "")] * COLS for _ in range(ROWS)]

    def put(self, x: int, y: int, ch: str, key: str) -> None:
        if 0 <= y < ROWS and 0 <= x < COLS and ch != " ":
            self.g[y][x] = (ch, key)

    def text(self, x: int, y: int, t: str, key: str) -> None:
        for i, ch in enumerate(t):
            self.put(x + i, y, ch, key)

    def blit(self, lines: list[str], x: int, y: int, key: str, mirror: bool = False,
             special: dict | None = None) -> None:
        w = max(len(l) for l in lines)
        for j, l in enumerate(lines):
            l = l.ljust(w)
            if mirror:
                l = l[::-1].translate(_MIRROR)
            for i, ch in enumerate(l):
                self.put(x + i, y + j, ch, (special or {}).get(ch, key))


def plague(c: dict) -> str:
    """Dark ASCII scene: a plague doctor under a gothic arch, skeletons fetching the dead."""
    import random
    rnd = random.Random(1348)
    g = _Grid()
    cx = COLS // 2
    # dust and stars outside the arch, drifting miasma near the floor
    for _ in range(420):
        g.put(rnd.randrange(2, COLS - 2), rnd.randrange(2, 46), rnd.choice(".·,'`:"), "dim")
    for _ in range(700):
        g.put(rnd.randrange(2, COLS - 2), rnd.randrange(46, ROWS - 2), rnd.choice("░░▒~≈-"), "mist")
    # pointed arch (double line) with spring at row 34
    spring, hw = 34, 31
    for off, key in ((0, "stone"), (3, "dim")):
        h = hw - off
        for r in range(2 + off, ROWS - 3):
            if r >= spring:
                lx, rx, chl, chr_ = cx - h, cx + h, "║", "║"
            else:
                dy = (spring - r) * LH
                R = 2 * h * CW
                d = R * R - dy * dy
                if d < 0:
                    continue
                lx = round(cx + h - __import__("math").sqrt(d) / CW)
                if lx > cx:
                    continue
                rx = 2 * cx - lx
                chl, chr_ = ("/", "\\") if r < spring - 4 else ("║", "║")
            g.put(lx, r, chl, key)
            g.put(rx, r, chr_, key)
    # rose window in the apex
    import math
    rcx, rcy = cx, 14
    for a in range(0, 360, 4):
        for rad, ch in ((6.2, "o"), (3.2, "·")):
            g.put(round(rcx + math.cos(math.radians(a)) * rad * LH / CW), round(rcy + math.sin(math.radians(a)) * rad), ch, "glass")
    for a in range(0, 360, 45):
        for t in range(1, 6):
            g.put(round(rcx + math.cos(math.radians(a)) * t * LH / CW), round(rcy + math.sin(math.radians(a)) * t), "+", "glass")
    g.put(rcx, rcy, "✠", "blood")
    # the cast
    doc = _piece("plague_doctor")
    g.blit(doc, cx - max(map(len, doc)) // 2, 22, "doc", special={"@": "blood"})
    sk = _piece("plague_skeleton")
    g.blit(sk, 14, 34, "bone")
    g.blit(sk, COLS - 14 - max(map(len, sk)), 34, "bone", mirror=True)
    g.blit(_piece("plague_cart"), 10, 37, "bone", special={"x": "blood"})
    for x, y, m in ((26, 6, False), (166, 8, True), (50, 14, True), (150, 4, False)):
        g.blit(_piece("plague_bat"), x, y, "dim", mirror=m)
    for x, y in ((cx - 30, 3), (cx + 22, 5), (cx + 32, 19)):
        g.blit(_piece("plague_crow"), x, y, "doc")
    # candles
    for x in (cx - 40, cx - 35, cx + 36, cx + 41):
        h = 3 + (x % 3)
        for j in range(h):
            g.put(x, ROWS - 4 - j, "|", "bone")
        g.put(x, ROWS - 4 - h, ")", "gold")
        g.put(x, ROWS - 5 - h, ",", "gold")
    # frame and lettering
    orn = "✠ ❦ † ❦ " * (COLS // 8 + 1)
    g.text(0, 0, orn[:COLS], "blood")
    g.text(0, ROWS - 1, orn[:COLS], "blood")
    for r in range(1, ROWS - 1):
        g.put(0, r, "║", "blood")
        g.put(COLS - 1, r, "║", "blood")
        if r % 6 == 0:
            g.put(0, r, "†", "gold")
            g.put(COLS - 1, r, "†", "gold")
    for t, y, key in (("M E M E N T O   M O R I", 2, "blood"),
                      ("A N N O   D O M I N I   M C C C X L V I I I", ROWS - 3, "stone"),
                      ("~ ~ ~  ex pestilentia libera nos  ~ ~ ~", ROWS - 2, "mist")):
        g.text(cx - len(t) // 2, y, t, key)
    col = {"dim": (c["overlay"], 0.55), "stone": (c["subtext"], 0.7), "bone": (c["text"], 0.78),
           "doc": (c["subtext"], 0.95), "blood": (c["accent"], 0.95), "gold": (c["yellow"], 0.95),
           "mist": (c["accent2"], 0.5), "glass": (c["accent"], 0.55)}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           '<defs><radialGradient id="v" cx="0.5" cy="0.45" r="0.75"><stop offset="0.35" stop-color="#000" stop-opacity="0"/>'
           '<stop offset="1" stop-color="#000" stop-opacity="0.92"/></radialGradient>',
           f'<radialGradient id="glow" cx="0.5" cy="0.55" r="0.4"><stop offset="0" stop-color="{c["accent"]}" stop-opacity="0.22"/>'
           '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>',
           f'<rect width="{W}" height="{H}" fill="{c["crust"]}"/>',
           f'<rect width="{W}" height="{H}" fill="url(#glow)"/>',
           f'<g font-family="DejaVu Sans Mono, monospace" font-size="{FS}" xml:space="preserve">']
    esc = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
    for r, row in enumerate(g.g):
        y = 30 + r * LH
        spans, cur, buf = [], None, ""
        for i, (ch, key) in enumerate(row):
            if key != cur and buf:
                spans.append((cur, buf)); buf = ""
            cur = key
            buf += esc.get(ch, ch)
        spans.append((cur, buf))
        x = 0
        for key, txt in spans:
            n = len(txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
            if key:
                colr, op = col[key]
                out.append(f'<text x="{_f(x * CW)}" y="{_f(y)}" fill="{colr}" fill-opacity="{op}">{txt}</text>')
            x += n
    out.append("</g>")
    out.append(f'<rect width="{W}" height="{H}" fill="url(#v)"/>')
    out.append("</svg>\n")
    return "\n".join(out)


ART = {"cathedral": cathedral, "plague": plague}
