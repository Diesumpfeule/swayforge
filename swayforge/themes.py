"""Colour themes (bundled + ~/.config/swayforge/themes/*.toml)."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import paths, tomlw

COLOR_KEYS = ["crust", "mantle", "base", "surface", "surface2", "overlay", "text",
              "subtext", "accent", "accent2", "red", "green", "yellow", "orange",
              "blue", "magenta", "cyan"]
COLOR_LABELS = {
    "crust": "Deepest background", "mantle": "Panels / bar", "base": "Background",
    "surface": "Surfaces / buttons", "surface2": "Inactive borders", "overlay": "Muted / comments",
    "text": "Text", "subtext": "Muted text", "accent": "Accent", "accent2": "Accent 2",
    "red": "Red / errors", "green": "Green", "yellow": "Yellow", "orange": "Orange",
    "blue": "Blue", "magenta": "Magenta", "cyan": "Cyan",
}
ACCENT_CHOICES = ["accent", "accent2", "blue", "cyan", "green", "yellow", "orange",
                  "red", "magenta"]
# Style a theme may bring along (applied when you pick it, reverted when you switch away)
STYLE_KEYS = {"radius": ("look", "radius"), "layout": ("bar", "layout"),
              "font": ("theme", "font"), "font_size": ("theme", "font_size")}
WALLPAPER_STYLES = ["gradient", "gothic", "crt", "plain", "rust", "night", "wired", "cathedral"]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class Theme:
    id: str
    label: str
    dark: bool
    colors: dict[str, str]
    ansi: list[str]
    custom: bool = False
    style: dict = field(default_factory=dict)
    path: Path | None = None

    def with_accent(self, accent: str) -> dict[str, str]:
        c = dict(self.colors)
        if accent and accent in c:
            c["accent"] = c[accent]
        elif accent and HEX.match(accent):
            c["accent"] = accent
        return c

    @property
    def wallpaper_style(self) -> str:
        w = self.style.get("wallpaper", "gradient")
        return w if w in WALLPAPER_STYLES else "gradient"


def _load(path: Path, custom: bool) -> Theme | None:
    try:
        d = tomllib.loads(path.read_text())
        colors = d["colors"]
        missing = [k for k in COLOR_KEYS if k not in colors]
        if missing:
            raise KeyError(", ".join(missing))
        ansi = d.get("ansi") or [colors[k] for k in (
            "surface", "red", "green", "yellow", "blue", "magenta", "cyan", "subtext",
            "surface2", "red", "green", "yellow", "blue", "magenta", "cyan", "text")]
        style = dict(d.get("style", {}))
        if "bar_style" in style:                      # older theme files
            style["layout"] = {"floating": "modern"}.get(style.pop("bar_style"), "solid")
        return Theme(path.stem, d.get("label", path.stem), bool(d.get("dark", True)),
                     colors, list(ansi)[:16], custom, style, path)
    except (OSError, KeyError, tomllib.TOMLDecodeError) as e:
        print(f"swayforge: theme {path} ignored ({e})")
        return None


def all_themes() -> dict[str, Theme]:
    out: dict[str, Theme] = {}
    for p in sorted((paths.DATA / "themes").glob("*.toml")):
        if t := _load(p, False):
            out[t.id] = t
    if paths.USER_THEMES.is_dir():
        for p in sorted(paths.USER_THEMES.glob("*.toml")):
            if t := _load(p, True):
                out[t.id] = t
    return out


def get(name: str) -> Theme:
    themes = all_themes()
    return themes.get(name) or themes["catppuccin-mocha"]


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("ä", "ae").replace("ö", "oe")
               .replace("ü", "ue")).strip("-")
    return s or "my-theme"


def save_custom(label: str, base: Theme, colors: dict[str, str], ansi: list[str] | None = None,
                style: dict | None = None) -> Theme:
    """Save your own theme to ~/.config/swayforge/themes/<slug>.toml."""
    paths.ensure_dirs()
    tid = slug(label)
    data = {"label": label, "dark": base.dark, "ansi": list(ansi or base.ansi),
            "colors": {k: colors[k] for k in COLOR_KEYS},
            "style": dict(style if style is not None else base.style)}
    if not data["style"]:
        del data["style"]
    path = paths.USER_THEMES / f"{tid}.toml"
    path.write_text(f"# Your own theme – made with swayforge (based on {base.label})\n" + tomlw.dumps(data))
    return _load(path, True)  # type: ignore[return-value]


def apply_style(s: dict, new: Theme, old: Theme | None) -> list[str]:
    """Apply the new theme's style (e.g. square corners + retro font + Win98 layout).

    Your own values are remembered and restored as soon as you pick a theme without
    that style. If you changed a value yourself in the meantime, yours stays.
    Returns the options that changed."""
    stash: dict = s["theme"].setdefault("style_backup", {})
    old_style = old.style if old else {}
    changed = []
    for key, (sec, opt) in STYLE_KEYS.items():
        cur = s[sec].get(opt)
        set_by_old = key in old_style and cur == old_style[key]
        if key in new.style:
            if not set_by_old:
                stash[key] = cur              # your own value
            if cur != new.style[key]:
                s[sec][opt] = new.style[key]
                changed.append(opt)
        elif key in stash:
            prev = stash.pop(key)
            if set_by_old and cur != prev:
                s[sec][opt] = prev
                changed.append(opt)
    return changed
