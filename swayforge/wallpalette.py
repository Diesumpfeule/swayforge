"""Theme from a wallpaper: pick colours out of an image and build a full swayforge theme.

Background, surfaces and text get the wallpaper's dominant hue (kept calm, so text stays
readable); the accents are the most striking colours in the picture; red/green/yellow/…
keep their meaning but lean towards matching colours from the image. Every text and
accent colour is checked for contrast against the background.
"""
from __future__ import annotations

import colorsys
from pathlib import Path

from . import paths, themes, tomlw

LIVE_ID = "from-wallpaper"


def _rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % tuple(round(max(0, min(1, v)) * 255) for v in (r, g, b))


def hls(h: float, l: float, s: float) -> str:
    return _hex(*colorsys.hls_to_rgb(h % 1.0, max(0, min(1, l)), max(0, min(1, s))))


def luminance(c: str) -> float:
    def ch(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _readable(h: float, l: float, s: float, bg: str, dark: bool, need: float) -> str:
    """Move lightness away from the background until the contrast is good enough."""
    c = hls(h, l, s)
    for _ in range(40):
        if contrast(c, bg) >= need:
            break
        l += 0.02 if dark else -0.02
        c = hls(h, l, s)
    return c


def sample(path: str | Path, n: int = 16) -> list[tuple[float, float, float, float]]:
    """Main colours of an image as (hue, lightness, saturation, share 0..1)."""
    from PIL import Image                      # python3-pillow
    img = Image.open(path).convert("RGB")
    img.thumbnail((200, 200))
    q = img.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = q.getcolors() or []
    total = sum(c for c, _ in counts) or 1
    out = []
    for count, idx in counts:
        r, g, b = (pal[idx * 3 + i] / 255 for i in range(3))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        out.append((h, l, s, count / total))
    return sorted(out, key=lambda x: -x[3])


def _hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


def build(cols: list[tuple[float, float, float, float]], mode: str = "auto") -> tuple[dict, list[str], bool]:
    """Sampled colours → (theme colours, 16 ANSI colours, dark?)."""
    avg_l = sum(l * w for _h, l, _s, w in cols)
    dark = mode == "dark" or (mode == "auto" and avg_l < 0.55)
    dom_h, _dl, dom_s, _w = max(cols, key=lambda x: x[3] * (0.3 + x[2]))   # biggest, a bit colourful
    bs = min(dom_s, 0.45) * 0.55                  # calm background saturation
    if dark:
        c = {"crust": hls(dom_h, 0.035, bs), "mantle": hls(dom_h, 0.055, bs), "base": hls(dom_h, 0.075, bs),
             "surface": hls(dom_h, 0.13, bs), "surface2": hls(dom_h, 0.20, bs * 0.9),
             "overlay": hls(dom_h, 0.38, bs * 0.7)}
    else:
        c = {"crust": hls(dom_h, 0.84, bs), "mantle": hls(dom_h, 0.90, bs), "base": hls(dom_h, 0.955, bs),
             "surface": hls(dom_h, 0.88, bs), "surface2": hls(dom_h, 0.80, bs * 0.9),
             "overlay": hls(dom_h, 0.58, bs * 0.7)}
    base = c["base"]
    c["text"] = _readable(dom_h, 0.86 if dark else 0.16, min(bs, 0.18), base, dark, 9)
    c["subtext"] = _readable(dom_h, 0.66 if dark else 0.36, min(bs, 0.2), base, dark, 4.5)

    # accents: vivid colours that actually appear in the picture
    vivid = [x for x in cols if x[2] > 0.22 and 0.12 < x[1] < 0.9]
    vivid.sort(key=lambda x: -(x[3] ** 0.5) * x[2] * (1.1 - abs(x[1] - 0.5)))
    if vivid:
        ah, _al, as_, _ = vivid[0]
    else:                                         # grey picture: tint of the dominant hue
        ah, as_ = dom_h, max(dom_s, 0.45)
    as_ = max(as_, 0.5)
    c["accent"] = _readable(ah, 0.6 if dark else 0.42, as_, base, dark, 4.5)
    second = next((x for x in vivid[1:] if _hue_dist(x[0], ah) > 0.08), None)
    if second:
        c["accent2"] = _readable(second[0], 0.55 if dark else 0.4, max(second[2], 0.45), base, dark, 3)
    else:                                         # same hue, deeper – like the bundled retro themes
        c["accent2"] = _readable(ah, 0.42 if dark else 0.52, as_ * 0.9, base, dark, 2.5)

    # named colours keep their meaning, but lean towards matching picture colours
    named = {"red": 0.0, "orange": 0.08, "yellow": 0.15, "green": 0.33, "cyan": 0.5,
             "blue": 0.6, "magenta": 0.83}
    for name, h in named.items():
        near = [x for x in vivid if _hue_dist(x[0], h) < 0.06]
        if near:
            h = h + ((near[0][0] - h + 0.5) % 1.0 - 0.5) * 0.6
        c[name] = _readable(h, 0.62 if dark else 0.4, 0.6, base, dark, 3)

    def bright(col: str) -> str:
        hh, ll, ss = colorsys.rgb_to_hls(*_rgb(col))
        return hls(hh, ll + (0.08 if dark else -0.06), ss)
    ansi = [c["surface"], c["red"], c["green"], c["yellow"], c["blue"], c["magenta"], c["cyan"], c["subtext"],
            c["surface2"], bright(c["red"]), bright(c["green"]), bright(c["yellow"]), bright(c["blue"]),
            bright(c["magenta"]), bright(c["cyan"]), c["text"]]
    return {k: c[k] for k in themes.COLOR_KEYS}, ansi, dark


def make_theme(image: str | Path, mode: str = "auto", label: str = "", tid: str = LIVE_ID) -> themes.Theme:
    """Write the theme file (~/.config/swayforge/themes/<tid>.toml) and return it.

    The live one (from-wallpaper) is overwritten on every new wallpaper; give it a name
    to keep it for good."""
    colors, ansi, dark = build(sample(image), mode)
    paths.ensure_dirs()
    name = label or f"From wallpaper ({Path(image).name})"
    data = {"label": name, "dark": dark, "ansi": ansi, "colors": colors,
            "source": {"wallpaper": str(image), "mode": mode}}
    tid = themes.slug(tid)
    p = paths.USER_THEMES / f"{tid}.toml"
    p.write_text(f"# Made by swayforge from {image}\n" + tomlw.dumps(data))
    t = themes.all_themes().get(tid)
    assert t is not None
    return t
