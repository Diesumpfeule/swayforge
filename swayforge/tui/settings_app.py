"""swayforge settings – like KDE's System Settings, but for Sway and in the terminal."""
from __future__ import annotations

import copy
import os
import shlex
import subprocess
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import (Button, ContentSwitcher, Footer, Header, Input, Label, ListItem,
                             ListView, Select, SelectionList, Static, Switch, TextArea)
from textual.widgets.selection_list import Selection

from .. import ascii as asc
from .. import boot, layouts, paths, render, settings, themes
from ..system import detect, have, run
from .common import (BASE_CSS, HOLD, AnimatedArt, Field, art_styles, coerce, field_row, path_from_wid, section, swatch,
                     use_layout, use_theme)
from .games import GamesPanel
from .maintenance import AboutPanel, AppsPanel, CleanupPanel, MountsPanel
from .wallpapers import WallpapersPanel
from ..fields import FIELDS, ON_OFF, PAGES, SAVER_OPTS  # noqa: F401
from .panels import AudioPanel, BluetoothPanel, NetworkPanel

# Sidebar chapters (page ids from PAGES)
NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("LOOK", ["theme", "wallpapers", "layout", "look", "bar"]),
    ("DEVICES", ["display", "audio", "sound", "bluetooth", "network", "input"]),
    ("WORK & PLAY", ["shell", "keys", "apps", "games"]),
    ("SYSTEM", ["power", "boot", "security", "cleanup", "mounts", "system", "about"]),
]


def nav_items(start: str) -> tuple[list, int]:
    """Sidebar entries with chapter headers; returns (items, index of the start page)."""
    labels = dict(PAGES)
    items, idx = [], 0
    for title, pids in NAV_GROUPS:
        items.append(ListItem(Label(title), classes="navgroup", disabled=True))
        for pid in pids:
            if pid == start:
                idx = len(items)
            items.append(ListItem(Label(labels[pid]), id=f"nav-{pid}"))
    return items, idx


# Fields a theme style can change → refresh the form after a theme switch
STYLE_PATHS = ["look.radius", "theme.font", "theme.font_size"]

class ThemeItem(ListItem):
    def __init__(self, t: themes.Theme) -> None:
        super().__init__(name=t.id)
        self.t = t

    def compose(self) -> ComposeResult:
        tag = "  (yours)" if self.t.custom else ("  ▣ retro" if self.t.style.get("radius") == 0 else "")
        yield Horizontal(Label(f"{self.t.label + tag:<40}"), Label(swatch(self.t)))


class LayoutItem(ListItem):
    def __init__(self, lay: layouts.Layout) -> None:
        super().__init__(name=lay.id)
        self.lay = lay

    def compose(self) -> ComposeResult:
        yield Label(f"[b]{self.lay.label:<16}[/b] [dim]{self.lay.desc}[/]")


class SettingsApp(App):
    ENABLE_COMMAND_PALETTE = False      # Textual's Ctrl+P command search – not useful here
    TITLE = "swayforge"
    SUB_TITLE = "Settings"
    CSS = BASE_CSS + """
    #ap_table { height: 24; margin-bottom: 1; }
    #wpt_mode { width: 40; }
    #mt_drive { width: 1fr; }
    #mt_name { width: 1fr; }
    .mtrow { width: 1fr; }
    #ap_filter { width: 30; }
    #ap_group { width: 28; }
    #ap_sum { padding: 0; }
    #cl_items { height: auto; }
    .clrow { height: auto; }
    .clcheck { width: 52; height: auto; border: none; background: transparent; padding: 0; }
    .clcheck:focus { background: transparent; }
    .clcheck > .toggle--button { color: $panel; background: $panel; }
    .clcheck.-on > .toggle--button { color: $background; background: $accent; text-style: bold; }
    .cldesc { width: 1fr; }
    #wp_drive, #wp_mode, #wp_fs { width: 1fr; }
    #wp_label { width: 20; }
    #hero { height: auto; margin-bottom: 1; }
    #hero_banner { width: auto; height: auto; margin: 1 0; }
    #hero_art { width: auto; margin-right: 4; }
    #hero_intro { width: 1fr; padding-top: 1; }
    #themelist { height: auto; max-height: 18; border: round $panel; margin-bottom: 1; }
    #themelist > ThemeItem { height: 1; padding: 0 1; }
    ThemeItem Horizontal { height: 1; }
    ThemeItem Label { width: auto; }
    #layoutlist { height: auto; border: round $panel; margin-bottom: 1; }
    #layoutlist > LayoutItem { height: 1; padding: 0 1; }
    .preview { border: round $accent; padding: 1 2; margin-bottom: 1; height: auto; color: $text; }
    #keylist .frow Input { width: 30; }
    #outputs { height: auto; }
    #outputs .outbox { border: round $panel; padding: 0 1; margin-bottom: 1; height: auto; }
    #autostart { height: 6; }
    #sections { height: 16; width: 50; }
    #backuplist { height: 8; border: round $panel; }
    #reportlist { height: auto; max-height: 10; border: round $panel; }
    #sec_out { border: round $panel; padding: 0 1; height: auto; max-height: 24; overflow-y: auto; }
    #sec_path { width: 1fr; margin-right: 2; }
    #sec_drive { width: 40; margin-right: 2; }
    #colors { grid-size: 2; grid-gutter: 0 2; height: auto; }
    .colrow { height: 3; }
    .colrow Label { width: 24; padding-top: 1; }
    .colrow .sw { width: 6; height: 1; margin: 1 1 0 0; }
    .colrow Input { width: 14; }
    .filerow { height: 3; }
    .filerow Label { width: 1fr; padding-top: 1; }
    .filerow Button { min-width: 10; }
    #bt_list, #net_list { height: 12; border: round $panel; margin-bottom: 1; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save", "Save & apply", priority=True),
        Binding("ctrl+l", "redraw", "Redraw", priority=True),
        Binding("ctrl+q", "quit_app", "Quit", priority=True),
        Binding("escape", "quit_app", "Quit", show=False),
    ]

    def action_redraw(self) -> None:
        """Repaint everything – for when the terminal shows leftovers after resizing."""
        self.refresh(repaint=True, layout=True)
        self.screen.refresh(repaint=True, layout=True)
        self.notify("Redrawn", timeout=1)

    def __init__(self, page: str = "") -> None:
        super().__init__()
        self.s = settings.load()
        self.saved = copy.deepcopy(self.s)
        self.si = detect()
        self.all_themes = themes.all_themes()
        self._fields = {f.wid: f for fs in FIELDS.values() for f in fs if isinstance(f, Field)}
        self._quit_armed = False
        self._loading = True
        self.start_page = page if page in dict(PAGES) else "theme"

    # ── Building ────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            items, idx = nav_items(self.start_page)
            yield ListView(*items, id="sidebar", initial_index=idx)
            with ContentSwitcher(initial=f"page-{self.start_page}", id="pages"):
                yield self.page_theme()
                yield WallpapersPanel(id="page-wallpapers", classes="page")
                yield self.page_layout()
                yield self.page_fields("look")
                yield self.page_fields("bar")
                yield self.page_display()
                yield AudioPanel(id="page-audio", classes="page")
                yield BluetoothPanel(id="page-bluetooth", classes="page")
                yield NetworkPanel(id="page-network", classes="page")
                yield self.page_fields("sound")
                yield self.page_fields("input")
                yield self.page_shell()
                yield self.page_keys()
                yield GamesPanel(id="page-games", classes="page")
                yield self.page_power()
                yield self.page_boot()
                yield self.page_security()
                yield AppsPanel(id="page-apps", classes="page")
                yield CleanupPanel(id="page-cleanup", classes="page")
                yield MountsPanel(id="page-mounts", classes="page")
                yield self.page_system()
                yield AboutPanel(id="page-about", classes="page")
        yield Static("", id="statusbar")
        yield Footer()

    def page(self, pid: str, *children) -> VerticalScroll:
        title = dict(PAGES)[pid].split("  ", 1)[-1]
        return VerticalScroll(Static(title, classes="pagetitle"), *children, id=f"page-{pid}", classes="page")

    def fields(self, pid: str) -> list:
        return [section(f) if isinstance(f, str) else field_row(f, self.s) for f in FIELDS[pid]]

    def page_fields(self, pid: str) -> VerticalScroll:
        extra = [Static("✎ opens the file where you can fine-tune this further. "
                        "Whatever you put there always wins.", classes="hint")]
        if pid == "look" and not self.si.swayfx:
            extra.append(Static("SwayFX is not installed – effects and rounded windows need it "
                                "(installer → Sway desktop → SwayFX).", classes="hint"))
        return self.page(pid, *extra, *self.fields(pid))

    # Theme page with ASCII hero and colour editor
    def page_theme(self) -> VerticalScroll:
        items = [ThemeItem(t) for t in self.all_themes.values()]
        ids = list(self.all_themes)
        current = ids.index(self.s["theme"]["name"]) if self.s["theme"]["name"] in ids else 0
        accent_opts = [("Theme default", "")] + [(k, k) for k in themes.ACCENT_CHOICES[1:]]
        t = themes.get(self.s["theme"]["name"])
        rows = [Horizontal(Label(themes.COLOR_LABELS[k]), Static(" ", classes="sw", id=f"sw__{k}"),
                           Input(t.colors[k], id=f"col__{k}", max_length=7), classes="colrow")
                for k in themes.COLOR_KEYS]
        art_opts = [("Theme's motif", "auto")] + [(n, n) for n in asc.all_art()]
        return self.page(
            "theme",
            AnimatedArt(asc.best_banner("swayforge", 78), art_styles(t.with_accent(self.s["theme"]["accent"]),
                                                                      bold=True),
                        animate=self.s["theme"]["animate"], id="hero_banner"),
            Horizontal(AnimatedArt(asc.art(asc.resolve(self.s, t)),
                                   art_styles(t.with_accent(self.s["theme"]["accent"]), "accent2"),
                                   animate=self.s["theme"]["animate"], id="hero_art"),
                       Static("One click recolours everything: Sway, bar, Rofi, terminal, prompt, fastfetch, "
                              "GTK apps, lock screen, notifications, btop, cava, MangoHud and the boot/login "
                              "screens.\n\nRetro themes also bring square corners, a retro font and their own "
                              "layout.", classes="hint", id="hero_intro"), id="hero"),
            section("Colour theme"),
            ListView(*items, id="themelist", initial_index=current),
            section("Accent & ASCII art"),
            field_row(Field("theme.accent", "Accent colour", "choice", accent_opts), self.s),
            field_row(Field("theme.ascii", "ASCII art", "choice", art_opts,
                            help="fastfetch, login, boot screen · add your own in ~/.config/swayforge/ascii"),
                      self.s),
            field_row(Field("theme.animate", "Animate the ASCII art", "bool",
                            help="glint + twinkling sparks · terminal greeting · LibreWolf"), self.s),
            section("Edit colours → your own theme"),
            Static("Everything else (gaps, font, bar, shortcuts …) stays when you switch themes. "
                   "Colours are changed here: edit, give it a name, save – it then shows up above as "
                   "your own theme. Tip: “Clean” is a neutral starting point.", classes="hint"),
            Grid(*rows, id="colors"),
            Horizontal(Input(placeholder="Name, e.g. My Retro", id="custom_name",
                             value=t.label if t.custom else ""),
                       Button("Save as my theme", id="theme_save", variant="success"), classes="btnrow"),
            Horizontal(Button("Reset colours", id="theme_reset"),
                       Button("Open theme file ✎", id="theme_file"), classes="btnrow"),
        )

    def page_layout(self) -> VerticalScroll:
        cur = layouts.get(self.s["bar"]["layout"])
        ids = list(layouts.LAYOUTS)
        noctalia = self.s["general"].get("shell") == "noctalia"
        opacity = Field("look.ui_opacity", "Transparency", "choice",
                        [("Off – layout default", 1.0)] + [(f"{n}% see-through", round(1 - n / 100, 2))
                                                           for n in (10, 20, 30, 40, 50, 60, 70, 80)],
                        help="bar, launcher, notifications · turns blur off so the wallpaper shows")
        return self.page(
            "layout",
            section("Layout"),
            Static("Sets how the bar, launcher, notifications and GTK buttons look. Mix it with any colour "
                   "theme. Quick switch: " + self.s.get("keys", {}).get(
                       "layout_next", next(k for a, _, k, _ in settings.KEY_ACTIONS if a == "layout_next")
                   ).replace("$mod", "Super") + ".", classes="hint"),
            ListView(*[LayoutItem(l) for l in layouts.LAYOUTS.values()], id="layoutlist",
                     initial_index=ids.index(cur.id)),
            Static(cur.preview, id="layout_preview", classes="preview", markup=False),
            section("Transparency"),
            field_row(opacity, self.s),
            Static("Islands and plain bars fade their background; bevelled retro bars fade as a whole. "
                   "Blur needs SwayFX (Appearance).", classes="hint"),
            section("Desktop shell"),
            Static(("Noctalia runs the bar and notifications; swayforge's bar is off."
                    if noctalia else "swayforge's own bar and notifications are on."), id="shell_state"),
            Horizontal(Button("Switch back to swayforge's bar" if noctalia else "Run Noctalia instead (bar off)",
                              id="shell_toggle", variant="primary"), classes="btnrow"),
            Static("Needs Noctalia installed (sudo dnf install noctalia). Theme, wallpaper and shortcuts "
                   "keep working.", classes="hint"),
            Static("Individual bar modules: see “Bar modules”.", classes="hint"),
        )

    def page_display(self) -> VerticalScroll:
        children: list = [section("Games"), field_row(Field("display.allow_tearing", "Allow tearing in games", "bool",
                                          help="lower input lag in fullscreen games"), self.s)]
        outs = self.si.outputs
        if not outs:
            children.append(Static("Displays can only be detected inside Sway. Open the settings "
                                   "in Sway with Super+I.", classes="warn"))
        else:
            main_opts = [(f"{o['name']}  {o.get('make', '')} {o.get('model', '')}".strip(), self.output_key(o))
                         for o in outs]
            cur_main = self.s["display"].get("primary") or ""
            if cur_main not in [v for _, v in main_opts]:
                cur_main = main_opts[0][1]
            children.append(section("Screens"))
            children.append(Horizontal(
                Vertical(Label("Main screen", classes="flabel"),
                         Label("workspace 1 opens here, and games (XWayland) see it as the primary monitor",
                               classes="fhelp"), classes="flabelbox"),
                Select(main_opts, value=cur_main, allow_blank=False, id="out_primary"), classes="frow"))
            children.append(Static("Position: x y in pixels. Right of a 2560 px wide monitor = 2560 0. "
                                   "With scaling, use the scaled width.", classes="hint"))
            boxes = []
            for n, o in enumerate(outs):
                key = self.output_key(o)
                cfg = self.s["display"]["outputs"].get(key, {})
                modes = []
                for m in o.get("modes", []):
                    ms = f"{m['width']}x{m['height']}@{m['refresh'] / 1000:.3f}Hz"
                    lab = f"{m['width']}×{m['height']} @ {m['refresh'] / 1000:.0f} Hz"
                    if ms not in [v for _, v in modes]:
                        modes.append((lab, ms))
                modes.sort(key=lambda x: (-int(x[1].split("x")[0]), -float(x[1].split("@")[1][:-2])))
                cur = o.get("current_mode") or {}
                cur_s = f"{cur.get('width')}x{cur.get('height')}@{cur.get('refresh', 0) / 1000:.3f}Hz" if cur else ""
                mode_val = cfg.get("mode") or cur_s or (modes[0][1] if modes else "")
                if mode_val not in [v for _, v in modes]:
                    modes.insert(0, (mode_val, mode_val))
                rect = o.get("rect", {})
                boxes.append(Vertical(
                    Label(f"[b]{o['name']}[/b]  {o.get('make', '')} {o.get('model', '')}"),
                    Horizontal(Label("Enabled", classes="flabel flabelbox"),
                               Switch(value=cfg.get("enabled", True), id=f"out{n}_enabled"), classes="frow"),
                    Horizontal(Label("Resolution & refresh rate", classes="flabel flabelbox"),
                               Select(modes, value=mode_val, allow_blank=False, id=f"out{n}_mode"), classes="frow"),
                    Horizontal(Label("Scale", classes="flabel flabelbox"),
                               Input(str(cfg.get("scale", o.get("scale", 1.0))), type="number", id=f"out{n}_scale"),
                               classes="frow"),
                    Horizontal(Label("Position (x y)", classes="flabel flabelbox"),
                               Input(cfg.get("pos", f"{rect.get('x', 0)} {rect.get('y', 0)}"), id=f"out{n}_pos"),
                               classes="frow"),
                    Horizontal(Label("FreeSync / adaptive sync", classes="flabel flabelbox"),
                               Switch(value=cfg.get("adaptive_sync", o.get("adaptive_sync_status") == "enabled"),
                                      id=f"out{n}_vrr"), classes="frow"),
                    classes="outbox"))
            children.append(Vertical(*boxes, id="outputs"))
        return self.page("display", *children)

    @staticmethod
    def output_key(o: dict) -> str:
        ident = " ".join(x for x in (o.get("make"), o.get("model"), o.get("serial")) if x and x != "Unknown")
        return ident or o["name"]

    def page_shell(self) -> VerticalScroll:
        children = self.fields("shell")
        sel = self.s["prompt"]["sections"]
        children.append(section("Prompt sections"))
        children.append(Static("What the prompt shows (order is fixed).", classes="hint"))
        children.append(SelectionList[str](*[Selection(x, x, x in sel) for x in settings.PROMPT_SECTIONS],
                                           id="sections"))
        if not have(self.s["general"]["terminal"]):
            children.insert(0, Static(f"{self.s['general']['terminal']} is not installed.", classes="warn"))
        return self.page("shell", *children)

    def page_keys(self) -> VerticalScroll:
        rows = []
        over = self.s.get("keys", {})
        for aid, label, key, _cmd in settings.KEY_ACTIONS:
            rows.append(Horizontal(Label(label, classes="flabel flabelbox"),
                                   Input(over.get(aid, key), id=f"key__{aid}"),
                                   Button("✎", name="edit:general.keys", classes="editbtn"), classes="frow"))
        return self.page(
            "keys", *self.fields("keys"),
            section("Shortcuts"),
            Static("$mod = main modifier. Empty field = shortcut off. Extra shortcuts of your own go "
                   "into ~/.config/sway/custom.conf (✎).", classes="hint"),
            Vertical(*rows, id="keylist"),
            Horizontal(Button("Reset all", id="keys_reset"), classes="btnrow"),
            section("Autostart"),
            Static("One command per line, e.g. discord --start-minimized or steam -silent", classes="hint"),
            TextArea("\n".join(self.s["autostart"]["extra"]), id="autostart"),
        )

    def page_power(self) -> VerticalScroll:
        children = self.fields("power")
        children[2:2] = [Static("It starts after “Lock after (minutes)” below; the first key or mouse move locks the screen. "
                                "Set “Screen off after” higher than “Lock after”. cmatrix is the real program "
                                "(Apps page → cmatrix); without it the built-in Matrix is used.", classes="hint"),
                         Horizontal(Button("Preview screensaver", id="sv_preview"), classes="btnrow")]
        if have("powerprofilesctl"):
            cur = run(["powerprofilesctl", "get"]).stdout.strip()
            avail = [l.strip().rstrip(":").lstrip("* ").strip()
                     for l in run(["powerprofilesctl", "list"]).stdout.splitlines() if l.strip().endswith(":")]
            names = {"performance": "Performance", "balanced": "Balanced", "power-saver": "Power saver"}
            opts = [(names.get(a, a), a) for a in avail] or [("Balanced", "balanced")]
            if cur and cur not in [v for _, v in opts]:
                opts.append((cur, cur))
            children[4:4] = [section("Power profile (applies immediately)"),
                             Horizontal(Label("Profile", classes="flabel flabelbox"),
                                        Select(opts, value=cur or opts[0][1], allow_blank=False, id="ppd"),
                                        classes="frow")]
        return self.page("power", *children)

    def page_boot(self) -> VerticalScroll:
        ctx = render.make_ctx(self.s, self.si)
        cur = boot.style_for(ctx)
        style_opts = [("Theme's style", "auto")] + [(label, k) for k, (label, _) in boot.STYLES.items()]
        greeter = run(["systemctl", "is-enabled", "greetd"]).stdout.strip() if have("systemctl") else ""
        state = ("[green]active[/]" if greeter == "enabled" else "[yellow]not installed yet[/]")
        return self.page(
            "boot",
            section("Boot screen (Plymouth)"),
            field_row(Field("boot.style", "Style", "choice", style_opts), self.s),
            field_row(Field("boot.text", "Banner text", help="empty = your host name"), self.s),
            Static(boot.PREVIEWS[cur], id="boot_preview", classes="preview", markup=False),
            Static("Uses your theme colours, font and ASCII art. Installing rebuilds the initramfs "
                   "(about a minute) – re-run it after changing the theme if you want them to match.",
                   classes="hint"),
            Horizontal(Button("Install boot screen", id="boot_apply", variant="primary"), classes="btnrow"),
            *self.fields("boot"),
            Static(f"tuigreet: {state}. Keyboard-only text login with your ASCII art and theme colours "
                   "(the Linux console only knows 16 colours, so they are approximated).", classes="hint"),
            Horizontal(Button("Install login screen", id="login_apply", variant="primary"),
                       Button("Back to SDDM", id="login_restore", variant="warning"), classes="btnrow"),
        )

    def page_security(self) -> VerticalScroll:
        from .. import security
        inst = security.installed()
        age = security.signature_age_days()
        ok, no, warn = "[green]✓[/]", "[dim]✗[/]", "[yellow]![/]"
        status = [f"{ok if inst[t] else no} {label}" for t, label in security.TOOLS.items()]
        if inst["clamscan"]:
            status.append(f"{warn if age is None or age > 7 else ok} virus signatures: "
                          + ("none yet – Update signatures" if age is None else
                             f"{age:.0f} day(s) old" if age >= 1 else "up to date"))
        drives = security.removable_drives()
        drive_opts = [(f"{d['label']} ({d['size']}) – {d['mount']}", d["mount"]) for d in drives]
        reps = security.reports()
        missing = not inst["clamscan"]
        return self.page(
            "security",
            Static("Free scanners from the Fedora repos. Linux malware is rare – ClamAV mostly finds "
                   "Windows malware in downloads and on USB sticks, which is exactly what you don't want to "
                   "pass on. Nothing is deleted automatically; every run leaves a report.", classes="hint"),
            Static("\n".join(status), id="sec_status"),
            *([Static("[yellow]Scanners not installed:[/] installer → IT & Security → Malware & rootkit "
                      "scanners, or the button below.", classes="hint")] if missing else []),
            section("Malware scan (ClamAV)"),
            Horizontal(Button("Scan Downloads", id="sec_dl", variant="primary"),
                       Button("Scan home folder", id="sec_home"),
                       Button("Update signatures", id="sec_fresh"),
                       *([Button("Install scanners", id="sec_install", variant="warning")] if missing else []),
                       classes="btnrow"),
            Horizontal(Select(drive_opts, prompt="no USB drive mounted" if not drives else "USB drive …",
                              id="sec_drive", disabled=not drives),
                       Button("Scan drive", id="sec_drive_scan", disabled=not drives),
                       Button("↻", id="sec_refresh", classes="small"), classes="btnrow"),
            Horizontal(Input(placeholder="any folder or file, e.g. ~/Games/setup.exe", id="sec_path"),
                       Button("Scan path", id="sec_path_scan"), classes="btnrow"),
            section("Rootkits & system audit (needs your password)"),
            Static("rkhunter + chkrootkit look for rootkits and backdoors. Lynis checks how well the system "
                   "is hardened and gives tips. Both report false alarms now and then – read before you act.",
                   classes="hint"),
            Horizontal(Button("Rootkit check", id="sec_rootkit", variant="primary"),
                       Button("System audit (Lynis)", id="sec_audit"),
                       Button("Open quarantine", id="sec_quar"), classes="btnrow"),
            section("Devices & connections"),
            Horizontal(Button("USB devices", id="sec_ov_usb"), Button("Drives", id="sec_ov_drives"),
                       Button("Open ports", id="sec_ov_ports"), Button("Autostart", id="sec_ov_autostart"),
                       classes="btnrow"),
            Static("Pick an overview above.", id="sec_out", markup=False),
            section("Reports"),
            ListView(*[ListItem(Label(security.describe(r, s)), name=str(r)) for r, s in reps] or
                     [ListItem(Label("none yet"))], id="reportlist"),
            Horizontal(Button("Open report", id="sec_report"), classes="btnrow"),
            *self.fields("security"),
        )

    def page_system(self) -> VerticalScroll:
        backups = sorted((d for d in paths.BACKUP_DIR.iterdir() if d.is_dir()), reverse=True) \
            if paths.BACKUP_DIR.is_dir() else []
        files = [Horizontal(Label(f"{label}  [dim]{str(p).replace(str(paths.HOME), '~')}[/]"),
                            Button("Open ✎", name=f"file:{key}"), classes="filerow")
                 for key, (label, p) in render.CONFIG_FILES.items()]
        return self.page(
            "system",
            section("System"),
            Horizontal(Button("Update system", id="sys_update", variant="primary"),
                       Button("Update swayforge + wolfforge", id="sys_selfupdate"),
                       Button("Install/remove apps", id="sys_installer"),
                       Button("Check firmware", id="sys_fw"), classes="btnrow"),
            section("All config files"),
            Static("Generated files contain the line “swayforge generated”. Delete it and you take the "
                   "file over – swayforge leaves it alone from then on.", classes="hint"),
            *files,
            section("Feed in an existing Sway config"),
            Static("Shortcuts, rules and autostarts go into custom.conf. Colours, font, bar and wallpaper "
                   "keep coming from the theme.", classes="hint"),
            Horizontal(Input(placeholder="~/Downloads/config", id="import_path"),
                       Button("Import", id="sys_import"), classes="btnrow"),
            section("Back up for the next reset"),
            Static("Saves settings, app selection, your themes, ASCII art, tweaks and the CS2 translator. "
                   "After a reset: ./install.sh --restore FILE", classes="hint"),
            Horizontal(Input(str(paths.HOME / "swayforge-backup.tar.gz"), id="export_path"),
                       Button("Export", id="sys_export", variant="success"), classes="btnrow"),
            section("Automatic backups of old configs"),
            ListView(*[ListItem(Label(d.name), name=str(d)) for d in backups[:30]] or
                     [ListItem(Label("none yet"))], id="backuplist"),
            Horizontal(Button("Restore selected", id="sys_restore", variant="warning"),
                       Button("Open folder", id="sys_open_backup"), classes="btnrow"),
        )

    def on_mount(self) -> None:
        use_theme(self, self.s["theme"]["name"], self.s["theme"]["accent"], self.s["bar"]["layout"])
        self.update_swatches()
        self.status()
        self.set_timer(0.6, self._done_loading)

    def _done_loading(self) -> None:
        self._loading = False

    # ── State ───────────────────────────────────────────────────────
    @property
    def dirty(self) -> bool:
        return self.s != self.saved

    def status(self, msg: str = "") -> None:
        t = self.all_themes.get(self.s["theme"]["name"])
        lay = layouts.get(self.s["bar"]["layout"])
        info = (f"Theme: {t.label if t else '?'}  │  Layout: {lay.label}  │  "
                f"{'● unsaved – Ctrl+S' if self.dirty else '✓ saved'}")
        if self.si.swayfx:
            info += "  │  SwayFX"
        self.query_one("#statusbar", Static).update(f"{info}   {msg}")

    def changed(self) -> None:
        self._quit_armed = False
        self.status()

    def set_widget(self, path: str) -> None:
        """Set a form field to the current settings value (without a change event)."""
        wid = "f__" + path.replace(".", "__")
        val = settings.get(self.s, path)
        for w in self.query(f"#{wid}"):
            with self.prevent(Input.Changed, Select.Changed, Switch.Changed):
                if isinstance(w, Input):
                    w.value = str(val)
                elif isinstance(w, (Select, Switch)):
                    try:
                        w.value = val
                    except Exception:
                        pass

    def refresh_hero(self) -> None:
        t = themes.get(self.s["theme"]["name"])
        c = t.with_accent(self.s["theme"]["accent"])
        self.query_one("#hero_art", AnimatedArt).set_art(asc.art(asc.resolve(self.s, t)), art_styles(c, "accent2"))
        self.query_one("#hero_banner", AnimatedArt).set_art(asc.best_banner("swayforge", 78),
                                                           art_styles(c, bold=True))
        ctx = render.make_ctx(self.s, self.si)
        self.query_one("#boot_preview", Static).update(boot.PREVIEWS[boot.style_for(ctx)])

    # ── Navigation ──────────────────────────────────────────────────
    @on(ListView.Highlighted, "#sidebar")
    def nav(self, ev: ListView.Highlighted) -> None:
        if ev.item and ev.item.id:
            pid = ev.item.id[4:]
            self.query_one("#pages", ContentSwitcher).current = "page-" + pid
            if pid in ("audio", "bluetooth", "network") and not self._loading:
                self.query_one(f"#page-{pid}").refresh_data()   # type: ignore[attr-defined]

    # ── Form fields ─────────────────────────────────────────────────
    def _set_field(self, wid: str, raw) -> None:
        if self._loading or not wid.startswith("f__"):
            return
        f = self._fields.get(wid) or Field(path_from_wid(wid), "", "choice")
        val = coerce(f, raw)
        if val is None or settings.get(self.s, f.path) == val:
            return
        settings.set_(self.s, f.path, val)
        if f.path == "theme.accent":
            use_theme(self, self.s["theme"]["name"], val, self.s["bar"]["layout"])
            self.refresh_hero()
            self.live_apply()
        elif f.path == "theme.animate":
            for w in self.query(AnimatedArt):
                w.set_animate(bool(val))
            self.live_apply()
        elif f.path == "look.ui_opacity":
            self.live_apply()
        elif f.path in ("theme.wallpaper", "theme.ascii"):
            self.refresh_hero()
            self.live_apply()
        elif f.path == "boot.style":
            self.refresh_hero()
        elif f.path == "general.terminal" and not have(val):
            self.notify(f"{val} is not installed yet: sudo dnf install {val}", severity="warning")
        self.changed()

    @on(Input.Changed)
    def input_changed(self, ev: Input.Changed) -> None:
        wid = ev.input.id or ""
        if wid.startswith("key__"):
            aid = wid[5:]
            default = next(k for a, _, k, _ in settings.KEY_ACTIONS if a == aid)
            keys = self.s.setdefault("keys", {})
            if ev.value.strip() == default:
                keys.pop(aid, None)
            else:
                keys[aid] = ev.value.strip()
            self.changed()
        elif wid.startswith("col__"):
            self.update_swatches()
        elif wid.startswith("out"):
            self.output_changed()
        else:
            self._set_field(wid, ev.value)

    @on(Switch.Changed)
    def switch_changed(self, ev: Switch.Changed) -> None:
        wid = ev.switch.id or ""
        if wid.startswith("out"):
            self.output_changed()
        else:
            self._set_field(wid, ev.value)

    @on(Select.Changed)
    def select_changed(self, ev: Select.Changed) -> None:
        wid = ev.select.id or ""
        if wid == "ppd":
            if not self._loading and isinstance(ev.value, str):
                r = run(["powerprofilesctl", "set", ev.value])
                self.notify("Power profile set" if r.returncode == 0 else r.stderr.strip()[:200])
        elif wid.startswith("out"):
            self.output_changed()
        elif ev.value is not Select.BLANK:
            self._set_field(wid, ev.value)

    @on(SelectionList.SelectedChanged, "#sections")
    def sections_changed(self, ev) -> None:
        if self._loading:
            return
        chosen = set(ev.selection_list.selected)
        self.s["prompt"]["sections"] = [x for x in settings.PROMPT_SECTIONS if x in chosen]
        self.changed()

    @on(TextArea.Changed, "#autostart")
    def autostart_changed(self, ev: TextArea.Changed) -> None:
        if self._loading:
            return
        self.s["autostart"]["extra"] = [l.strip() for l in ev.text_area.text.splitlines() if l.strip()]
        self.changed()

    def output_changed(self) -> None:
        if self._loading:
            return
        outs = {}
        for n, o in enumerate(self.si.outputs):
            try:
                scale = float(self.query_one(f"#out{n}_scale", Input).value or 1)
            except ValueError:
                scale = 1.0
            mode = self.query_one(f"#out{n}_mode", Select).value
            outs[self.output_key(o)] = {
                "enabled": self.query_one(f"#out{n}_enabled", Switch).value,
                "mode": mode if isinstance(mode, str) else "",
                "scale": scale,
                "pos": self.query_one(f"#out{n}_pos", Input).value.strip(),
                "adaptive_sync": self.query_one(f"#out{n}_vrr", Switch).value,
            }
        self.s["display"]["outputs"] = outs
        prim = self.query("#out_primary")
        if prim:
            v = prim.first(Select).value
            self.s["display"]["primary"] = v if isinstance(v, str) else ""
        self.changed()

    # ── Theme & layout lists: apply immediately ─────────────────────
    @on(ListView.Selected, "#themelist")
    def theme_selected(self, ev: ListView.Selected) -> None:
        if isinstance(ev.item, ThemeItem):
            self.select_theme(ev.item.t)

    def select_theme(self, t: themes.Theme) -> None:
        old = self.all_themes.get(self.s["theme"]["name"])
        changed = themes.apply_style(self.s, t, old)
        self.s["theme"]["name"] = t.id
        for p in STYLE_PATHS:
            self.set_widget(p)
        self.sync_layout_list()
        self.load_colors(t)
        self.query_one("#custom_name", Input).value = t.label if t.custom else ""
        use_theme(self, t.id, self.s["theme"]["accent"], self.s["bar"]["layout"])
        self.refresh_hero()
        if changed:
            self.notify(f"{t.label}: style applied ({', '.join(changed)}) – change it under Appearance/Layout")
        self.live_apply()

    @on(ListView.Highlighted, "#layoutlist")
    def layout_highlight(self, ev: ListView.Highlighted) -> None:
        if isinstance(ev.item, LayoutItem):
            self.query_one("#layout_preview", Static).update(ev.item.lay.preview)

    @on(ListView.Selected, "#layoutlist")
    def layout_selected(self, ev: ListView.Selected) -> None:
        if isinstance(ev.item, LayoutItem):
            self.s["bar"]["layout"] = ev.item.lay.id
            use_layout(self, ev.item.lay.id)
            self.notify(f"Layout: {ev.item.lay.label}")
            self.live_apply()

    def sync_layout_list(self) -> None:
        ids = list(layouts.LAYOUTS)
        lv = self.query_one("#layoutlist", ListView)
        with self.prevent(ListView.Highlighted, ListView.Selected):
            lv.index = ids.index(layouts.get(self.s["bar"]["layout"]).id)
        self.query_one("#layout_preview", Static).update(layouts.get(self.s["bar"]["layout"]).preview)

    def load_colors(self, t: themes.Theme) -> None:
        for k in themes.COLOR_KEYS:
            with self.prevent(Input.Changed):
                self.query_one(f"#col__{k}", Input).value = t.colors[k]
        self.update_swatches()

    def editor_colors(self) -> dict[str, str] | None:
        cols = {}
        for k in themes.COLOR_KEYS:
            v = self.query_one(f"#col__{k}", Input).value.strip()
            if not themes.HEX.match(v):
                return None
            cols[k] = v.lower()
        return cols

    def update_swatches(self) -> None:
        for k in themes.COLOR_KEYS:
            v = self.query_one(f"#col__{k}", Input).value.strip()
            sw = self.query_one(f"#sw__{k}", Static)
            if themes.HEX.match(v):
                sw.styles.background = v
                sw.update(" ")
            else:
                sw.styles.background = None
                sw.update("?")

    def save_custom_theme(self) -> None:
        cols = self.editor_colors()
        if not cols:
            self.notify("At least one colour is not a valid hex value (#rrggbb)", severity="error")
            return
        name = self.query_one("#custom_name", Input).value.strip()
        base = themes.get(self.s["theme"]["name"])
        if not name:
            name = f"{base.label.split(' (')[0]} custom"
        t = themes.save_custom(name, base, cols)
        self.all_themes = themes.all_themes()
        lv = self.query_one("#themelist", ListView)
        if not any(isinstance(i, ThemeItem) and i.t.id == t.id for i in lv.children):
            lv.append(ThemeItem(t))
        self.s["theme"]["name"] = t.id
        self.s["theme"]["accent"] = ""
        self.set_widget("theme.accent")
        use_theme(self, t.id, "", self.s["bar"]["layout"])
        self.notify(f"Theme “{t.label}” saved ({t.path.name if t.path else ''}) and activated")
        self.live_apply()

    def show_wallpaper(self, img: str) -> None:
        """Remember an image (or "theme" / "solid") as the wallpaper."""
        self.s["theme"]["wallpaper"] = img

    def theme_from_wallpaper(self) -> None:
        from .. import wallpalette
        img = self.s["theme"]["wallpaper"]
        if not img or not Path(img).is_file():
            self.notify("Pick a picture on the Wallpapers page first", severity="warning")
            return
        mode = str(self.query_one("#wpt_mode", Select).value)
        try:
            from .. import livewall
            t = wallpalette.make_theme(livewall.thumb(img) if livewall.is_video(img) else img, mode)
        except ImportError:
            self.notify("Needs Pillow: sudo dnf install python3-pillow", severity="error", timeout=10)
            return
        except OSError as e:
            self.notify(f"Can't read that image: {e}", severity="error")
            return
        self.show_wallpaper(img)
        self.s["theme"]["accent"] = ""
        self.set_widget("theme.accent")
        self.all_themes = themes.all_themes()
        lv = self.query_one("#themelist", ListView)
        for item in list(lv.children):
            if isinstance(item, ThemeItem) and item.t.id == t.id:
                item.remove()
        lv.append(ThemeItem(t))
        with self.prevent(ListView.Highlighted, ListView.Selected):
            lv.index = len(lv.children) - 1
        self.select_theme(t)
        self.query_one("#custom_name", Input).value = ""
        self.notify(f"{'Dark' if t.dark else 'Light'} theme made from {Path(img).name} – "
                    "name it and press “Save as my theme” to keep it")

    def start_update(self) -> None:
        """Update both projects in a terminal; when it reports success, restart with the new code."""
        import time
        from .. import update
        update.DONE_MARK.unlink(missing_ok=True)
        self._update_started = time.time()
        self.spawn_term(update.terminal_command(HOLD))
        self.notify("Updating in a terminal – this app restarts by itself when it is done", timeout=8)
        if getattr(self, "_update_timer", None) is None:
            self._update_timer = self.set_interval(1.0, self._check_update_done)

    def _check_update_done(self) -> None:
        from .. import update
        try:
            done = update.DONE_MARK.stat().st_mtime >= self._update_started - 1
        except OSError:
            return
        if done:
            update.DONE_MARK.unlink(missing_ok=True)
            if self.dirty:
                settings.save(self.s)              # nothing you changed gets lost
            self.exit("restart")

    def live_apply(self) -> None:
        """Make theme changes visible right away (saves as well)."""
        self.save_and_apply(quiet=True)

    # ── Buttons ─────────────────────────────────────────────────────
    @on(Button.Pressed)
    def button(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        name = ev.button.name or ""
        hold = HOLD
        if name.startswith("edit:"):
            path = name[5:]
            key = "sway" if path == "general.keys" else render.file_for(path, self.s)
            self.open_file(render.CONFIG_FILES[key][1])
        elif name.startswith("file:"):
            self.open_file(render.CONFIG_FILES[name[5:]][1])
        elif bid == "theme_save":
            self.save_custom_theme()
        elif bid == "theme_reset":
            self.load_colors(themes.get(self.s["theme"]["name"]))
        elif bid == "theme_file":
            t = themes.get(self.s["theme"]["name"])
            if not t.custom:
                self.notify("Bundled themes are replaced on updates – “Save as my theme” first, "
                            "then open it.", severity="warning", timeout=8)
                return
            self.open_file(t.path)  # type: ignore[arg-type]
        elif bid == "sys_selfupdate":
            self.start_update()
            self.notify("Updating swayforge + wolfforge in a terminal – restart this app afterwards")
        elif bid == "shell_toggle":
            if not (have("noctalia") or have("noctalia-shell")) and self.s["general"].get("shell") != "noctalia":
                self.notify("Noctalia is not installed. Run: sudo dnf install noctalia", severity="warning", timeout=10)
                return
            self.s["general"]["shell"] = "swayforge" if self.s["general"].get("shell") == "noctalia" else "noctalia"
            if self.s["general"]["shell"] == "swayforge":
                for pat in (["-x", "noctalia"], ["-x", "noctalia-shell"], ["-f", "^quickshell.*noctalia"]):
                    run(["pkill", *pat])                  # swayforge's bar + mako come back with the reload
            self.save_and_apply(quiet=False)
            on = self.s["general"]["shell"] == "noctalia"
            ev.button.label = "Switch back to swayforge's bar" if on else "Run Noctalia instead (bar off)"
            self.query_one("#shell_state", Static).update(
                ("Noctalia runs the bar and notifications; swayforge's bar is off."
                                            if on else "swayforge's own bar and notifications are on."))
        elif bid == "sv_preview":
            name = self.s["power"].get("screensaver", "off")
            if name == "off":
                name = "matrix"
                self.notify("No screensaver chosen – showing the Matrix one", timeout=5)
            self.spawn_term(f"{render.LAUNCHER} screensaver preview {name}")
        elif bid == "keys_reset":
            self.s["keys"] = {}
            for aid, _l, key, _c in settings.KEY_ACTIONS:
                self.query_one(f"#key__{aid}", Input).value = key
            self.changed()
        elif bid in ("boot_apply", "login_apply", "login_restore"):
            self.save_and_apply(quiet=True)
            script = {"boot_apply": "apply-boot.sh", "login_apply": "apply-login.sh",
                      "login_restore": "restore-sddm.sh"}[bid]
            self.spawn_term(f"bash {shlex.quote(str(boot.BOOT_DIR / script))}; {hold}")
        elif bid.startswith("sec_"):
            self.security_button(bid, hold)
        elif bid == "sys_update":
            self.spawn_term(f"sudo dnf upgrade --refresh; flatpak update 2>/dev/null; {hold}")
        elif bid == "sys_fw":
            self.spawn_term(f"fwupdmgr refresh; fwupdmgr get-updates; {hold}")
        elif bid == "sys_installer":
            self.spawn_term(f"{shlex.quote(render.LAUNCHER)} install")
        elif bid == "sys_import":
            self.import_sway(self.query_one("#import_path", Input).value.strip())
        elif bid == "sys_export":
            from .. import tools
            self.save_and_apply(quiet=True)
            tools.export(self.query_one("#export_path", Input).value.strip())
            self.notify("Backup exported")
        elif bid in ("sys_restore", "sys_open_backup"):
            item = self.query_one("#backuplist", ListView).highlighted_child
            if not item or not item.name:
                self.notify("Select a backup first", severity="warning")
                return
            if bid == "sys_open_backup":
                subprocess.Popen(["xdg-open", item.name], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                self.restore_backup(Path(item.name))

    def security_button(self, bid: str, hold: str) -> None:
        from .. import security
        L = shlex.quote(render.LAUNCHER)
        nq = "" if self.s["security"]["quarantine"] else " --no-quarantine"
        if bid in ("sec_dl", "sec_home"):
            self.spawn_term(f"{L} scan {'downloads' if bid == 'sec_dl' else 'home'}{nq}; {hold}")
        elif bid == "sec_drive_scan":
            v = self.query_one("#sec_drive", Select).value
            if v is Select.BLANK:
                self.notify("Pick a drive first", severity="warning")
                return
            self.spawn_term(f"{L} scan {shlex.quote(str(v))}{nq}; {hold}")
        elif bid == "sec_path_scan":
            v = self.query_one("#sec_path", Input).value.strip()
            if not v or not Path(os.path.expanduser(v)).exists():
                self.notify("That path doesn't exist", severity="error")
                return
            self.spawn_term(f"{L} scan {shlex.quote(os.path.expanduser(v))}{nq}; {hold}")
        elif bid == "sec_fresh":
            self.spawn_term(f"sudo freshclam; {hold}")
        elif bid == "sec_install":
            self.spawn_term("sudo dnf install -y clamav clamav-freshclam rkhunter chkrootkit lynis usbutils && "
                            "sudo freshclam && sudo systemctl enable --now clamav-freshclam.service; "
                            f"sudo rkhunter --propupd; {hold}")
        elif bid == "sec_rootkit":
            self.spawn_term(f"{L} audit rootkit; {hold}")
        elif bid == "sec_audit":
            self.spawn_term(f"{L} audit system; {hold}")
        elif bid == "sec_quar":
            security.QUARANTINE.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["xdg-open", str(security.QUARANTINE)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif bid.startswith("sec_ov_"):
            self.query_one("#sec_out", Static).update(security.overview(bid[7:]))
        elif bid == "sec_refresh":
            drives = security.removable_drives()
            sel = self.query_one("#sec_drive", Select)
            sel.set_options([(f"{d['label']} ({d['size']}) – {d['mount']}", d["mount"]) for d in drives])
            sel.disabled = not drives
            self.query_one("#sec_drive_scan", Button).disabled = not drives
            self.notify(f"{len(drives)} USB drive(s) found")
        elif bid == "sec_report":
            item = self.query_one("#reportlist", ListView).highlighted_child
            if item and item.name:
                self.spawn_term(f"less {shlex.quote(item.name)}")

    def open_file(self, p: Path) -> None:
        if not p.exists():
            render.render_all(copy.deepcopy(self.s))      # creates your files
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        editor = self.s["general"]["editor"]
        if editor.split()[0] in ("code", "codium"):
            subprocess.Popen(shlex.split(editor.replace(" --wait", "")) + [str(p)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.spawn_term(f"{editor} {shlex.quote(str(p))}")
        self.notify(f"Opened {str(p).replace(str(paths.HOME), '~')} – after saving there, press Ctrl+S "
                    "here or run `swayforge apply`", timeout=6)

    def spawn_term(self, cmd: str) -> None:
        full = render.terminal_cmd(self.s, "swayforge-task", f"sh -c {shlex.quote(cmd)}")
        if os.environ.get("WAYLAND_DISPLAY"):
            subprocess.Popen(shlex.split(full), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            with self.suspend():
                subprocess.run(["sh", "-c", cmd])

    def import_sway(self, path: str) -> None:
        from ..importer import import_sway_config
        try:
            msg = import_sway_config(Path(os.path.expanduser(path)))
        except (OSError, ValueError) as e:
            self.notify(str(e), severity="error", timeout=10)
            return
        self.notify(msg, timeout=8)
        self.save_and_apply(quiet=False)

    def restore_backup(self, d: Path) -> None:
        n = 0
        for f in d.rglob("*"):
            if f.is_file():
                target = paths.HOME / f.relative_to(d)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
                n += 1
        self.notify(f"{n} files restored. Note: saving in swayforge rewrites generated files again.",
                    timeout=10)
        if os.environ.get("SWAYSOCK"):
            run(["swaymsg", "reload"])

    # ── Saving ──────────────────────────────────────────────────────
    def action_save(self) -> None:
        self.save_and_apply(quiet=False)

    @work(exclusive=True, thread=True, group="apply")
    def save_and_apply(self, quiet: bool) -> None:
        snapshot = copy.deepcopy(self.s)
        settings.save(snapshot)
        res = render.apply(snapshot)

        def done() -> None:
            self.saved = snapshot
            if res.errors:
                self.notify("\n".join(res.errors)[:600], severity="error", timeout=15)
            elif not quiet:
                extra = f" – old files backed up ({len(res.backups)})" if res.backups else ""
                self.notify(f"Saved and applied{extra}")
            for n in res.notes:
                if "Duplicate" in n or "not found" in n or "taken over" in n:
                    self.notify(n, severity="warning", timeout=8)
            self.status("")
        self.call_from_thread(done)

    def action_quit_app(self) -> None:
        if self.dirty and not self._quit_armed:
            self._quit_armed = True
            self.notify("Unsaved changes! Ctrl+S saves – press Esc/Ctrl+Q again to discard.",
                        severity="warning")
            return
        self.exit()


def main(page: str = "") -> None:
    from .. import crash
    result = crash.run_app("swayforge settings", SettingsApp(page))
    if result == "restart":                       # updated: start the new code in this same window
        os.execv(render.LAUNCHER, [render.LAUNCHER, "settings", "--page", "about"])
