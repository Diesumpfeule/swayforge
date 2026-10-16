"""swayforge settings – like KDE's System Settings, but for Sway and in the terminal."""
from __future__ import annotations

import copy
import os
import shlex
import subprocess
from pathlib import Path

from rich.text import Text
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
from .common import (BASE_CSS, Field, coerce, field_row, hero_text, path_from_wid, section, swatch,
                     two_tone, use_theme)
from .panels import AudioPanel, BluetoothPanel, NetworkPanel

ON_OFF = [("always", "always"), ("only via SSH/root", "needed"), ("never", "false")]

PAGES: list[tuple[str, str]] = [
    ("theme", "\U000f03d8  Theme"),
    ("layout", "\U000f056e  Layout"),
    ("look", "\U000f00e3  Appearance"),
    ("bar", "\U000f062e  Bar modules"),
    ("display", "\U000f0379  Displays"),
    ("audio", "\U000f057e  Audio"),
    ("bluetooth", "\U000f00af  Bluetooth"),
    ("network", "\U000f05a9  Network"),
    ("input", "\U000f030c  Keyboard & mouse"),
    ("shell", "\U000f018d  Terminal & prompt"),
    ("keys", "\U000f003b  Apps & shortcuts"),
    ("power", "\U000f06a5  Power & lock"),
    ("boot", "\U000f07b7  Boot & login"),
    ("system", "\U000f0493  System & files"),
]

FIELDS: dict[str, list[Field | str]] = {
    "look": [
        "Font (used everywhere)",
        Field("theme.font", "Font", help="A Nerd Font · retro: Terminess Nerd Font"),
        Field("theme.font_size", "Font size", "int"),
        Field("theme.font_everywhere", "Use it in every app", "bool",
              help="also browser, GTK and Qt apps (fontconfig)"),
        "Windows",
        Field("look.gaps_inner", "Gap between windows", "int"),
        Field("look.gaps_outer", "Gap to the screen edge", "int"),
        Field("look.border", "Border width", "int", help="0 = no border at all"),
        Field("look.radius", "Corner radius", "int", help="0 = square · 4 = slight · 10 = round"),
        Field("look.title_bars", "Window title bars", "bool"),
        Field("look.gtk_buttons", "Close buttons in GTK apps", "bool", help="off = cleaner, keyboard-only"),
        Field("look.smart_gaps", "No gaps with a single window", "bool"),
        "Icons & cursor",
        Field("theme.icon_theme", "Icon theme", "choice",
              [("Automatic (Papirus)", "auto"), ("Papirus", "Papirus"), ("Papirus Dark", "Papirus-Dark"),
               ("Papirus Light", "Papirus-Light"), ("Adwaita", "Adwaita")]),
        Field("theme.cursor_theme", "Cursor theme", help="e.g. Adwaita, Bibata-Modern-Classic"),
        Field("theme.cursor_size", "Cursor size", "choice", [("24", 24), ("32", 32), ("48", 48)]),
        "Effects (SwayFX only)",
        Field("look.fx_blur", "Blur behind transparent windows", "bool"),
        Field("look.fx_shadows", "Shadows", "bool"),
        Field("look.fx_dim_inactive", "Dim inactive windows", "float", help="0.0 = off, 0.2 = slight"),
    ],
    "bar": [
        "General",
        Field("bar.height", "Height", "int"),
        Field("bar.clock_format", "Time format", help="strftime: %H:%M or %H:%M:%S"),
        Field("bar.date_format", "Date format", help="e.g. %a %d.%m. – empty = time only"),
        "Buttons & modules",
        Field("bar.taskmanager", "Task manager button (btop)", "bool", help="also Ctrl+Shift+Esc"),
        Field("bar.gamemode", "Gaming mode button", "bool", help="no gaps, do not disturb, full power"),
        Field("bar.window_title", "Window title", "bool"),
        Field("bar.cpu", "CPU", "bool"),
        Field("bar.gpu", "GPU load (AMD)", "bool"),
        Field("bar.memory", "Memory", "bool"),
        Field("bar.temperature", "CPU temperature", "bool"),
        Field("bar.network", "Network", "bool"),
        Field("bar.bluetooth", "Bluetooth", "bool"),
        Field("bar.audio", "Volume + microphone", "bool"),
        Field("bar.media", "Music (Spotify, browser …)", "bool"),
        Field("bar.battery", "Battery (laptops)", "bool"),
        Field("bar.backlight", "Brightness (laptops)", "bool"),
        Field("bar.idle_inhibitor", "Stay-awake toggle", "bool"),
        Field("bar.tray", "Tray icons (Discord, Steam …)", "bool"),
    ],
    "input": [
        "Keyboard",
        Field("input.kb_layout", "Layout", help="ch, de, us … several: ch,us"),
        Field("input.kb_variant", "Variant", help="empty = Swiss German, fr = Swiss French"),
        Field("input.kb_options", "Options", help="e.g. caps:escape or grp:alt_shift_toggle"),
        Field("input.numlock", "NumLock on at start", "bool"),
        Field("input.repeat_rate", "Repeat rate (per second)", "int"),
        Field("input.repeat_delay", "Delay before repeat (ms)", "int"),
        "Mouse",
        Field("input.mouse_accel_profile", "Acceleration", "choice",
              [("Off (flat – best for games)", "flat"), ("Adaptive", "adaptive")]),
        Field("input.mouse_speed", "Speed", "float", help="-1.0 to 1.0"),
        "Touchpad",
        Field("input.touchpad_tap", "Tap to click", "bool"),
        Field("input.touchpad_natural", "Natural scrolling", "bool"),
        Field("input.touchpad_dwt", "Disable while typing", "bool"),
    ],
    "shell": [
        "Terminal",
        Field("general.terminal", "Terminal", "choice", [("kitty", "kitty"), ("Alacritty", "alacritty")]),
        Field("look.terminal_opacity", "Opacity", "float", help="1.0 = opaque"),
        Field("look.terminal_padding", "Padding", "int"),
        "zsh",
        Field("shell.fastfetch_on_start", "fastfetch on open (themed, with ASCII art)", "bool"),
        Field("shell.autosuggestions", "Suggestions from history (grey)", "bool"),
        Field("shell.syntax_highlighting", "Syntax highlighting", "bool"),
        Field("shell.aliases", "Handy aliases (ll, update, …)", "bool"),
        "Spaceship prompt",
        Field("shell.spaceship", "Use Spaceship", "bool"),
        Field("prompt.char", "Prompt character", help="❯  ➜  λ  $  ▶"),
        Field("prompt.separate_line", "Input on its own line", "bool"),
        Field("prompt.add_newline", "Blank line before each prompt", "bool"),
        Field("prompt.async", "Async (faster in big Git repos)", "bool"),
        Field("prompt.show_time", "Show time", "bool"),
        Field("prompt.show_exec_time", "Duration of long commands", "bool"),
        Field("prompt.exit_code", "Show exit code", "bool"),
        Field("prompt.user", "User name", "choice", ON_OFF),
        Field("prompt.host", "Host name", "choice", ON_OFF),
        Field("prompt.dir_trunc", "Directory depth", "int", help="0 = full path"),
    ],
    "keys": [
        "Default apps",
        Field("general.mod", "Main modifier ($mod)", "choice", [("Super / Windows", "Mod4"), ("Alt", "Mod1")]),
        Field("general.browser", "Browser", "choice",
              [("Firefox", "firefox"), ("Brave", "brave"), ("LibreWolf", "librewolf"),
               ("Zen", "zen"), ("Chromium", "chromium")]),
        Field("general.file_manager", "File manager", "choice",
              [("Thunar", "thunar"), ("Nautilus", "nautilus"), ("yazi (terminal)", "yazi")]),
        Field("general.editor", "Editor (for ✎ and $EDITOR)", "choice",
              [("Neovim", "nvim"), ("nano", "nano"), ("VS Code", "code --wait"),
               ("VSCodium", "codium --wait"), ("micro", "micro")]),
    ],
    "power": [
        "Lock & screen",
        Field("power.lock_after", "Lock after (minutes)", "int", help="0 = never"),
        Field("power.screen_off_after", "Screen off after (minutes)", "int", help="0 = never"),
        Field("power.suspend_after", "Suspend after (minutes)", "int", help="0 = never"),
        Field("power.lock_before_sleep", "Lock before suspend", "bool"),
        Field("power.inhibit_fullscreen", "Don't lock while fullscreen (games, videos)", "bool"),
        "Night light",
        Field("power.nightlight", "Night light (warmer colours at night)", "bool"),
        Field("power.nightlight_temp", "Night colour temperature (K)", "int", help="3500 = warm, 4500 = mild"),
        Field("power.location", "Location latitude:longitude", help="for sunrise/sunset, e.g. 47.4:8.5"),
    ],
    "boot": [
        "Login screen (tuigreet)",
        Field("login.show_time", "Show date & time", "bool"),
        Field("login.remember", "Remember the last user", "bool"),
        Field("login.greeting", "Extra line under the art", help="empty = none"),
    ],
}

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
    TITLE = "swayforge"
    SUB_TITLE = "Settings"
    CSS = BASE_CSS + """
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
    #outputs .outbox { border: round $panel; padding: 0 1; margin-bottom: 1; height: auto; }
    #autostart { height: 6; }
    #sections { height: 16; width: 50; }
    #backuplist { height: 8; border: round $panel; }
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
        Binding("ctrl+q", "quit_app", "Quit", priority=True),
        Binding("escape", "quit_app", "Quit", show=False),
    ]

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
            yield ListView(*[ListItem(Label(label), id=f"nav-{pid}") for pid, label in PAGES],
                           id="sidebar", initial_index=[p for p, _ in PAGES].index(self.start_page))
            with ContentSwitcher(initial=f"page-{self.start_page}", id="pages"):
                yield self.page_theme()
                yield self.page_layout()
                yield self.page_fields("look")
                yield self.page_fields("bar")
                yield self.page_display()
                yield AudioPanel(id="page-audio", classes="page")
                yield BluetoothPanel(id="page-bluetooth", classes="page")
                yield NetworkPanel(id="page-network", classes="page")
                yield self.page_fields("input")
                yield self.page_shell()
                yield self.page_keys()
                yield self.page_power()
                yield self.page_boot()
                yield self.page_system()
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
        wps = self.wallpaper_options()
        wp_val = self.s["theme"]["wallpaper"]
        if wp_val not in [v for _, v in wps]:
            wps.append((Path(wp_val).name, wp_val))
        t = themes.get(self.s["theme"]["name"])
        rows = [Horizontal(Label(themes.COLOR_LABELS[k]), Static(" ", classes="sw", id=f"sw__{k}"),
                           Input(t.colors[k], id=f"col__{k}", max_length=7), classes="colrow")
                for k in themes.COLOR_KEYS]
        art_opts = [("Theme's motif", "auto")] + [(n, n) for n in asc.all_art()]
        return self.page(
            "theme",
            Static(hero_text(self.s["theme"]["name"], self.s["theme"]["accent"]), id="hero_banner"),
            Horizontal(Static(two_tone(asc.art(asc.resolve(self.s, t)), t.with_accent(self.s["theme"]["accent"])["accent2"],
                                       t.colors["overlay"]), id="hero_art"),
                       Static("One click recolours everything: Sway, bar, Rofi, terminal, prompt, fastfetch, "
                              "GTK apps, lock screen, notifications, btop, cava, MangoHud and the boot/login "
                              "screens.\n\nRetro themes also bring square corners, a retro font and their own "
                              "layout.", classes="hint", id="hero_intro"), id="hero"),
            ListView(*items, id="themelist", initial_index=current),
            field_row(Field("theme.accent", "Accent colour", "choice", accent_opts), self.s),
            field_row(Field("theme.ascii", "ASCII art", "choice", art_opts,
                            help="fastfetch, login, boot screen · add your own in ~/.config/swayforge/ascii"),
                      self.s),
            section("Wallpaper"),
            field_row(Field("theme.wallpaper", "Wallpaper", "choice", wps,
                            help="images from ~/Pictures/Wallpapers or ~/Bilder/Hintergründe"), self.s),
            Horizontal(Input(placeholder="… or type a path to an image", id="wp_path"),
                       Button("Apply", id="wp_apply"), classes="btnrow"),
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
        return self.page(
            "layout",
            Static("The layout decides how the bar, start menu/launcher, notifications and GTK buttons "
                   "look – combine it with any colour theme (e.g. Classic 98 + Rust). Also: Super+Shift+L.",
                   classes="hint"),
            ListView(*[LayoutItem(l) for l in layouts.LAYOUTS.values()], id="layoutlist",
                     initial_index=ids.index(cur.id)),
            Static(cur.preview, id="layout_preview", classes="preview", markup=False),
            Static("Turn individual modules on/off under “Bar modules”. Per-module tweaks: ✎ there.",
                   classes="hint"),
        )

    def wallpaper_options(self) -> list[tuple[str, str]]:
        opts = [("Theme motif (follows the theme)", "theme"), ("Solid colour", "solid")]
        for d in (paths.HOME / "Pictures/Wallpapers", paths.HOME / "Pictures/wallpapers",
                  paths.HOME / "Bilder/Hintergründe", paths.HOME / "Wallpapers"):
            if d.is_dir():
                for f in sorted(d.iterdir())[:60]:
                    if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                        opts.append((f.name, str(f)))
        return opts

    def page_display(self) -> VerticalScroll:
        children: list = [field_row(Field("display.allow_tearing", "Allow tearing in games", "bool",
                                          help="lower input lag in fullscreen games"), self.s)]
        outs = self.si.outputs
        if not outs:
            children.append(Static("Displays can only be detected inside Sway. Open the settings "
                                   "in Sway with Super+I.", classes="warn"))
        else:
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
            *self.cs2_section(),
        )

    def cs2_section(self) -> list:
        if not (paths.XDG_DATA / "cs2-chat-uebersetzer").is_dir():
            return []
        watcher = run(["pgrep", "-f", "swayforge-cs2-watcher"]).returncode == 0 if have("pgrep") else False
        cond = False
        for lc in (paths.HOME / ".local/share/Steam/userdata").glob("*/config/localconfig.vdf"):
            try:
                cond = cond or "-condebug" in lc.read_text(errors="replace")
            except OSError:
                pass
        ok, no = "[green]✓[/]", "[yellow]✗[/]"
        return [
            section("CS2 chat translator"),
            Static(f"{ok if watcher else no} watcher {'running' if watcher else 'not running (starts with Sway)'}"
                   f"    {ok if cond else no} Steam launch option -condebug"
                   f"{'' if cond else ' – set it in Steam → CS2 → Properties'}", classes="hint"),
            Static("Overlay colours follow the theme. Position it once while CS2 runs "
                   "(drag, then Esc).", classes="hint"),
            Horizontal(Button("Position overlay", id="cs2_move", variant="primary"),
                       Button("Test in terminal", id="cs2_test"),
                       Button("Options ✎", id="cs2_args"),
                       Button("Log", id="cs2_log"), classes="btnrow"),
        ]

    def page_power(self) -> VerticalScroll:
        children = self.fields("power")
        if have("powerprofilesctl"):
            cur = run(["powerprofilesctl", "get"]).stdout.strip()
            avail = [l.strip().rstrip(":").lstrip("* ").strip()
                     for l in run(["powerprofilesctl", "list"]).stdout.splitlines() if l.strip().endswith(":")]
            names = {"performance": "Performance", "balanced": "Balanced", "power-saver": "Power saver"}
            opts = [(names.get(a, a), a) for a in avail] or [("Balanced", "balanced")]
            if cur and cur not in [v for _, v in opts]:
                opts.append((cur, cur))
            children[0:0] = [section("Power profile (applies immediately)"),
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
        use_theme(self, self.s["theme"]["name"], self.s["theme"]["accent"])
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
                    except Exception:  # noqa: BLE001 – value not among the options
                        pass

    def refresh_hero(self) -> None:
        t = themes.get(self.s["theme"]["name"])
        self.query_one("#hero_art", Static).update("\n".join(asc.art(asc.resolve(self.s, t))))
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
            use_theme(self, self.s["theme"]["name"], val)
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
        use_theme(self, t.id, self.s["theme"]["accent"])
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
        use_theme(self, t.id)
        self.notify(f"Theme “{t.label}” saved ({t.path.name if t.path else ''}) and activated")
        self.live_apply()

    def live_apply(self) -> None:
        """Make theme changes visible right away (saves as well)."""
        self.save_and_apply(quiet=True)

    # ── Buttons ─────────────────────────────────────────────────────
    @on(Button.Pressed)
    def button(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        name = ev.button.name or ""
        hold = 'echo; read -rp "Press Enter to close …"'
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
        elif bid == "wp_apply":
            p = os.path.expanduser(self.query_one("#wp_path", Input).value.strip())
            if not Path(p).is_file():
                self.notify("File not found", severity="error")
                return
            self.s["theme"]["wallpaper"] = p
            self.live_apply()
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
        elif bid == "cs2_move":
            subprocess.Popen([str(paths.HOME / ".local/bin/cs2-uebersetzer"), "--verschieben"],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.notify("Drag the overlay over the CS2 chat, then press Esc", timeout=6)
        elif bid == "cs2_test":
            self.spawn_term(f"{shlex.quote(str(paths.HOME / '.local/bin/cs2-uebersetzer'))} --terminal --alles; {hold}")
        elif bid == "cs2_args":
            self.open_file(paths.CONFIG_DIR / "cs2.args")
        elif bid == "cs2_log":
            self.spawn_term(f"less +F {shlex.quote(str(paths.HOME / '.cache/cs2_chat_uebersetzer.log'))}")
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
    SettingsApp(page).run()
