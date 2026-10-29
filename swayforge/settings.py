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
        "shell": "swayforge",         # swayforge = our bar + notifications | noctalia = hand them to Noctalia
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
        "animate": True,              # ASCII art glints and twinkles (apps, terminal greeting, LibreWolf)
        "motion": "wave",               # how the ASCII art moves: wave | float | drift | glint
        "live_fps": 0,                # animated wallpaper: 0 = as the video is, else limit (uses more CPU: no hardware decoding)
        "live_pause_fullscreen": True,   # pause the animation while a fullscreen window covers it
        "live_pause_battery": True,      # pause on battery
        "style_backup": {},           # internal: your own values while a theme style is active
    },
    "look": {
        "gaps_inner": 8,
        "gaps_outer": 4,
        "border": 2,
        "radius": 4,                  # bar/launcher/notifications; windows too with SwayFX (0 = square)
        "tiling_only": True,          # every window tiles – no floating, no tabs/stacking
        "title_bars": False,
        "gtk_buttons": False,         # close/minimise buttons in GTK apps (keyboard users: off)
        "smart_gaps": True,
        "terminal_opacity": 0.95,
        "ui_opacity": 1.0,            # bar, launcher, notifications: 1.0 = layout default, lower = more see-through
        "terminal_padding": 10,
        "fx_blur": True,              # SwayFX only
        "fx_shadows": True,           # SwayFX only
        "fx_dim_inactive": 0.0,       # SwayFX only, 0.0–0.5
    },
    "bar": {
        "layout": "modern",           # modern | glass | solid | win98 | winxp | dread | win7 | win11 | touch | wired | cathedral | minimal | sidebar
        "height": 34,
        "window_title": True,
        "taskmanager": True,          # button: btop in a terminal
        "gamemode": True,             # button: gaming mode
        "cpu": True,
        "memory": True,
        "gpu": True,                  # AMD GPU load
        "temperature": True,
        "network": "name",            # name (Wi-Fi name / IP on cable) | ip | icon | off
        "audio": True,                # volume
        "mic": True,                  # microphone (click = mute)
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
        "kb_layout": "us",
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
        "primary": "",                # main screen ("Make Model Serial"): workspace 1 + games start there
    },
    "sound": {
        "enabled": False,             # generated system sounds (login chime, notifications, errors …)
        "pack": "auto",               # auto (follows theme/layout) | classic | glass | modern | touch | wired | gothic | soft
        "volume": 0.7,
        "login": True,                # chime at login
        "notify": True,               # sound for notifications
    },
    "cyberdeck": {                    # small screens / Raspberry Pi – see cyberdeck.py
        "enabled": False,
        "compact": True,
        "low_power": True,
        "touch": False,
        "scale": 0,                   # 0 = keep each screen's own scale
    },
    "clipboard": {
        "enabled": True,
        "max_items": 100,
        "max_age": 1440,             # minutes, 0 = forever
        "images": True,
        "skip_sensitive": True,      # never keep passwords from password managers
    },
    "widgets": {                      # desktop widgets (below the windows) – see widgets.py
        "enabled": False,
        "clock": "binary",            # binary | dots | digital | analog | off
        "clock_pos": "top-right",
        "player": True,
        "player_pos": "bottom-right",
        "sysmon": False,
        "sysmon_pos": "top-left",
        "clippy": False,
        "clippy_pos": "bottom-left",
        "calendar": False,
        "calendar_pos": "top-left",
        "weather": False,
        "weather_pos": "top-right",
        "weather_city": "",            # empty = guessed from your internet connection
        "battery": False,
        "battery_pos": "bottom-left",
        "network": False,
        "network_pos": "top-left",
        "disks": False,
        "disks_pos": "top-left",
        "notes": False,
        "notes_pos": "bottom-left",
        "timer": False,
        "timer_pos": "bottom-right",
        "workspaces": False,
        "workspaces_pos": "bottom-center",
        "ws_thumbs": True,             # remember how each workspace looked (pictures stay in ~/.cache)
        "layer": "bottom",             # bottom = under your windows (desktop) | top = above them
        "scale": 1.0,
        "opacity": 0.85,
    },
    "power": {
        "lock_after": 10,             # minutes, 0 = never
        "screen_off_after": 15,
        "suspend_after": 0,           # 0 = never (desktop); the installer sets 30 on laptops
        "screensaver": "off",         # animated full-screen scene instead of a plain lock (see screensaver.py)
        "saver_speed": 5,             # Matrix / cmatrix: 1 = slow … 10 = fast
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
        "fetch_anim": "intro",        # intro | spin | donut | cube | fire | video | off – see fetchanim.py
        "fetch_seconds": 5,           # how long it plays (0 = until you press a key)
        "fetch_video": "",            # your own GIF / video for fetch_anim = video
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
    # Defaults = the author's own long-time Sway shortcuts. Empty key = off (set one in the app).
    ("terminal", "Open terminal", "$mod+Return", "exec {term}"),
    ("launcher", "App launcher + run (Rofi)", "$mod+r",
     "exec rofi -show combi -combi-modes drun#run -modes combi"),
    ("run", "Run a command", "", "exec rofi -show run"),
    ("windows", "Find a window", "$mod+Shift+w", "exec rofi -show window"),
    ("browser", "Browser", "$mod+w", "exec {browser}"),
    ("files", "File manager", "$mod+d", "exec {files}"),
    ("settings", "swayforge settings", "$mod+i", "exec {settings}"),
    ("studio", "swayforge app (graphical)", "$mod+Ctrl+i", "exec {sf} gui"),
    ("power", "Power menu", "$mod+Escape", "exec {sf} power"),
    ("exit", "Exit Sway (asks first)", "$mod+Shift+e",
     "exec swaynag -t warning -m 'Exit Sway? This ends your Wayland session.' -B 'Yes, exit' 'swaymsg exit'"),
    ("lock", "Lock screen", "$mod+Shift+x", "exec swaylock -f"),
    ("clipboard", "Clipboard history", "$mod+v", "exec {sf} clip"),
    ("keys", "Show all shortcuts", "$mod+F1", "exec {sf} keys"),
    ("kill", "Close window", "$mod+q", "kill"),
    ("fullscreen", "Real fullscreen (hides the bar – games, video)", "$mod+Shift+f", "fullscreen toggle"),
    ("focus_parent", "Focus parent container", "$mod+a", "focus parent"),
    ("focus_mode", "Focus tiling/floating", "$mod+space", "focus mode_toggle"),
    ("reload", "Reload Sway", "$mod+Shift+c", "reload"),
    ("ws_back", "Previous workspace", "$mod+Tab", "workspace back_and_forth"),
    ("ws_overview", "Workspace overview", "$mod+o", "exec {sf} widgets overview"),
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
    ("layout_next", "Next bar layout", "$mod+Shift+b", "exec {sf} layout --next"),
    ("taskmanager", "Task manager (btop)", "Ctrl+Shift+Escape", "exec {btop}"),
    ("gamemode", "Gaming mode on/off", "$mod+Shift+g", "exec {sf} gamemode"),
    ("audio", "Audio settings", "$mod+Shift+a", "exec {settings_page}audio"),
    ("network", "Network settings", "$mod+Shift+i", "exec {settings_page}network"),
    # off by default – tiling + workspaces only. Give them a key if you ever want them.
    ("split_h", "Next window to the right", "", "splith"),
    ("split_v", "Next window below", "", "splitv"),
    ("resize", "Resize mode (h/j/k/l or arrows)", "", 'mode "resize"'),
    ("float", "Floating on/off", "", "floating toggle"),
    ("layout_stack", "Layout: stacked", "", "layout stacking"),
    ("layout_tab", "Layout: tabbed", "", "layout tabbed"),
    ("layout_split", "Layout: toggle split", "", "layout toggle split"),
    ("scratch_show", "Show scratchpad", "", "scratchpad show"),
    ("scratch_move", "Move to scratchpad", "", "move scratchpad"),
]


def _fits(default, value):
    """A hand-edited value of the wrong type falls back to the default instead of breaking the
    config generation later (e.g. radius = "round"). Returns the value to keep."""
    if default is None or value is None:
        return value
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, (int, float)) and not isinstance(default, bool):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                return type(default)(value)
            except (TypeError, ValueError):
                return default
        return type(default)(value) if isinstance(default, float) else value
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    if isinstance(default, list):
        return value if isinstance(value, list) else default
    return value


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("outputs", "keys", "style_backup"):
            out[k] = _merge(out[k], v)
        elif k in out and not isinstance(out[k], dict):
            out[k] = copy.deepcopy(_fits(out[k], v))
        elif k in out and isinstance(out[k], dict) and not isinstance(v, dict) and k not in ("outputs", "keys", "style_backup"):
            pass                                    # a section replaced by a plain value – keep the defaults
        else:
            out[k] = copy.deepcopy(v)
    return out


def _migrate(data: dict) -> dict:
    """Older settings files → current names."""
    bar = data.get("bar", {})
    if "style" in bar and "layout" not in bar:
        bar["layout"] = {"floating": "modern", "solid": "solid"}.get(bar["style"], "modern")
    bar.pop("style", None)
    if isinstance(bar.get("network"), bool):
        bar["network"] = "name" if bar["network"] else "off"
    bar.pop("position", None)
    sb = data.get("theme", {}).get("style_backup", {})
    if "bar_style" in sb:
        sb["layout"] = {"floating": "modern", "solid": "solid"}.get(sb.pop("bar_style"), "modern")
    th = data.get("theme", {})
    if th.get("name") == "onyx":                   # Onyx was merged into Noir
        th["name"] = "noir"
    return data


LOAD_ERRORS: list[str] = []          # what went wrong reading settings.toml (shown by the apps)


def load() -> dict:
    """Your settings on top of the defaults. A settings.toml with a syntax error is kept aside
    (settings.toml.broken-DATE) and the defaults are used, so no app is locked out by a typo."""
    data = {}
    if paths.SETTINGS_FILE.exists():
        try:
            data = tomllib.loads(paths.SETTINGS_FILE.read_text())
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            import shutil
            import time
            raw = paths.SETTINGS_FILE.read_bytes()
            same = [p for p in paths.SETTINGS_FILE.parent.glob("settings.toml.broken-*") if p.read_bytes() == raw]
            keep = same[0] if same else paths.SETTINGS_FILE.with_name(f"settings.toml.broken-{time.strftime('%Y%m%d-%H%M%S')}")
            if not same:                            # one copy per broken version, not one per read
                try:
                    shutil.copy2(paths.SETTINGS_FILE, keep)
                except OSError:
                    pass
            msg = f"{paths.SETTINGS_FILE} has an error ({e}) – using the defaults; your file is kept as {keep.name}"
            if msg not in LOAD_ERRORS:
                LOAD_ERRORS.append(msg)
            import sys
            print("swayforge: " + msg, file=sys.stderr)
            data = {}
    return _merge(DEFAULTS, _migrate(data))


def save(s: dict) -> None:
    paths.ensure_dirs()
    header = ("# swayforge settings – safe to edit by hand,\n"
              "# then run `swayforge apply` (or save in the app).\n\n")
    from .fsutil import atomic_write
    atomic_write(paths.SETTINGS_FILE, header + tomlw.dumps(s))


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
