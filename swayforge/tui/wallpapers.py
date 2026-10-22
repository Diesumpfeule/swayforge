"""Wallpapers page: browse your pictures with a real preview (kitty), set one, or download collections."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, OptionList, Select, SelectionList, Static
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from .. import kittyimg, paths, wallpacks
from .common import HOLD
from .panels import Panel
from .preview import KittyPreview

MAX_FILES = 4000


def scan(root: Path, limit: int = MAX_FILES) -> list[Path]:
    """Pictures below root (sub-folders included), sorted by relative path."""
    out: list[Path] = []
    if not root.is_dir():
        return out
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in fn:
            if Path(f).suffix.lower() in paths.WALLPAPER_EXT:
                out.append(Path(dp) / f)
                if len(out) >= limit:
                    return sorted(out, key=lambda p: str(p).lower())
    return sorted(out, key=lambda p: str(p).lower())


def mb(n: int) -> str:
    return f"{n / 1000:.1f} GB" if n >= 1000 else f"{n} MB"


class WallpapersPanel(Panel):
    TITLE = "Wallpapers"
    DEFAULT_CSS = """
    WallpapersPanel #wp_row { height: 18; }
    WallpapersPanel #wp_left { width: 42%; height: 18; }
    WallpapersPanel #wp_files { height: 1fr; }
    WallpapersPanel #wp_right { width: 1fr; height: 18; margin-left: 1; }
    WallpapersPanel KittyPreview { height: 1fr; }
    WallpapersPanel #wp_packs { height: 14; margin-top: 1; }
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.files: list[Path] = []
        self.shown: list[Path] = []
        self.current: Path | None = None
        self._timer = None

    def body(self) -> ComposeResult:
        st = kittyimg.status()
        yield Static("Pictures in your Wallpapers folder (sub-folders included). Pick one to see it here – "
                     "the preview is drawn by the kitty terminal, nothing else is needed."
                     + ("" if st.ok else f"\n[b]Preview is off:[/b] {escape(st.reason)}. "
                        "Everything else works."), classes="hint")
        yield Static("", id="wp_where", classes="hint")
        yield Static("", id="wp_current", classes="hint")
        with Horizontal(id="wp_row"):
            with Vertical(id="wp_left"):
                yield Input(placeholder="filter …", id="wpl_filter")
                yield OptionList(id="wp_files")
            with Vertical(id="wp_right"):
                yield KittyPreview(id="wp_prev")
                yield Static("", id="wp_info", classes="hint")
        yield Horizontal(Button("Set as wallpaper", id="wpl_set", variant="primary", disabled=True),
                         Button("Theme from wallpaper", id="wpl_theme", disabled=True),
                         Button("Open folder", id="wpl_folder"),
                         Button("↻", id="wpl_refresh", classes="small"), classes="btnrow")
        yield Static("[b]Theme from wallpaper[/b] builds a whole theme from the picture's colours (bar, terminal, "
                     "Rofi, GTK, LibreWolf …). It replaces the last “From wallpaper” theme; to keep one, name it on "
                     "the Theme page and press “Save as my theme”.", classes="hint")
        yield Horizontal(Select([("Dark or light: from the picture", "auto"), ("Always dark", "dark"),
                                 ("Always light", "light")], value="auto", allow_blank=False, id="wpt_mode"),
                         classes="btnrow")
        yield Horizontal(Button("Use the theme's own wallpaper", id="wpl_themewp"),
                         Button("Solid colour", id="wpl_solid"), classes="btnrow")
        yield Static("Collections", classes="section")
        yield Static("Optional downloads – swayforge does not ship these pictures. They come from the original "
                     "GitHub repositories (only the folders you tick) straight into your Wallpapers folder, "
                     "and show up above afterwards. Not my pictures: collections by other people – github.com/dharmx/walls and "
                     "github.com/D3Ext/aesthetic-wallpapers. [b]dharmx/walls[/b] has no stated licence (images belong to "
                     "their authors – fine as a private wallpaper); [b]D3Ext/aesthetic-wallpapers[/b] is MIT.",
                     classes="hint")
        yield SelectionList[str](id="wp_packs")
        yield Static("", id="wp_total", classes="hint")
        yield Horizontal(Button("Download selected …", id="wpl_get", variant="primary", disabled=True),
                         classes="btnrow")

    # ── data ────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self.fill_packs()
        self.show_current()

    def refresh_data(self) -> None:
        self.files = scan(paths.WALLPAPER_DIR)
        self.show_current()
        self.fill_files()
        self.fill_packs()

    def show_current(self) -> None:
        cur = str(self.app.s["theme"]["wallpaper"])    # type: ignore[attr-defined]
        what = {"theme": "the theme's own wallpaper", "solid": "a solid colour"}.get(cur, escape(Path(cur).name))
        self.query_one("#wp_current", Static).update(f"Current wallpaper: [b]{what}[/b]")

    def fill_files(self) -> None:
        q = self.query_one("#wpl_filter", Input).value.strip().lower()
        root = paths.WALLPAPER_DIR
        self.shown = [p for p in self.files if q in str(p.relative_to(root)).lower()] if q else list(self.files)
        ol = self.query_one("#wp_files", OptionList)
        ol.clear_options()
        ol.add_options([Option(escape(str(p.relative_to(root)))) for p in self.shown[:MAX_FILES]])
        where = str(root).replace(str(paths.HOME), "~")
        n = len(self.files)
        self.query_one("#wp_where", Static).update(
            f"{where}: {n} picture(s)" + (f", {len(self.shown)} match" if q else "")
            + (f" (showing the first {MAX_FILES})" if n >= MAX_FILES else "")
            + ("" if n else " – empty. Drop images in, or download a collection below."))
        for b in ("wpl_set", "wpl_theme"):
            self.query_one(f"#{b}", Button).disabled = True
        self.current = None
        self.query_one("#wp_prev", KittyPreview).clear("Select a picture to preview it.")
        self.query_one("#wp_info", Static).update("")

    def fill_packs(self) -> None:
        sl = self.query_one("#wp_packs", SelectionList)
        keep = set(sl.selected)
        sl.clear_options()
        for p in wallpacks.load():
            for c in p.categories:
                have = wallpacks.installed_count(p, c)
                tag = f"  [✓ {have} here]" if have else ""
                label = (f"{p.name}   all folders  ({c.files} files, {mb(c.mb)}){tag}" if c.id == "all"
                         else f"{p.name} › {c.id}  ({c.files} files, {mb(c.mb)}){tag}")
                key = wallpacks.key(p.id, c.id)
                sl.add_option(Selection(label.replace("[", "\\["), key, key in keep))
        self.update_total()

    def update_total(self) -> None:
        sel = self.query_one("#wp_packs", SelectionList).selected
        n = wallpacks.total_mb(sel)
        self.query_one("#wp_total", Static).update(
            f"{len(sel)} folder(s) selected, about {mb(n)} to download." if sel else "Nothing selected.")
        self.query_one("#wpl_get", Button).disabled = not sel

    # ── events ──────────────────────────────────────────────────────
    @on(Input.Changed, "#wpl_filter")
    def filtered(self, ev: Input.Changed) -> None:
        ev.stop()
        self.fill_files()

    @on(OptionList.OptionHighlighted, "#wp_files")
    def highlighted(self, ev: OptionList.OptionHighlighted) -> None:
        ev.stop()
        if ev.option_index >= len(self.shown):
            return
        self.current = self.shown[ev.option_index]
        for b in ("wpl_set", "wpl_theme"):
            self.query_one(f"#{b}", Button).disabled = False
        try:
            size = f"{self.current.stat().st_size / 1e6:.1f} MB"
        except OSError:
            size = "?"
        self.query_one("#wp_info", Static).update(escape(f"{self.current.name} · {size}"))
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(0.2, lambda p=self.current: self.query_one("#wp_prev", KittyPreview).show(str(p)))

    @on(SelectionList.SelectedChanged, "#wp_packs")
    def picked(self, ev) -> None:
        ev.stop()
        self.update_total()

    @on(Button.Pressed)
    def pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if not bid.startswith("wpl_"):
            return
        ev.stop()
        app = self.app
        if bid == "wpl_refresh":
            self.refresh_data()
        elif bid == "wpl_folder":
            paths.WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["xdg-open", str(paths.WALLPAPER_DIR)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif bid in ("wpl_themewp", "wpl_solid"):
            app.show_wallpaper("theme" if bid == "wpl_themewp" else "solid")
            self.show_current()
            app.refresh_hero()
            app.live_apply()
            app.changed()
        elif bid in ("wpl_set", "wpl_theme") and self.current:
            app.show_wallpaper(str(self.current))
            if bid == "wpl_theme":
                app.theme_from_wallpaper()
            else:
                app.refresh_hero()
                app.live_apply()
                app.changed()
                app.notify(f"Wallpaper: {self.current.name}")
            self.show_current()
        elif bid == "wpl_get":
            sel = self.query_one("#wp_packs", SelectionList).selected
            if sel:
                app.spawn_term(f"{wallpacks.script(sel)}; {HOLD}")
                app.notify("Downloading in a terminal – press ↻ when it's done", timeout=8)
