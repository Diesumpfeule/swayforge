"""Settings forms shared by the terminal app and swayforge Studio: every editable option with its
label, kind, choices and hint. Pure data – no UI toolkit imported here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import screensaver, sounds


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


SAVER_OPTS = [(label, key) for key, label in screensaver.SAVERS.items()]
ON_OFF = [("always", "always"), ("only via SSH/root", "needed"), ("never", "false")]

PAGES: list[tuple[str, str]] = [
    ("theme", "\U000f03d8  Theme"),
    ("wallpapers", "\U000f02e9  Wallpapers"),
    ("layout", "\U000f056e  Layout"),
    ("look", "\U000f00e3  Appearance"),
    ("bar", "\U000f062e  Bar modules"),
    ("display", "\U000f0379  Displays"),
    ("audio", "\U000f057e  Audio"),
    ("sound", "\U000f075a  System sounds"),
    ("bluetooth", "\U000f00af  Bluetooth"),
    ("network", "\U000f05a9  Network"),
    ("input", "\U000f030c  Keyboard & mouse"),
    ("shell", "\U000f018d  Terminal & prompt"),
    ("keys", "\U000f003b  Apps & shortcuts"),
    ("games", "\U000f0297  Games"),
    ("power", "\U000f06a5  Power & lock"),
    ("boot", "\U000f07b7  Boot & login"),
    ("security", "\U000f0483  Security"),
    ("apps", "\U000f03d6  Apps"),
    ("cleanup", "\U000f00e2  Cleanup & drives"),
    ("mounts", "\U000f02ca  Mount drives"),
    ("system", "\U000f0493  System & files"),
    ("about", "\U000f02fd  About & updates"),
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
        Field("look.tiling_only", "Tiling only", "bool",
              help="every window tiles, even dialogs · no floating, tabs or stacking"),
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
        "Animated wallpaper (videos, GIFs)",
        Field("theme.live_pause_fullscreen", "Pause while a fullscreen window covers it", "bool",
              help="saves CPU/GPU in games and videos"),
        Field("theme.live_pause_battery", "Pause on battery", "bool"),
        Field("theme.live_fps", "Limit frame rate", "choice",
              [("As the video is (hardware decoding)", 0), ("12 fps", 12), ("15 fps", 15), ("24 fps", 24),
               ("30 fps", 30)], help="lower = less work, but disables hardware decoding"),
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
        Field("bar.network", "Network", "choice",
              [("Wi-Fi name / IP (cable)", "name"), ("IP address", "ip"), ("Icon only", "icon"), ("Off", "off")],
              help="click opens the network settings"),
        Field("bar.bluetooth", "Bluetooth", "bool"),
        Field("bar.audio", "Volume", "bool", help="click = audio settings · scroll = volume"),
        Field("bar.mic", "Microphone", "bool", help="click = mute on/off"),
        Field("bar.media", "Music (Spotify, browser …)", "bool"),
        Field("bar.battery", "Battery (laptops)", "bool"),
        Field("bar.backlight", "Brightness (laptops)", "bool"),
        Field("bar.idle_inhibitor", "Stay-awake toggle", "bool"),
        Field("bar.tray", "Tray icons (Discord, Steam …)", "bool"),
    ],
    "sound": [
        "System sounds (generated – no sample files)",
        Field("sound.enabled", "Play system sounds", "bool",
              help="login chime, notifications, errors, plug/unplug – off by default"),
        Field("sound.pack", "Sound pack", "choice",
              [("Auto (follows theme / layout)", "auto")] + [(v, k) for k, v in sounds.PACKS.items()],
              help="gothic = church bell & organ · classic = 98 bleeps · wired = digital blips"),
        Field("sound.volume", "Volume", "float", help="0.1 – 1.0 (relative to the system volume)"),
        Field("sound.login", "Chime at login", "bool"),
        Field("sound.notify", "Sound for notifications", "bool"),
        "Try it:  swayforge sound test   ·   swayforge sound play bell",
    ],
    "input": [
        "Keyboard",
        Field("input.kb_layout", "Layout", help="us, de, ch … several: us,de"),
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
        "Screensaver",
        Field("power.screensaver", "Screensaver", "choice", SAVER_OPTS,
              help="choose one: it plays instead of a plain lock"),
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
    "security": [
        "Settings",
        Field("security.quarantine", "Move infected files to quarantine", "bool",
              help="off = only report · nothing is ever deleted"),
        Field("security.weekly_scan", "Weekly malware scan", "bool",
              help="in the background, you get a notification · Ctrl+S to switch"),
        Field("security.weekly_target", "Weekly scan covers", "choice",
              [("Downloads", "downloads"), ("Whole home folder", "home")]),
    ],
}
