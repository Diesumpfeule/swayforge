"""Central settings: ~/.config/swayforge/settings.toml is the single source of truth."""
from __future__ import annotations

import copy
import tomllib
from typing import Any

from . import paths, tomlw

DEFAULTS: dict[str, Any] = {
    "general": {
        "terminal": "kitty",          # kitty | alacritty
        "browser": "firefox",
        "file_manager": "thunar",
        "editor": "nvim",
        "mod": "Mod4",                # Mod4 = Super/Windows key, Mod1 = Alt
    },
    "theme": {
        "name": "catppuccin-mocha",
        "accent": "",                 # empty = theme default, else a colour name (blue, green …)
        "font": "JetBrainsMono Nerd Font",   # used EVERYWHERE (apps, bar, terminal, GTK, browser)
        "font_size": 11,
        "font_everywhere": True,      # make it the system default via fontconfig
        "icon_theme": "auto",         # auto = Papirus matching light/dark
        "cursor_theme": "Adwaita",
        "cursor_size": 24,
        "wallpaper": "theme",         # theme | solid | /path/to/image
        "ascii": "auto",              # auto = the theme's motif, or anvil/rose/moon/bat/…
        "style_backup": {},           # internal: your own values while a theme style is active
    },
    "look": {
        "gaps_inner": 8,
        "gaps_outer": 4,
        "border": 2,
        "radius": 4,                  # bar/launcher/notifications; windows too with SwayFX (0 = square)
        "title_bars": False,
        "gtk_buttons": False,         # close/minimise buttons in GTK apps (keyboard users: off)
        "smart_gaps": True,
        "terminal_opacity": 0.95,
        "terminal_padding": 10,
        "fx_blur": True,              # SwayFX only
        "fx_shadows": True,           # SwayFX only
        "fx_dim_inactive": 0.0,       # SwayFX only, 0.0–0.5
    },
    "bar": {
        "layout": "modern",           # modern | solid | win98 | win7 | wired | minimal | sidebar
        "height": 34,
        "window_title": True,
        "taskmanager": True,          # button: btop in a terminal
        "gamemode": True,             # button: gaming mode
        "cpu": True,
        "memory": True,
        "gpu": True,                  # AMD GPU load
        "temperature": True,
        "network": True,
        "audio": True,
        "bluetooth": True,
        "battery": True,              # only shown when a battery exists
        "backlight": True,            # laptops only
        "idle_inhibitor": True,
        "media": False,
        "tray": True,
        "clock_format": "%H:%M",
        "date_format": "%a %d.%m.",
    },
    "input": {
        "kb_layout": "ch",
        "kb_variant": "",
        "kb_options": "",
        "numlock": True,
        "repeat_rate": 35,
        "repeat_delay": 300,
        "mouse_accel_profile": "flat",   # flat = no acceleration (gaming)
        "mouse_speed": 0.0,
        "touchpad_tap": True,
        "touchpad_natural": True,
        "touchpad_dwt": True,
    },
    "display": {
        "allow_tearing": True,        # lower input lag in fullscreen games
        "outputs": {},                # "Make Model Serial" = { mode=…, pos=…, scale=…, adaptive_sync=…, enabled=… }
    },
    "power": {
        "lock_after": 10,             # minutes, 0 = never
        "screen_off_after": 15,
        "suspend_after": 0,           # 0 = never (desktop); the installer sets 30 on laptops
        "lock_before_sleep": True,
        "inhibit_fullscreen": True,   # don't lock while gaming / watching videos
        "nightlight": False,
        "nightlight_temp": 4000,
        "location": "47.4:8.5",       # latitude:longitude for sunrise/sunset
    },
    "shell": {
        "zsh": True,
        "spaceship": True,
        "autosuggestions": True,
        "syntax_highlighting": True,
        "fastfetch_on_start": True,
        "aliases": True,
    },
    "prompt": {
        "char": "❯",
        "add_newline": True,
        "separate_line": True,
        "async": True,
        "show_time": False,
        "show_exec_time": True,
        "exit_code": True,
        "user": "needed",            # always | needed | false
        "host": "needed",
        "dir_trunc": 3,
        "sections": ["user", "dir", "host", "git", "python", "venv", "node", "rust",
                     "golang", "docker", "exec_time", "async", "line_sep", "jobs",
                     "exit_code", "sudo", "char"],
    },
    "boot": {
        "style": "auto",              # auto = the theme's, or bios | ascii | wired | classic | minimal
        "text": "",                   # banner text, empty = hostname
    },
    "login": {
        "greeter": "tuigreet",        # tuigreet | sddm (what the installer set up)
        "show_time": True,
        "remember": True,
        "greeting": "",               # extra line under the art, empty = none
    },
    "security": {
        "quarantine": True,           # move infected files to a quarantine folder (never delete)
        "weekly_scan": False,         # systemd user timer: weekly ClamAV scan
        "weekly_target": "downloads", # downloads | home
    },
    "keys": {},                       # overrides: action-id = "$mod+x"
    "autostart": {
        "extra": [],                  # your own commands at login
    },
}

# All prompt sections offered in the settings app (order = display order)
PROMPT_SECTIONS = ["time", "user", "dir", "host", "git", "package", "python", "venv",
                   "conda", "node", "rust", "golang", "java", "php", "docker",
                   "kubectl", "terraform", "aws", "exec_time", "async", "line_sep",
                   "battery", "jobs", "exit_code", "sudo", "char"]

# (id, label, default key, command). {term} {browser} {files} {sf} {btop} {settings} are replaced.
KEY_ACTIONS: list[tuple[str, str, str, str]] = [
    ("terminal", "Open terminal", "$mod+Return", "exec {term}"),
    ("launcher", "App launcher (Rofi)", "$mod+d", "exec rofi -show drun"),
    ("run", "Run a command", "$mod+Shift+d", "exec rofi -show run"),
    ("windows", "Find a window", "$mod+Shift+w", "exec rofi -show window"),
    ("browser", "Browser", "$mod+b", "exec {browser}"),
    ("files", "File manager", "$mod+e", "exec {files}"),
    ("settings", "swayforge settings", "$mod+i", "exec {settings}"),
    ("power", "Power menu", "$mod+Escape", "exec {sf} power"),
    ("lock", "Lock screen", "$mod+Shift+x", "exec swaylock -f"),
    ("clipboard", "Clipboard history", "$mod+v", "exec {sf} clip"),
    ("keys", "Show all shortcuts", "$mod+F1", "exec {sf} keys"),
    ("kill", "Close window", "$mod+q", "kill"),
    ("fullscreen", "Fullscreen", "$mod+f", "fullscreen toggle"),
    ("float", "Floating on/off", "$mod+Shift+space", "floating toggle"),
    ("focus_mode", "Focus tiling/floating", "$mod+space", "focus mode_toggle"),
    ("layout_stack", "Layout: stacked", "$mod+s", "layout stacking"),
    ("layout_tab", "Layout: tabbed", "$mod+w", "layout tabbed"),
    ("layout_split", "Layout: toggle split", "$mod+t", "layout toggle split"),
    ("split_h", "Next window to the right", "$mod+h", "splith"),
    ("split_v", "Next window below", "$mod+g", "splitv"),
    ("resize", "Resize mode", "$mod+r", 'mode "resize"'),
    ("reload", "Reload Sway", "$mod+Shift+c", "reload"),
    ("ws_back", "Previous workspace", "$mod+Tab", "workspace back_and_forth"),
    ("scratch_show", "Show scratchpad", "$mod+minus", "scratchpad show"),
    ("scratch_move", "Move to scratchpad", "$mod+Shift+minus", "move scratchpad"),
    ("focus_out_l", "Focus left monitor", "$mod+Ctrl+Left", "focus output left"),
    ("focus_out_r", "Focus right monitor", "$mod+Ctrl+Right", "focus output right"),
    ("ws_to_out_l", "Workspace → left monitor", "$mod+Ctrl+Shift+Left", "move workspace to output left"),
    ("ws_to_out_r", "Workspace → right monitor", "$mod+Ctrl+Shift+Right", "move workspace to output right"),
    ("shot_area", "Screenshot area → clipboard", "Print", "exec {sf} shot area"),
    ("shot_full", "Screenshot whole monitor", "Shift+Print", "exec {sf} shot output"),
    ("shot_edit", "Screenshot area and edit", "$mod+Shift+s", "exec {sf} shot edit"),
    ("notif_dismiss", "Dismiss notifications", "$mod+n", "exec makoctl dismiss --all"),
    ("notif_dnd", "Do not disturb on/off", "$mod+Shift+n", "exec makoctl mode -t do-not-disturb"),
    ("theme_next", "Next theme", "$mod+Shift+t", "exec {sf} theme --next"),
    ("layout_next", "Next bar layout", "$mod+Shift+l", "exec {sf} layout --next"),
    ("taskmanager", "Task manager (btop)", "Ctrl+Shift+Escape", "exec {btop}"),
    ("gamemode", "Gaming mode on/off", "$mod+Shift+g", "exec {sf} gamemode"),
    ("audio", "Audio settings", "$mod+Shift+a", "exec {settings_page}audio"),
    ("network", "Network settings", "$mod+Shift+i", "exec {settings_page}network"),
]


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("outputs", "keys", "style_backup"):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _migrate(data: dict) -> dict:
    """Older settings files → current names."""
    bar = data.get("bar", {})
    if "style" in bar and "layout" not in bar:
        bar["layout"] = {"floating": "modern", "solid": "solid"}.get(bar["style"], "modern")
    bar.pop("style", None)
    bar.pop("position", None)
    sb = data.get("theme", {}).get("style_backup", {})
    if "bar_style" in sb:
        sb["layout"] = {"floating": "modern", "solid": "solid"}.get(sb.pop("bar_style"), "modern")
    return data


def load() -> dict:
    data = {}
    if paths.SETTINGS_FILE.exists():
        try:
            data = tomllib.loads(paths.SETTINGS_FILE.read_text())
        except tomllib.TOMLDecodeError as e:
            raise SystemExit(f"Error in {paths.SETTINGS_FILE}: {e}")
    return _merge(DEFAULTS, _migrate(data))


def save(s: dict) -> None:
    paths.ensure_dirs()
    header = ("# swayforge settings – safe to edit by hand,\n"
              "# then run `swayforge apply` (or save in the app).\n\n")
    paths.SETTINGS_FILE.write_text(header + tomlw.dumps(s))


def get(s: dict, path: str, default=None):
    cur: Any = s
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_(s: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = s
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def keybinds(s: dict) -> list[tuple[str, str, str, str]]:
    """(id, label, key, command) with user overrides."""
    over = s.get("keys", {})
    return [(aid, label, over.get(aid, key), cmd) for aid, label, key, cmd in KEY_ACTIONS]
