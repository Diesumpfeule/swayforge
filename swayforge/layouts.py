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
    Layout("glass", "Glass islands",
           "Translucent floating islands with hairline borders, accent outline on the focused workspace, compact centred launcher",
           "top",
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
    Layout("winxp", "Luna XP", "Bottom taskbar in blue with a big green Start button, rounded task buttons, tray with clock, balloon notifications",
           "bottom",
           "┌─────────╮┌─────────────┐┌─────────────┐              ┌──────────────────┐\n"
           "│ ❖ start ││ kitty       ││ firefox     │              │ ♪  ⇅  ▤   21:30  │\n"
           "└─────────╯└─────────────┘└─────────────┘              └──────────────────┘"),
    Layout("dread", "Dread (survival horror)",
           "Dark top bar of worn inventory slots, rust rule, blood-red focus glow, item-box launcher, grim notifications",
           "top",
           "▕▓ 1 ▓│░ 2 ░│░ 3 ░▏  ▸ kitty                    ▕ cpu 12% ▏▕ vol 40% ▏▕ 21:30 ▏▕ ⏻ ▏\n"
           "▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔"),
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


# ── Your own layouts (made in the swayforge app → Theme & layout maker) ─────────────
# A user layout = one of the layouts above as the look ("base") + your own arrangement:
# where the bar sits, which modules go left/centre/right, and a few size knobs.
# Stored as ~/.config/swayforge/layouts/<id>.toml – ids always start with "my-".
from dataclasses import replace  # noqa: E402

MODULES: dict[str, tuple[str, str]] = {      # key → (waybar module, label)
    "start": ("custom/start", "Start button"),
    "workspaces": ("sway/workspaces", "Workspaces"),
    "mode": ("sway/mode", "Resize mode"),
    "window": ("sway/window", "Window title"),
    "taskbar": ("wlr/taskbar", "Task buttons"),
    "clock": ("clock", "Clock"),
    "media": ("mpris", "Now playing"),
    "gamemode": ("custom/gamemode", "Gaming mode"),
    "cpu": ("cpu", "CPU"),
    "gpu": ("custom/gpu", "GPU"),
    "memory": ("memory", "Memory"),
    "temperature": ("temperature", "Temperature"),
    "taskmanager": ("custom/taskmanager", "Task manager"),
    "network": ("network", "Network"),
    "bluetooth": ("bluetooth", "Bluetooth"),
    "audio": ("pulseaudio", "Volume"),
    "mic": ("pulseaudio#mic", "Microphone"),
    "backlight": ("backlight", "Brightness"),
    "battery": ("battery", "Battery"),
    "idle": ("idle_inhibitor", "Stay awake"),
    "tray": ("tray", "Tray"),
    "keyboard": ("custom/osk", "On-screen keyboard"),
    "power": ("custom/power", "Power menu"),
}
WS_STYLES = {"numbers": "1 2 3", "roman": "I II III", "dots": "● ○ ○", "brackets": "[1][2][3]"}
TEXT_MODES = {"both": "Icons + text", "icons": "Icons only", "text": "Text only"}
POSITIONS = ("top", "bottom", "left", "right")
CUSTOM_DEFAULT = {
    "label": "My layout", "base": "modern", "position": "top",
    "left": ["workspaces", "mode", "window"], "center": ["clock"],
    "right": ["media", "cpu", "memory", "network", "audio", "tray", "power"],
    "height": 34, "margin": 0, "radius": -1, "opacity": 0.9, "padding": 12, "font_size": 0,
    "ws_style": "numbers", "text_mode": "both",
}
_NUM = {"height": (18, 72), "margin": (0, 40), "radius": (-1, 30), "opacity": (0.2, 1.0), "padding": (0, 30),
        "font_size": (-4, 8)}


def user_dir():
    from . import paths
    return paths.CONFIG_DIR / "layouts"


def sanitize(d: dict) -> dict:
    """Anything from a file or the app → a valid layout (unknown values fall back, numbers are clamped)."""
    import re as _re
    out = dict(CUSTOM_DEFAULT)
    out["label"] = _re.sub(r"[\x00-\x1f]", "", str(d.get("label", out["label"])))[:40].strip() or "My layout"
    out["base"] = d.get("base") if d.get("base") in LAYOUTS else "modern"
    out["position"] = d.get("position") if d.get("position") in POSITIONS else "top"
    seen: set[str] = set()
    for zone in ("left", "center", "right"):
        mods = []
        for m in d.get(zone, out[zone]) if isinstance(d.get(zone, out[zone]), list) else []:
            if isinstance(m, str) and m in MODULES and m not in seen:
                mods.append(m)
                seen.add(m)
        out[zone] = mods[:20]
    for k, (lo, hi) in _NUM.items():
        try:
            v = float(d.get(k, out[k]))
        except (TypeError, ValueError):
            v = float(out[k])
        v = min(hi, max(lo, v))
        out[k] = v if k == "opacity" else int(round(v))
    out["ws_style"] = d.get("ws_style") if d.get("ws_style") in WS_STYLES else "numbers"
    out["text_mode"] = d.get("text_mode") if d.get("text_mode") in TEXT_MODES else "both"
    return out


def user_layouts() -> dict[str, dict]:
    import tomllib
    out = {}
    d = user_dir()
    for f in sorted(d.glob("my-*.toml")) if d.is_dir() else []:
        try:
            out[f.stem] = sanitize(tomllib.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return out


def custom(name: str) -> dict | None:
    if not str(name).startswith("my-"):
        return None
    return user_layouts().get(name)


def exists(name: str) -> bool:
    return name in LAYOUTS or name in LEGACY or custom(name) is not None


def save_user(d: dict, lid: str = "") -> str:
    import re as _re
    from . import tomlw
    from .fsutil import atomic_write
    data = sanitize(d)
    if not (lid.startswith("my-") and _re.fullmatch(r"my-[a-z0-9-]{1,40}", lid)):
        slug = _re.sub(r"[^a-z0-9]+", "-", data["label"].lower()).strip("-") or "layout"
        lid = "my-" + slug.removeprefix("my-")[:36]
    user_dir().mkdir(parents=True, exist_ok=True)
    atomic_write(user_dir() / f"{lid}.toml", "# Your own bar layout – made with swayforge\n" + tomlw.dumps(data))
    return lid


def delete_user(lid: str) -> bool:
    import re as _re
    if not _re.fullmatch(r"my-[a-z0-9-]{1,40}", lid):
        return False
    f = user_dir() / f"{lid}.toml"
    if f.exists():
        f.unlink()
        return True
    return False


def preview_of(c: dict) -> str:
    def zone(z):
        return "  ".join(MODULES[m][1].split()[0].lower() for m in c[z])
    return f"{zone('left')}   ·   {zone('center')}   ·   {zone('right')}"


_builtin_get = get


def get(name: str) -> Layout:                                     # noqa: F811 – extends the one above
    """Built-in layout, or for your own ones: the base look with your label and position."""
    c = custom(name)
    if c:
        base = _builtin_get(c["base"])
        return replace(base, label=c["label"], desc=f"Your layout (look: {base.label})", position=c["position"],
                       preview=preview_of(c))
    return _builtin_get(name)


def all_layouts() -> list[dict]:
    """Built-ins first, then yours – for lists in the apps."""
    out = [{"id": l.id, "label": l.label, "desc": l.desc, "position": l.position, "custom": False} for l in LAYOUTS.values()]
    for lid, c in user_layouts().items():
        out.append({"id": lid, "label": c["label"], "desc": f"Your layout (look: {LAYOUTS[c['base']].label})",
                    "position": c["position"], "custom": True, "base": c["base"], "cfg": c})
    return out


def choices() -> list[tuple[str, str]]:                           # noqa: F811
    return [(l["label"], l["id"]) for l in all_layouts()]
