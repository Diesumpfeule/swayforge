"""Turns scripts/plague_scene.svg into shaded ASCII art (data/wallart/plague_scene.txt).

The scene is drawn as a greyscale SVG; every character cell takes the glyph whose ink density
matches the cell's brightness. wallart.plague() then colours the text with the theme.
Needs rsvg-convert + Pillow (only to regenerate – the text file is shipped).
"""
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
COLS, ROWS = 600, 188
CANDIDATES = " .'`,:;-~_+<>=!/\\|()?*xvzucn1ilIrtjfLJYTVXZOQ0Ewmgdhkpqb#%8&B@WM"
FONT = "/home/owl/.local/share/fonts/JetBrainsMonoNerd/JetBrainsMonoNerdFont-Regular.ttf"


def ramp() -> str:
    f = ImageFont.truetype(FONT, 26)
    dens = []
    for ch in CANDIDATES:
        im = Image.new("L", (30, 40), 0)
        ImageDraw.Draw(im).text((2, 2), ch, font=f, fill=255)
        dens.append((sum(im.get_flattened_data()) / 255, ch))
    dens.sort()
    top = dens[-1][0]
    out, last = [], -1.0
    for d, ch in dens:                      # keep glyphs that are spaced out in density
        if d - last >= top / 30 or not out:
            out.append(ch)
            last = d
    return "".join(out)


def main() -> None:
    chars = ramp()
    print("ramp:", chars)
    with tempfile.TemporaryDirectory() as t:
        png = Path(t) / "s.png"
        subprocess.run(["rsvg-convert", "-w", "3840", "-o", str(png), str(ROOT / "scripts/plague_scene.svg")], check=True)
        im = Image.open(png).convert("L").resize((COLS, ROWS), Image.BOX)
    px = im.load()
    lines = []
    for y in range(ROWS):
        row = ""
        for x in range(COLS):
            v = (px[x, y] / 255) ** 0.62                       # lift the darks a little
            row += chars[min(len(chars) - 1, int(v * len(chars)))]
        lines.append(row.rstrip())
    out = ROOT / "swayforge/data/wallart/plague_scene.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("RAMP" + chars + "\n" + "\n".join(lines) + "\n")
    print(len(lines), "rows written")


if __name__ == "__main__":
    main()
