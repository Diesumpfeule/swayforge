"""ASCII art: a small block font for banners and one motif per theme.

All art here is original to swayforge. Add your own by dropping a text file into
~/.config/swayforge/ascii/<name>.txt – it shows up everywhere art can be chosen.
"""
from __future__ import annotations

from . import paths

# ── 5-row block font ─────────────────────────────────────────────────
FONT: dict[str, list[str]] = {
    "A": [" ██ ", "█  █", "████", "█  █", "█  █"],
    "B": ["███ ", "█  █", "███ ", "█  █", "███ "],
    "C": [" ███", "█   ", "█   ", "█   ", " ███"],
    "D": ["███ ", "█  █", "█  █", "█  █", "███ "],
    "E": ["███", "█  ", "██ ", "█  ", "███"],
    "F": ["███", "█  ", "██ ", "█  ", "█  "],
    "G": [" ███", "█   ", "█ ██", "█  █", " ██ "],
    "H": ["█  █", "█  █", "████", "█  █", "█  █"],
    "I": ["███", " █ ", " █ ", " █ ", "███"],
    "J": ["  █", "  █", "  █", "█ █", " █ "],
    "K": ["█  █", "█ █ ", "██  ", "█ █ ", "█  █"],
    "L": ["█  ", "█  ", "█  ", "█  ", "███"],
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    "N": ["█  █", "██ █", "█ ██", "█  █", "█  █"],
    "O": [" ██ ", "█  █", "█  █", "█  █", " ██ "],
    "P": ["███ ", "█  █", "███ ", "█   ", "█   "],
    "Q": [" ██ ", "█  █", "█  █", "█ ██", " ███"],
    "R": ["███ ", "█  █", "███ ", "█ █ ", "█  █"],
    "S": [" ███", "█   ", " ██ ", "   █", "███ "],
    "T": ["███", " █ ", " █ ", " █ ", " █ "],
    "U": ["█  █", "█  █", "█  █", "█  █", " ██ "],
    "V": ["█   █", "█   █", " █ █ ", " █ █ ", "  █  "],
    "W": ["█   █", "█   █", "█ █ █", "██ ██", "█   █"],
    "X": ["█   █", " █ █ ", "  █  ", " █ █ ", "█   █"],
    "Y": ["█ █", "█ █", " █ ", " █ ", " █ "],
    "Z": ["████", "   █", " ██ ", "█   ", "████"],
    "0": [" ██ ", "█ ██", "██ █", "█  █", " ██ "],
    "1": [" █ ", "██ ", " █ ", " █ ", "███"],
    "2": ["███ ", "   █", " ██ ", "█   ", "████"],
    "3": ["███ ", "   █", " ██ ", "   █", "███ "],
    "4": ["█  █", "█  █", "████", "   █", "   █"],
    "5": ["████", "█   ", "███ ", "   █", "███ "],
    "6": [" ██ ", "█   ", "███ ", "█  █", " ██ "],
    "7": ["████", "   █", "  █ ", " █  ", " █  "],
    "8": [" ██ ", "█  █", " ██ ", "█  █", " ██ "],
    "9": [" ██ ", "█  █", " ███", "   █", " ██ "],
    " ": ["  ", "  ", "  ", "  ", "  "],
    "-": ["   ", "   ", "███", "   ", "   "],
    "_": ["   ", "   ", "   ", "   ", "███"],
    ".": [" ", " ", " ", " ", "█"],
    ":": [" ", "█", " ", "█", " "],
    "/": ["   █", "  █ ", " █  ", "█   ", "    "],
    "!": ["█", "█", "█", " ", "█"],
    "?": ["███ ", "   █", " ██ ", "    ", " █  "],
    ">": ["█  ", " █ ", "  █", " █ ", "█  "],
}


def banner(text: str, fill: str = "█") -> list[str]:
    rows = ["", "", "", "", ""]
    for ch in text.upper():
        glyph = FONT.get(ch, FONT["?"])
        for i in range(5):
            rows[i] += glyph[i].replace("█", fill) + " "
    return [r.rstrip() for r in rows]


# ── Motifs (original swayforge art) ──────────────────────────────────
ART: dict[str, str] = {
    "anvil": r"""
      ____________________________
     /                            \__
    |    s w a y f o r g e         __|
     \_____________        _______/
                   |      |
                ___|      |___
               /______________\
""",
    "rose": r"""
            _,--._
          ,'  _   `.
         /  ,' `.   \
        |  (  @  )   |
         \  `._,'   /
          `-.____,-'
         .    ||    .
          \   ||   /
           `-.||.-'
              ||
              ||
              ||
""",
    "moon": r"""
                    .-''''-.
       *          .'  .-.   '.        *
                 /   (   )    \
    ----===**    |    '-'     |
                  \    .     /
        *          '-.____.-'
   /\       /\     /\        /\
  /  \/\   /  \   /  \  /\  /  \
 /      \_/    \_/    \/  \/    \
""",
    "bat": r"""
     _                         _
    / \__      .--. .--.     __/ \
   /     '----/    V    \----'    \
  /   /\      |  o   o  |     /\   \
  \__/  \___  '.   ^   .'  ___/  \__/
            '--'._____.'--'
""",
    "terminal": r"""
   .--------------------------.
   | .----------------------. |
   | | C:\> boot            | |
   | | memory ........ ok   | |
   | | video ......... ok   | |
   | | C:\> _               | |
   | '----------------------' |
   '----------.____.----------'
          ____|____|____
         [______________]
""",
    "wired": r"""
     o-------o            o
     |\     / \          /|
     | \   /   o--------o |
     |  \ /    |        | |
     o---@-----+--o     o-o
        / \    |   \   /
       o   o---o----o-o
   [ node 07 :: connected ]
   [ signal  :: ||||||||-- ]
""",
    "skull": r"""
        .--------.
       /  _    _  \
      |  (o)  (o)  |
      |      ^     |
       \   '----' /
        '-.____.-'
         |_|__|_|
""",
}


def user_art() -> dict[str, str]:
    d = paths.CONFIG_DIR / "ascii"
    out = {}
    if d.is_dir():
        for f in sorted(d.glob("*.txt")):
            out[f.stem] = "\n" + f.read_text().rstrip("\n") + "\n"
    return out


def all_art() -> dict[str, str]:
    return ART | user_art()


def art(name: str) -> list[str]:
    a = all_art().get(name) or ART["anvil"]
    lines = a.strip("\n").split("\n")
    pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return [l[pad:].rstrip() for l in lines]


def resolve(s: dict, theme) -> str:
    """Which art is active: explicit choice or the theme's motif."""
    choice = s["theme"].get("ascii", "auto")
    if choice and choice != "auto" and choice in all_art():
        return choice
    return theme.style.get("ascii", "anvil")


def fastfetch_logo(name: str) -> str:
    """Logo file for fastfetch: $1 = main colour, $2 = caption line."""
    lines = art(name)
    out = []
    for i, l in enumerate(lines):
        out.append(("$2" if i == len(lines) - 1 and l.strip().startswith("[") else "$1") + l)
    return "\n".join(out) + "\n"
