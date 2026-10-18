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


# ── plague: a medieval painting (danse macabre during the black death) ──
def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _town(rnd, ink: str, glow: str) -> str:
    """Silhouette of a burning medieval town: houses, spires, towers, flames."""
    out, x = [], -20
    while x < 1940:
        w = rnd.randrange(50, 120)
        h = rnd.randrange(50, 150)
        y = 760 - h
        kind = rnd.choice(("gable", "gable", "tower", "spire"))
        if kind == "gable":
            out.append(f'<path d="M{x} 770 V{y} L{x + w / 2:.0f} {y - 36} L{x + w} {y} V770z"/>')
        elif kind == "tower":
            out.append(f'<path d="M{x} 770 V{y - 40} h{w * .7:.0f} V770z M{x - 6} {y - 40} h{w * .7 + 12:.0f} v-14 h-10 v8 h-12 v-8 h-12 v8 h-12 v-8 h-10v8 h-6z"/>')
        else:
            out.append(f'<path d="M{x} 770 V{y} h{w * .5:.0f} V770z M{x - 4} {y} L{x + w * .25:.0f} {y - 150 - h // 2} L{x + w * .5 + 4:.0f} {y}z"/>')
        if rnd.random() < 0.45:
            fx = x + w * 0.3
            out.append(f'<g class="fl"><path d="M{fx:.0f} {y} q-14 -34 2 -64 q6 22 20 28 q6 -16 -2 -34 q30 26 14 70z" fill="{glow}"/></g>')
        for wy in range(y + 24, 740, 38):
            if rnd.random() < 0.35:
                out.append(f'<rect x="{x + 12}" y="{wy}" width="9" height="14" fill="{glow}" class="win"/>')
        x += w - rnd.randrange(0, 18)
    return "".join(out)


def _scroll(x0: float, x1: float, y: float, col: str, up: bool = True) -> str:
    """Running vine scroll with leaves for the illuminated border."""
    d, x, s = [], x0, -1 if up else 1
    while x < x1:
        d.append(f"M{x:.0f} {y} q18 {s * 26} 36 0 q18 {-s * 26} 36 0")
        d.append(f"M{x + 36:.0f} {y} q6 {s * 18} 22 {s * 16} q-6 {-s * 14} -22 {-s * 16}")
        x += 72
    return f'<path d="{" ".join(d)}" fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round"/>'


def plague(c: dict) -> str:
    """Medieval painting: a plague doctor under a golden rose-window halo, skeletons leading the
    dance, a burning town behind, an illuminated border in gold leaf. Original artwork; colours
    come from the theme (blood, bone, gold, verdigris)."""
    import random
    rnd = random.Random(1348)
    ink, blood, gold = c["crust"], c["accent"], c["yellow"]
    bone, green = c["text"], c["accent2"]
    sky_top = _mix(ink, "#000000", 0.4)
    sky_mid = _mix(ink, blood, 0.35)
    horizon = _mix(c["orange"], blood, 0.45)
    cloak = _mix(ink, "#000000", 0.5)
    gold_d = _mix(gold, ink, 0.45)
    bone_d = _mix(bone, ink, 0.45)
    crack = "".join(
        f'<path d="M{rnd.randrange(60, 1860)} {rnd.randrange(60, 1020)} l{rnd.randrange(-60, 60)} {rnd.randrange(10, 50)} '
        f'l{rnd.randrange(-50, 50)} {rnd.randrange(10, 50)} l{rnd.randrange(-40, 40)} {rnd.randrange(10, 40)}"/>'
        for _ in range(90))
    stars = "".join(f'<circle cx="{rnd.randrange(110, 1810)}" cy="{rnd.randrange(110, 520)}" r="{rnd.choice((1.6, 2.2, 3))}"/>'
                    for _ in range(90))
    rays = "".join(f'<path d="M830 430 L{830 + 620 * __import__("math").cos(a / 24 * 6.2832):.0f} '
                   f'{430 + 620 * __import__("math").sin(a / 24 * 6.2832):.0f}"/>' for a in range(24))
    bones = lambda sw: f'stroke="{bone}" stroke-width="{sw}" fill="none" stroke-linecap="round"'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 1920 1080">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky_top}"/><stop offset="0.55" stop-color="{sky_mid}"/><stop offset="0.78" stop-color="{horizon}"/><stop offset="1" stop-color="{_mix(horizon, ink, .4)}"/></linearGradient>
  <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{gold}" stop-opacity="0.55"/><stop offset="1" stop-color="{gold}" stop-opacity="0"/></radialGradient>
  <radialGradient id="fire" cx="0.5" cy="1" r="0.8"><stop offset="0" stop-color="{c["orange"]}" stop-opacity="0.8"/><stop offset="1" stop-color="{c["orange"]}" stop-opacity="0"/></radialGradient>
  <linearGradient id="goldleaf" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{_mix(gold, "#ffffff", .35)}"/><stop offset="0.5" stop-color="{gold}"/><stop offset="1" stop-color="{gold_d}"/></linearGradient>
  <linearGradient id="coat" x1="0" x2="1"><stop offset="0" stop-color="{_mix(cloak, gold, .22)}"/><stop offset="0.3" stop-color="{cloak}"/><stop offset="1" stop-color="{_mix(cloak, "#000000", .6)}"/></linearGradient>
  <radialGradient id="vig" cx="0.5" cy="0.5" r="0.75"><stop offset="0.5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.75"/></radialGradient>
  <filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="4"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.55 -0.12"/></filter>
  <filter id="paint" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.012 0.02" numOctaves="4" seed="9"/><feColorMatrix values="0 0 0 0 0.05  0 0 0 0 0.03  0 0 0 0 0.02  0 0 0 0.9 -0.28"/></filter>
  <filter id="blur"><feGaussianBlur stdDeviation="30"/></filter>
  <filter id="soft"><feGaussianBlur stdDeviation="1.2"/></filter>
  <style>.fl{{transform-box:fill-box}}.st{{fill:none;stroke:url(#goldleaf);stroke-linecap:round}}</style>
</defs>
<rect width="1920" height="1080" fill="url(#sky)"/>
<g fill="{gold}" opacity="0.8">{stars}</g>
<!-- gold-leaf rose window as a halo behind the doctor -->
<circle cx="900" cy="470" r="520" fill="url(#glow)"/>
<g opacity="0.22" stroke="{gold}" stroke-width="3">{rays}</g>
<circle cx="900" cy="470" r="330" fill="{_mix(sky_mid, gold, .22)}" stroke="url(#goldleaf)" stroke-width="16"/>
<g class="st" stroke-width="7"><circle cx="900" cy="470" r="292"/><circle cx="900" cy="470" r="208"/><circle cx="900" cy="470" r="92"/><circle cx="900" cy="470" r="40"/>
  <path d="M900 140V378 M900 562V800 M570 470H808 M992 470H1230 M666 236L832 402 M1134 236L968 402 M666 704L832 538 M1134 704L968 538"/></g>
<g class="st" stroke-width="5">{"".join(f'<circle cx="{900 + 250 * __import__("math").cos(i * .7854):.0f}" cy="{470 + 250 * __import__("math").sin(i * .7854):.0f}" r="38"/>' for i in range(8))}</g>
<!-- burning town on the hills -->
<path d="M0 720 C300 690 520 740 900 715 C1300 690 1600 745 1920 710 V800 H0z" fill="{_mix(ink, "#000000", .3)}"/>
<ellipse cx="960" cy="760" rx="1100" ry="220" fill="url(#fire)"/>
<g fill="{_mix(ink, "#000000", .35)}" stroke="{ink}" stroke-width="2">{_town(rnd, ink, c["yellow"])}</g>
<!-- dead earth -->
<path d="M0 770 C400 740 800 790 1200 760 C1560 740 1760 775 1920 760 V1080 H0z" fill="{_mix(ink, c["orange"], .08)}"/>
<ellipse cx="900" cy="990" rx="1100" ry="120" fill="{ink}" opacity="0.6" filter="url(#blur)"/>
<g stroke="{ink}" stroke-width="2" opacity="0.7">{"".join(f'<path d="M{x} {y} q14 -6 30 0 M{x + 8} {y + 8} q16 -5 34 0"/>' for x, y in [(rnd.randrange(160, 1760), rnd.randrange(800, 1020)) for _ in range(70)])}</g>
<!-- skeleton (left): reaches for the doctor -->
<g stroke-linejoin="round">
  <path d="M300 640 C285 740 270 820 262 930 M360 640 C372 740 378 830 388 940" {bones(15)}/>
  <path d="M276 600 q54 62 110 0 q-14 52 -55 52 q-41 0 -55 -52z" fill="{bone}" stroke="{bone_d}" stroke-width="3"/>
  <path d="M331 596 C340 520 322 450 336 380" {bones(13)}/>
  <g {bones(8)}><path d="M336 390 C260 392 232 430 244 470 M336 390 C412 392 440 430 428 470 M336 420 C252 426 224 470 240 514 M336 420 C420 426 448 470 432 514 M334 452 C256 462 232 508 252 548 M334 452 C416 462 440 508 420 548 M332 484 C268 498 252 540 274 574 M332 484 C404 498 420 540 398 574"/></g>
  <path d="M336 372 C300 360 270 362 246 380 M336 372 C380 358 420 356 456 372" {bones(11)}/>
  <path d="M456 372 C500 420 540 450 600 440 C650 430 690 400 735 372" {bones(12)}/>
  <path d="M735 372 l42 -22 M735 372 l48 -8 M735 372 l44 10 M735 372 l36 26" {bones(5)}/>
  <path d="M246 380 C206 440 196 520 210 590 M210 590 l-6 40 M210 590 l8 42 M210 590 l22 34" {bones(11)}/>
  <ellipse cx="338" cy="300" rx="52" ry="58" fill="{bone}" stroke="{bone_d}" stroke-width="3"/>
  <ellipse cx="316" cy="296" rx="15" ry="19" fill="{ink}"/><ellipse cx="362" cy="296" rx="15" ry="19" fill="{ink}"/>
  <path d="M338 318 l-8 24 h16z" fill="{ink}"/>
  <path d="M310 354 v18 M322 358 v18 M334 360 v18 M346 360 v18 M358 358 v18 M368 354 v18 M304 360 h70" stroke="{ink}" stroke-width="3"/>
</g>
<!-- skeleton (right) with a lantern -->
<g stroke="{bone}" fill="none" stroke-linecap="round">
  <ellipse cx="1590" cy="520" rx="30" ry="34" fill="{bone}" stroke="{bone_d}" stroke-width="2"/>
  <ellipse cx="1578" cy="516" rx="8" ry="11" fill="{ink}" stroke="none"/><ellipse cx="1602" cy="516" rx="8" ry="11" fill="{ink}" stroke="none"/>
  <path d="M1590 556 V690 M1590 690 C1560 760 1556 850 1552 940 M1590 690 C1620 760 1626 850 1634 940" stroke-width="10"/>
  <path d="M1590 570 C1550 574 1540 610 1550 640 M1590 570 C1630 574 1640 610 1630 640 M1590 596 C1556 600 1550 630 1558 660 M1590 596 C1624 600 1630 630 1622 660 M1555 574 C1520 560 1490 520 1470 470" stroke-width="6"/>
  <path d="M1470 470 V440" stroke-width="4"/>
  <circle cx="1470" cy="490" r="80" fill="url(#glow)" stroke="none"/>
  <rect x="1452" y="440" width="36" height="52" rx="6" fill="{gold}" stroke="{gold_d}" stroke-width="3"/><path d="M1448 440h44l-22 -20z" fill="{ink}" stroke="none"/>
</g>
<!-- the plague doctor -->
<g>
  <path d="M1290 250 V1040" stroke="{ink}" stroke-width="16" stroke-linecap="round"/>
  <path d="M1290 250 q-46 -44 0 -72 q40 14 14 52" fill="none" stroke="{gold_d}" stroke-width="10" stroke-linecap="round"/>
  <path d="M905 438 C840 560 800 800 745 1080 L1245 1080 C1225 820 1190 560 1140 438 C1070 410 975 410 905 438z" fill="url(#coat)" stroke="{gold_d}" stroke-width="4"/>
  <path d="M905 438 C860 520 826 640 806 760" fill="none" stroke="{gold}" stroke-width="3" opacity="0.8"/>
  <g fill="none" stroke="{_mix(cloak, gold, .3)}" stroke-width="4"><path d="M980 500 C960 700 930 880 900 1080 M1040 500 C1040 700 1030 880 1020 1080 M1110 500 C1130 700 1150 880 1170 1080"/></g>
  <path d="M870 440 C880 395 940 380 1010 384 C1090 380 1160 396 1180 440 C1120 470 940 470 870 440z" fill="{cloak}" stroke="{gold_d}" stroke-width="3"/>
  <path d="M790 780 C900 800 1100 800 1215 780 V808 C1100 830 900 830 790 808z" fill="{_mix(cloak, c["orange"], .25)}" stroke="{gold_d}" stroke-width="2"/>
  <rect x="1040" y="790" width="40" height="52" rx="6" fill="{_mix(cloak, c["orange"], .3)}" stroke="{gold}" stroke-width="2"/>
  <path d="M1140 450 C1210 480 1260 560 1285 640 L1250 660 C1220 590 1180 540 1120 520z" fill="{cloak}" stroke="{gold_d}" stroke-width="2"/>
  <ellipse cx="1288" cy="652" rx="26" ry="20" fill="{_mix(cloak, bone, .15)}" stroke="{gold_d}" stroke-width="2"/>
  <ellipse cx="1030" cy="352" rx="82" ry="92" fill="{cloak}"/>
  <path d="M948 340 C950 300 990 262 1040 262 C1100 262 1120 320 1108 390 C1090 440 1020 450 980 420 C960 400 950 370 948 340z" fill="{_mix(cloak, bone, .08)}"/>
  <path d="M968 322 C898 330 810 392 748 480 C820 468 900 440 976 392 C990 372 984 342 968 322z" fill="{_mix(ink, c["orange"], .35)}" stroke="{gold_d}" stroke-width="3"/>
  <path d="M968 322 C898 330 810 392 748 480" fill="none" stroke="{gold}" stroke-width="5" opacity="0.9"/>
  <circle cx="1000" cy="332" r="30" fill="{ink}" stroke="url(#goldleaf)" stroke-width="7"/>
  <circle cx="1000" cy="332" r="19" fill="{blood}"/><circle cx="1007" cy="325" r="6" fill="{_mix(blood, "#ffffff", .6)}"/>
  <path d="M1000 236 C1004 180 1030 150 1080 148 C1120 150 1140 176 1138 236z" fill="{cloak}" stroke="{gold_d}" stroke-width="3"/>
  <path d="M1002 214 H1138 V232 H1002z" fill="{blood}"/>
  <ellipse cx="1065" cy="238" rx="230" ry="34" fill="{cloak}" stroke="{gold_d}" stroke-width="3"/>
  <path d="M846 232 C900 214 1230 214 1290 232" fill="none" stroke="{gold}" stroke-width="3" opacity="0.7"/>
</g>
<!-- mist, ravens -->
<g filter="url(#blur)" fill="{bone}" opacity="0.22"><ellipse cx="420" cy="1000" rx="520" ry="46"/><ellipse cx="1500" cy="1000" rx="480" ry="44"/><ellipse cx="960" cy="1040" rx="800" ry="36"/></g>
<g fill="{ink}">
  <path d="M470 150 q22 -22 44 -4 q-18 4 -22 18 q-4 -14 -22 -14z"/><path d="M1140 120 q26 -26 52 -2 q-22 4 -26 22 q-6 -18 -26 -20z"/>
  <path d="M590 60 q16 -14 32 -2 q-12 3 -16 12 q-3 -10 -16 -10z"/><path d="M1300 300 q20 -20 40 -2 q-16 3 -20 16 q-4 -13 -20 -14z"/>
</g>
<!-- aged paint: craquelure, grain, darkened edges -->
<g fill="none" stroke="{ink}" stroke-width="1.4" opacity="0.5">{crack}</g>
<rect width="1920" height="1080" filter="url(#paint)" opacity="0.5"/>
<rect width="1920" height="1080" filter="url(#grain)" opacity="0.5"/>
<rect width="1920" height="1080" fill="url(#vig)"/>
<!-- illuminated border -->
<g>
  <rect x="0" y="0" width="1920" height="1080" fill="none" stroke="{_mix(ink, blood, .5)}" stroke-width="64"/>
  <rect x="32" y="32" width="1856" height="1016" fill="none" stroke="url(#goldleaf)" stroke-width="7"/>
  <rect x="60" y="60" width="1800" height="960" fill="none" stroke="url(#goldleaf)" stroke-width="3"/>
  {_scroll(96, 1830, 46, gold)}{_scroll(96, 1830, 1034, gold, False)}
  <path d="M46 96 V1000 M1874 96 V1000" stroke="{gold}" stroke-width="3" stroke-dasharray="2 14" stroke-linecap="round"/>
  {"".join(f'<g transform="translate({x} {y})"><circle r="30" fill="{blood}" stroke="url(#goldleaf)" stroke-width="5"/><path d="M0 -22 V22 M-22 0 H22 M-15 -15 L15 15 M15 -15 L-15 15" stroke="{gold}" stroke-width="3"/><circle r="6" fill="{gold}"/></g>' for x, y in ((46, 46), (1874, 46), (46, 1034), (1874, 1034)))}
  <rect x="560" y="1002" width="800" height="54" rx="8" fill="{_mix(ink, blood, .55)}" stroke="url(#goldleaf)" stroke-width="4"/>
  <text x="960" y="1038" text-anchor="middle" font-family="DejaVu Serif, Georgia, serif" font-size="27" letter-spacing="7" fill="{gold}">MEMENTO MORI · MCCCXLVIII</text>
</g>
</svg>
'''


def crypt(c: dict) -> str:
    import random
    rnd = random.Random(1492)
    ink, gold = c["crust"], c["yellow"]
    bone = c["text"]
    sky = _mix(ink, "#000000", 0.2)
    floor = _mix(ink, "#1a171a", 0.3)
    stone = _mix(ink, "#2a262a", 0.3)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 1920 1080">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky}"/><stop offset="1" stop-color="{ink}"/></linearGradient>
  <radialGradient id="cand" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{gold}" stop-opacity="0.22"/><stop offset="1" stop-color="{gold}" stop-opacity="0"/></radialGradient>
  <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{_mix(floor, stone, .5)}"/><stop offset="1" stop-color="{floor}"/></linearGradient>
  <filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" seed="7"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.4 -0.12"/></filter>
</defs>
<rect width="1920" height="1080" fill="url(#sky)"/>
<rect y="600" width="1920" height="480" fill="url(#floor)"/>
<g stroke="{_mix(stone, ink, .5)}" stroke-width="12" fill="none">
  <path d="M0 600 L320 320 L640 600"/>
  <path d="M320 600 L640 320 L960 600"/>
  <path d="M640 600 L960 320 L1280 600"/>
  <path d="M960 600 L1280 320 L1600 600"/>
  <path d="M1280 600 L1600 320 L1920 600"/>
</g>
<g fill="{_mix(stone, ink, .4)}">
  <rect x="310" y="320" width="20" height="280"/>
  <rect x="630" y="320" width="20" height="280"/>
  <rect x="950" y="320" width="20" height="280"/>
  <rect x="1270" y="320" width="20" height="280"/>
  <rect x="1590" y="320" width="20" height="280"/>
</g>
<g stroke="{_mix(stone, ink, .6)}" stroke-width="6" fill="none" opacity="0.6">
  <line x1="320" y1="320" x2="320" y2="220"/>
  <line x1="640" y1="320" x2="640" y2="220"/>
  <line x1="960" y1="320" x2="960" y2="220"/>
  <line x1="1280" y1="320" x2="1280" y2="220"/>
  <line x1="1600" y1="320" x2="1600" y2="220"/>
  <path d="M0 220 H1920 M0 140 H1920" opacity="0.4"/>
</g>
<g stroke="{_mix(gold, ink, .6)}" stroke-width="4" fill="none" opacity="0.5">
  <rect x="840" y="80" width="240" height="160" rx="6"/>
  <line x1="960" y1="80" x2="960" y2="240"/>
  <line x1="840" y1="160" x2="1080" y2="160"/>
  <path d="M900 80 A60 60 0 0 1 960 140 A60 60 0 0 0 1020 80"/>
  <path d="M900 240 A60 60 0 0 0 960 180 A60 60 0 0 1 1020 240"/>
</g>
<g>
  <ellipse cx="400" cy="580" rx="14" ry="6" fill="{_mix(gold, ink, .8)}"/>
  <path d="M394 580 L394 540 Q400 530 406 540 L406 580z" fill="{_mix(bone, ink, .4)}"/>
  <circle cx="400" cy="538" r="4" fill="{gold}" opacity="0.7"/>
  <circle cx="400" cy="520" r="60" fill="url(#cand)"/>
  <ellipse cx="1520" cy="580" rx="14" ry="6" fill="{_mix(gold, ink, .8)}"/>
  <path d="M1514 580 L1514 540 Q1520 530 1526 540 L1526 580z" fill="{_mix(bone, ink, .4)}"/>
  <circle cx="1520" cy="538" r="4" fill="{gold}" opacity="0.7"/>
  <circle cx="1520" cy="520" r="60" fill="url(#cand)"/>
</g>
<rect x="820" y="620" width="280" height="60" rx="4" fill="{_mix(stone, ink, .3)}" stroke="{_mix(stone, ink, .7)}" stroke-width="4"/>
<rect x="840" y="600" width="240" height="30" rx="2" fill="{_mix(stone, ink, .25)}" stroke="{_mix(stone, ink, .7)}" stroke-width="3"/>
<rect width="1920" height="1080" filter="url(#grain)" opacity="0.22"/>
<rect width="1920" height="1080" fill="url(#vig)" transform="rotate(180 960 540)" opacity="0.5"/>
<rect width="1920" height="1080" fill="url(#vig)" opacity="0.4"/>
</svg>
"""

ART = {"cathedral": cathedral, "plague": plague, "crypt": crypt}
