"""UI layouts: how the bar, launcher and notifications look – independent of colours.

A layout is combined with any colour theme, e.g. "win98" + "Rust".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Layout:
    id: str
    label: str
    desc: str
    position: str          # top | bottom | left
    preview: str           # ASCII sketch for the settings app


LAYOUTS: dict[str, Layout] = {l.id: l for l in [
    Layout("modern", "Modern islands", "Floating rounded islands at the top", "top",
           "(  1  2  3  )        (  Fri 16.10.  21:30  )        ( cpu 12%  vol 40%  ⏻ )"),
    Layout("solid", "Solid bar", "One continuous bar at the top", "top",
           "▕ 1  2  3 │ kitty              Fri 16.10. 21:30           cpu 12% │ vol 40% │ ⏻ ▏"),
    Layout("win98", "Classic 98", "Bottom taskbar, Start button, 3D bevelled buttons, sunken tray",
           "bottom",
           "┌─────────┐┌──────────────┐┌──────────────┐          ┌─────────────────┐\n"
           "│ ▣ Start ││ kitty        ││ firefox      │          │ ♪  ⇅  ▤  21:30 │\n"
           "└─────────┘└──────────────┘└──────────────┘          └─────────────────┘"),
    Layout("win7", "Glass 7", "Bottom glass taskbar, round start orb, icon-only task buttons",
           "bottom",
           "  ( ◉ )  ╭───╮ ╭───╮ ╭───╮                              ♪  ⇅  21:30\n"
           "         │ ▣ │ │ ◈ │ │ ✉ │                              Fri 16.10.\n"
           "         ╰───╯ ╰───╯ ╰───╯"),
    Layout("win11", "Modern 11", "Centered rounded taskbar with start button and icon tasks, widgets on the left",
           "bottom",
           "  1 2 3                  ( ❖ ) ╭───╮ ╭───╮ ╭───╮                  ♪ ⇅ 21:30\n"
           "                                 └ ▔ ┘ └───┘ └───┘"),
    Layout("touch", "Touch", "Tall bottom bar with big tap targets, on-screen keyboard button, large menus",
           "bottom",
           "┌──────┐┌──────┐                ┌────┐┌────┐┌────┐             ┌──────┐┌──────┐┌──────┐\n"
           "│  ❖   ││ ⌨    │                │ 1  ││ 2  ││ 3  │             │ ♪ 40 ││ 21:30││  ⏻   │\n"
           "└──────┘└──────┘                └────┘└────┘└────┘             └──────┘└──────┘└──────┘"),
    Layout("wired", "Wired (hacker)", "Text only, brackets, no icons, seconds ticking", "top",
           "[01][02][03] :: kitty          [cpu 12%][mem 40%][net up][vol 40%] [21:30:07] [off]"),
    Layout("cathedral", "Cathedral (gothic)",
           "Ornamented top bar: roman-numeral workspaces, crosses around the clock, framed menus", "top",
           "═╡ I  II  III ╞═══════════  ✠ 21:30 ✠  ═══════════╡ ♪ 40  ⇅  ❦ ⏻ ╞═\n"
           "           ¨¨¨                    ˘˘˘˘˘˘˘                           "),
    Layout("minimal", "Minimal", "Only workspaces, clock, tray and power", "top",
           "                    1  2  3          21:30          ▤  ⏻"),
    Layout("sidebar", "Sidebar", "Vertical icon bar on the left", "left",
           "┃ 1 ┃\n┃ 2 ┃\n┃ 3 ┃\n┃   ┃\n┃ ♪ ┃\n┃ ⇅ ┃\n┃21 ┃\n┃30 ┃\n┃ ⏻ ┃"),
]}

LEGACY = {"floating": "modern", "solid": "solid"}


def get(name: str) -> Layout:
    return LAYOUTS.get(LEGACY.get(name, name)) or LAYOUTS["modern"]


def choices() -> list[tuple[str, str]]:
    return [(l.label, l.id) for l in LAYOUTS.values()]
