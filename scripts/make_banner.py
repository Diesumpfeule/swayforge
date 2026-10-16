"""Generates docs/img/banner.svg – the README header: shaded ASCII letters + the forge motif."""
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from swayforge.ascii import SHADE, art, banner  # noqa: E402

FS, LH, CW = 14, 18, 8.43        # font size, line height, monospace advance (≈0.6 em)
PAD_X, PAD_Y = 36, 34
STOPS = ["#3fbf5f", "#7fbf6a", "#c96a3a", "#e05a4f", "#6c8fd8"]   # Type O → Rust → Wired → Green Night
FONT = "ui-monospace, 'JetBrains Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"


def _row(line: str, x: float, y: float, face: str, shade: str) -> str:
    spans, cur, buf = [], None, ""
    for ch in line:
        kind = "s" if ch in SHADE else "f"
        if ch == " ":
            kind = cur or "f"
        if kind != cur and buf:
            spans.append((cur, buf))
            buf = ""
        cur = kind
        buf += ch
    if buf:
        spans.append((cur, buf))
    inner = "".join(f'<tspan fill="{face if k == "f" else shade}">{escape(t)}</tspan>' for k, t in spans)
    return f'<text x="{x:.1f}" y="{y:.1f}" xml:space="preserve">{inner}</text>'


def build(word: str = "swayforge", tagline: str = "fedora sway · themes · installer · settings") -> str:
    title = banner(word, 7)
    pic = art("forge")
    tcols = max(map(len, title))
    pcols = max(map(len, pic))
    gap = 6
    w = (tcols + gap + pcols) * CW + 2 * PAD_X
    rows = max(len(title) + 3, len(pic))
    h = rows * LH + 2 * PAD_Y + 10
    ty0 = PAD_Y + LH + (len(pic) - len(title) - 3) / 2 * LH if len(pic) > len(title) + 3 else PAD_Y + LH
    out = [_row(l, PAD_X, ty0 + i * LH, "url(#g)", "url(#gs)") for i, l in enumerate(title)]
    px = PAD_X + (tcols + gap) * CW
    out += [_row(l, px, PAD_Y + LH + i * LH, "#b9dcb2", "#4e6a4b") for i, l in enumerate(pic)]
    stops = "".join(f'<stop offset="{i / (len(STOPS) - 1):.2f}" stop-color="{s}"/>' for i, s in enumerate(STOPS))
    tag_y = ty0 + (len(title) + 1.6) * LH
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{PAD_X}" x2="{PAD_X + tcols * CW:.0f}" y1="0" y2="0">{stops}</linearGradient>
  <linearGradient id="gs" gradientUnits="userSpaceOnUse" x1="{PAD_X}" x2="{PAD_X + tcols * CW:.0f}" y1="0" y2="0">{stops.replace('stop-color', 'stop-opacity="0.5" stop-color')}</linearGradient>
  <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#ffffff" opacity="0.025"/></pattern>
</defs>
<rect width="{w:.0f}" height="{h:.0f}" rx="10" fill="#0a0c0a"/>
<rect width="{w:.0f}" height="{h:.0f}" rx="10" fill="url(#scan)"/>
<g font-family="{FONT}" font-size="{FS}" font-weight="bold">
{chr(10).join(out)}
</g>
<text x="{PAD_X}" y="{tag_y:.1f}" font-family="{FONT}" font-size="15" fill="#8fa88f" letter-spacing="1">&gt; {tagline}<tspan fill="#3fbf5f">_<animate attributeName="opacity"
      values="1;1;0;0" dur="1.1s" repeatCount="indefinite"/></tspan></text>
</svg>
'''


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "docs/img/banner.svg"
    out.write_text(build())
    print(out)
