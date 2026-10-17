"""Generates extras/cs2/banner.svg (README header of cs2translate) and prints the start logo
that is pasted into extras/cs2/cs2translate.py (LOGO)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_banner as mb  # noqa: E402
from swayforge.ascii import art, banner  # noqa: E402

STOPS = ["#6fb6ff", "#7fbf6a", "#f2b84b", "#e05a4f"]       # CT blue → green → T yellow → red


def build() -> str:
    cs2, tr = banner("CS2", 6), banner("TRANSLATE", 6)
    n = max(map(len, cs2))
    title = [a.ljust(n + 4) + b for a, b in zip(cs2, tr)]
    pic = art("gamepad")
    mb.STOPS = STOPS
    # reuse swayforge's layout: monkey-patch banner() to return our stacked title
    mb.banner = lambda *_a: title
    mb.art = lambda *_a: pic
    return mb.build("", "live chat translation for Counter-Strike 2 · click-through overlay")


def logo() -> str:
    return "\n".join(banner("CS2", 5) + banner("TRANSLATE", 5))


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "extras/cs2/banner.svg"
    out.write_text(build())
    print(out)
    print(logo())
