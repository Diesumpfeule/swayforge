"""Shared TUI pieces: colours from the active theme, form fields, swatches."""
from __future__ import annotations


from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select, Static, Switch

from .. import settings, themes
from ..fields import Field, coerce, path_from_wid  # noqa: F401 – re-exported for the TUI pages


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


UI_STYLES = ("win98", "winxp", "win7", "wired", "dread")


def use_layout(app, layout: str) -> None:
    """Button shapes follow the bar layout: bevels for Classic 98, glass for 7, text for Wired."""
    from .. import layouts
    layout = layouts.get(layout).id                  # your own layouts wear their base look
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


class AnimatedArt(Static):
    """ASCII art that glints and twinkles (see anim.py). Static when animate=False."""

    def __init__(self, lines: list[str], styles: dict[str, str], animate: bool = True, fps: int = 12,
                 motion: str | None = None, banner: bool = False, **kw) -> None:
        super().__init__("", **kw)
        self.lines, self.palette, self.animate, self.fps = lines, styles, animate, fps
        if motion is None:                       # default: what you picked in the settings
            try:
                motion = settings.load()["theme"].get("motion", "wave")
            except SystemExit:
                motion = "wave"
        self.motion = motion
        self.banner = banner                     # block lettering: moves as a whole, letters stay intact
        self._timer = None

    def on_mount(self) -> None:
        import time
        self._t0 = time.monotonic()
        self._draw()
        if self.animate:
            self._timer = self.set_interval(1 / self.fps, self._draw)

    def _draw(self) -> None:
        import time
        from ..anim import rich_frame
        t = (time.monotonic() - self._t0) if self.animate else 10_000.0
        self.update(rich_frame(self.lines, t + 3.0 if self.animate else t, self.palette,
                               motion=("float" if self.banner and self.motion == "wave" else self.motion)
                               if self.animate else "glint"))

    def set_motion(self, motion: str) -> None:
        self.motion = motion
        self._draw()

    def set_animate(self, on: bool) -> None:
        self.animate = on
        if on and self._timer is None:
            self._timer = self.set_interval(1 / self.fps, self._draw)
        elif not on and self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._draw()

    def set_art(self, lines: list[str], styles: dict[str, str] | None = None) -> None:
        self.lines = lines
        if styles:
            self.palette = styles
        self._draw()


def art_styles(c: dict[str, str], main: str = "accent", bold: bool = False) -> dict[str, str]:
    """Colours for AnimatedArt: face/shade from one theme colour, glint = text, sparks = yellow."""
    from ..render import mix
    b = "bold " if bold else ""
    return {"face": f"{b}{c[main]}", "shade": mix(c[main], c["base"], 0.5),
            "glint": f"bold {c['text']}", "hot": f"bold {c['yellow']}"}


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
    # one line per setting: the name, then the hint dimmed behind it (wraps only when it must)
    txt = Text(f.label)
    if f.help:
        txt.append("  " + f.help, style="dim")
    lab = Vertical(Label(txt, classes="flabel"), classes="flabelbox")
    edit = Button("✎", name=f"edit:{f.path}", classes="editbtn", tooltip="Open the responsible config file")
    return Horizontal(lab, widget, edit, classes="frow")


# Ends every task terminal. Line mode (Enter) instead of raw "any key": it doesn't depend on the tty
# state a finished installer/dnf leaves behind (stty sane), and it closes by itself after 3 minutes,
# so a window that lost keyboard focus never hangs around.
HOLD = "stty sane 2>/dev/null; echo; read -t 180 -rp 'Done – press Enter to close (closes itself after 3 min) '"


def section(title: str) -> Static:
    return Static(title, classes="section")


BASE_CSS = """
Screen { layout: vertical; }
#body { height: 1fr; }
#sidebar { width: 26; border-right: tall $panel; padding: 0; }
#sidebar > ListItem { padding: 0 1; height: 1; content-align: left middle; }
#sidebar > ListItem.navgroup { color: $text-muted; text-style: bold; margin-top: 1; background: transparent; }
#sidebar > ListItem Label { padding: 0; }
#pages { width: 1fr; }
.page { padding: 0 2; }
.pagetitle { text-style: bold; color: $accent; padding: 0 1; margin-bottom: 1; border-bottom: heavy $accent; }
.section { text-style: bold; color: $text; background: $panel; padding: 0 1; margin-top: 1; margin-bottom: 1; }
.frow { height: auto; margin-bottom: 0; padding: 0 0 0 1; }
/* zebra rows: every switch/field sits on the same band as its label */
.frow:odd { background: $panel 45%; }
.frow:hover { background: $accent 15%; }
.flabelbox { width: 1fr; height: auto; }
.flabel { padding-top: 0; }
.fhelp { color: $text-muted; }
.frow Input { width: 30; border: none; height: 1; padding: 0 1; background: $panel; }
.frow Input:focus { background: $accent 30%; }
.frow Select { width: 30; }
.frow Select > SelectCurrent { border: none; height: 1; padding: 0 1; background: $panel; }
.frow Select:focus > SelectCurrent { border: none; background: $accent 30%; }
.frow Switch { margin-right: 22; border: none; height: 1; padding: 0; width: 8; background: $panel; }
.frow Switch > .switch--slider { color: $text-muted; background: $panel; }
.frow Switch.-on > .switch--slider { color: $accent; background: $panel; }
.frow Switch:focus { background: $accent 30%; }
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
App.-ui-winxp Button { height: 3; border: round $accent 70%; background: $panel; color: $text; }
App.-ui-winxp Button:hover, App.-ui-winxp Button:focus { border: round $warning; }
App.-ui-winxp Button.-primary, App.-ui-winxp Button.-success { background: $success; color: $background; border: round $success-darken-2; }
App.-ui-win7 Button { height: 3; border: round $accent 50%; background: $panel; }
App.-ui-win7 Button:hover { border: round $accent; }
App.-ui-dread Button { height: 3; border: tall $accent 45%; background: $panel; color: $text; }
App.-ui-dread Button:hover, App.-ui-dread Button:focus { border: tall $accent; }
App.-ui-dread Button.-primary, App.-ui-dread Button.-success { background: $accent 55%; color: $text; }
App.-ui-wired Button { background: transparent; color: $accent; padding: 0 1; }
App.-ui-wired Button:hover, App.-ui-wired Button:focus { background: $accent; color: $background; }
App.-ui-wired Button.-primary, App.-ui-wired Button.-success { background: transparent; color: $accent;
         text-style: bold underline; }
.editbtn { min-width: 5; width: 5; margin-left: 1; margin-top: 0; background: $panel; padding: 0 1; }
App.-ui-win98 .editbtn, App.-ui-dread .editbtn, App.-ui-winxp .editbtn, App.-ui-win7 .editbtn { height: 1; border: none; margin-top: 1; }
App.-ui-win98 .small, App.-ui-dread .small, App.-ui-winxp .small, App.-ui-win7 .small { height: 1; border: none; }
.editbtn:hover { background: $accent; color: $background; }
.small { min-width: 5; width: 5; }
.volval { width: 7; padding: 0 1; }
ProgressBar { padding: 0 1; width: 30; }
.hint { color: $text-muted; padding: 0 1; margin-bottom: 1; border-left: tall $panel; }
.warn { color: $warning; padding-bottom: 0; }
.btnrow { height: auto; margin: 0; align: left middle; }
.btnrow Button { margin-right: 2; }
ThemeItem { height: 3; padding: 0 1; }
#statusbar { height: 1; background: $panel; padding: 0 2; color: $text-muted; }
"""
