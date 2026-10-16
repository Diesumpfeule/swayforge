"""Shared TUI pieces: colours from the active theme, form fields, swatches."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select, Static, Switch

from .. import settings, themes


def textual_theme(theme_id: str, accent: str = ""):
    """Textual theme from the system palette – the app looks like your desktop."""
    from textual.theme import Theme as TTheme
    t = themes.get(theme_id)
    c = t.with_accent(accent)
    return TTheme(
        name=f"sf-{t.id}-{(accent or 'def').lstrip('#')}", dark=t.dark,
        primary=c["accent"], secondary=c["accent2"], accent=c["accent"],
        background=c["base"], surface=c["mantle"], panel=c["surface"],
        foreground=c["text"], warning=c["yellow"], error=c["red"], success=c["green"],
    )


def use_theme(app, theme_id: str, accent: str = "", layout: str = "") -> None:
    th = textual_theme(theme_id, accent)
    app.register_theme(th)
    app.theme = th.name
    if layout:
        use_layout(app, layout)


UI_STYLES = ("win98", "win7", "wired")


def use_layout(app, layout: str) -> None:
    """Button shapes follow the bar layout: bevels for Classic 98, glass for 7, text for Wired."""
    for x in UI_STYLES:
        app.set_class(layout == x, f"-ui-{x}")


def two_tone(lines: list[str], face: str, shade: str) -> Text:
    """ASCII art with block faces in one colour and shading/shadow in another."""
    from ..ascii import SHADE
    txt = Text(no_wrap=True)
    for i, line in enumerate(lines):
        if i:
            txt.append("\n")
        for ch in line:
            txt.append(ch, style=shade if ch in SHADE else face)
    return txt


def hero_text(theme_id: str, accent: str = "", word: str = "swayforge", width: int = 78) -> Text:
    from ..ascii import best_banner
    from ..render import mix
    c = themes.get(theme_id).with_accent(accent)
    return two_tone(best_banner(word, width), f"bold {c['accent']}", mix(c["accent"], c["base"], 0.5))


def swatch(t: themes.Theme, width: int = 3) -> Text:
    txt = Text()
    for k in ("base", "surface", "accent", "accent2", "red", "green", "yellow", "blue", "magenta", "cyan"):
        txt.append(" " * width, style=f"on {t.colors[k]}")
    return txt


@dataclass
class Field:
    path: str
    label: str
    kind: str = "str"                 # str | int | float | bool | choice
    options: list[tuple[str, Any]] = field(default_factory=list)
    help: str = ""

    @property
    def wid(self) -> str:
        return "f__" + self.path.replace(".", "__")


def path_from_wid(wid: str) -> str:
    return wid[3:].replace("__", ".")


def field_row(f: Field, s: dict) -> Horizontal:
    value = settings.get(s, f.path)
    if f.kind == "bool":
        widget = Switch(value=bool(value), id=f.wid)
    elif f.kind == "choice":
        opts = [(label, v) for label, v in f.options]
        if value not in [v for _, v in opts]:
            opts.append((str(value), value))
        widget = Select(opts, value=value, allow_blank=False, id=f.wid)
    else:
        typ = {"int": "integer", "float": "number"}.get(f.kind, "text")
        widget = Input(value="" if value is None else str(value), type=typ, id=f.wid)
    lab = Vertical(Label(f.label, classes="flabel"),
                   *([Label(f.help, classes="fhelp")] if f.help else []), classes="flabelbox")
    edit = Button("✎", name=f"edit:{f.path}", classes="editbtn", tooltip="Open the responsible config file")
    return Horizontal(lab, widget, edit, classes="frow")


def coerce(f: Field, raw: Any) -> Any:
    if f.kind == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if f.kind == "float":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return raw


def section(title: str) -> Static:
    return Static(title, classes="section")


BASE_CSS = """
Screen { layout: vertical; }
#body { height: 1fr; }
#sidebar { width: 30; border-right: tall $panel; padding: 1 0; }
#sidebar > ListItem { padding: 0 2; height: 3; content-align: left middle; }
#sidebar > ListItem Label { padding: 1 0 0 0; }
#pages { width: 1fr; }
.page { padding: 1 3; }
.pagetitle { text-style: bold; color: $accent; padding-bottom: 1; }
.section { text-style: bold; color: $secondary; margin-top: 1; padding-bottom: 1;
           border-bottom: solid $panel; }
.frow { height: auto; margin-bottom: 1; }
.flabelbox { width: 1fr; height: auto; }
.flabel { padding-top: 1; }
.fhelp { color: $text-muted; }
.frow Input { width: 36; }
.frow Select { width: 36; }
.frow Switch { margin-right: 26; }
/* ── Buttons: compact by default, shaped by the layout (App.-ui-<layout>) ── */
Button { height: 1; min-width: 6; border: none; padding: 0 2; background: $panel; color: $text;
         text-style: bold; }
Button:hover { background: $accent 35%; }
Button:focus { background: $accent 55%; text-style: bold; }
Button.-primary, Button.-success { background: $accent; color: $background; }
Button.-primary:hover, Button.-success:hover { background: $accent 80%; }
Button.-warning { background: $warning 75%; color: $background; }
Button.-error { background: $error 80%; color: $background; }
Button:disabled { background: $panel 50%; color: $text-muted; }
App.-ui-win98 Button { height: 3; border: outer $panel-lighten-2; background: $panel; color: $text; }
App.-ui-win98 Button.-active, App.-ui-win98 Button:focus { border: inner $panel-lighten-2; }
App.-ui-win98 Button.-primary, App.-ui-win98 Button.-success { background: $accent; color: $background;
         border: outer $accent-lighten-2; }
App.-ui-win7 Button { height: 3; border: round $accent 50%; background: $panel; }
App.-ui-win7 Button:hover { border: round $accent; }
App.-ui-wired Button { background: transparent; color: $accent; padding: 0 1; }
App.-ui-wired Button:hover, App.-ui-wired Button:focus { background: $accent; color: $background; }
App.-ui-wired Button.-primary, App.-ui-wired Button.-success { background: transparent; color: $accent;
         text-style: bold underline; }
.editbtn { min-width: 5; width: 5; margin-left: 1; margin-top: 1; background: $panel; padding: 0 1; }
App.-ui-win98 .editbtn, App.-ui-win7 .editbtn { height: 1; border: none; margin-top: 1; }
App.-ui-win98 .small, App.-ui-win7 .small { height: 1; border: none; }
.editbtn:hover { background: $accent; color: $background; }
.small { min-width: 5; width: 5; }
.volval { width: 7; padding: 1 1; }
ProgressBar { padding: 1 1; width: 30; }
.hint { color: $text-muted; padding-bottom: 1; }
.warn { color: $warning; padding-bottom: 1; }
.btnrow { height: auto; margin: 1 0; align: left middle; }
.btnrow Button { margin-right: 2; }
ThemeItem { height: 3; padding: 0 1; }
#statusbar { height: 1; background: $panel; padding: 0 2; color: $text-muted; }
"""
