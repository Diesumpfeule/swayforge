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


# ── plague: shaded ASCII-art wallpaper ───────────────────────────────
def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def plague(c: dict) -> str:
    """The black-death scene (rose window, plague doctor, skeletons) as dense ASCII shading.

    data/art/plague_scene.txt is generated by scripts/make_plague_art.py from a greyscale
    drawing; the glyph's ink density carries the brightness, the theme supplies the colours.
    """
    from . import paths
    head, *lines = (paths.DATA / "wallart/plague_scene.txt").read_text().split("\n")
    asc_ramp = head[4:]
    lines = lines[:-1] if lines and not lines[-1] else lines
    cols = max(len(l) for l in lines)
    ramp = asc_ramp
    n = len(ramp)
    bins = [(range(1, n // 4), _mix(c["crust"], c["accent"], 0.55)), (range(n // 4, n // 2), c["accent"]),
            (range(n // 2, n * 3 // 4), _mix(c["accent"], c["text"], 0.5)), (range(n * 3 // 4, n), c["text"])]
    lh = H / len(lines)
    fs = round(W / cols / 0.6, 2)
    esc = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" fill="{c["crust"]}"/>',
           f'<g font-family="JetBrainsMono Nerd Font, JetBrains Mono, DejaVu Sans Mono, monospace" '
           f'font-size="{fs}" xml:space="preserve">']
    for idx, color in bins:
        out.append(f'<g fill="{color}"' + (' font-weight="700"' if idx.start >= n // 2 else "") + ">")
        for r, line in enumerate(lines):
            row = "".join(ch if ramp.find(ch) in idx else " " for ch in line.ljust(cols))
            if row.strip():
                out.append(f'<text x="0" y="{_f((r + 0.8) * lh)}" textLength="{W}" lengthAdjust="spacing">'
                           f'{"".join(esc.get(ch, ch) for ch in row)}</text>')
        out.append("</g>")
    out += ["</g>", "</svg>", ""]
    return "\n".join(out)


ART = {"cathedral": cathedral, "plague": plague}
