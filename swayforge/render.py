"""Generates every config from settings.toml + theme + layout, backs up foreign files, reloads.

Two kinds of files:
  * generated ("owned") – belong to swayforge and are rewritten on every change.
                          Delete the line containing "swayforge generated" and swayforge
                          leaves that file alone from then on (you take it over).
  * yours ("stub")      – created once; they include the generated file. Whatever you
                          put there always wins.
"""
from __future__ import annotations

import json
import re
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import jinja2

from . import art_svg
from . import ascii as asc
from . import layouts, livewall, paths, settings, themes
from .system import SysInfo, detect, have, run

MARK = "swayforge generated"   # present in every file swayforge fully owns
OLD_MARKS = ("swayforge generiert",)
LAUNCHER = str(paths.HOME / ".local/bin/swayforge")
MANIFEST = paths.GEN_DIR / "manifest.json"

# Nerd Font icons
I = {
    "cpu": "", "mem": "\U000f035b", "gpu": "\U000f08ae", "temp": "",
    "wifi": "\U000f05a9", "eth": "\U000f0200", "offline": "\U000f05aa",
    "vol": ["\U000f057f", "\U000f0580", "\U000f057e"], "mute": "\U000f0581",
    "head": "\U000f02cb", "bt": "\U000f00af", "bt_on": "\U000f00b1", "bt_off": "\U000f00b2",
    "bat": ["\U000f007a", "\U000f007c", "\U000f007e", "\U000f0080", "\U000f0079"],
    "charge": "\U000f0084", "light": "\U000f00e0", "awake": "\U000f0176",
    "sleep": "\U000f06ca", "power": "", "clock": "\U000f0150", "music": "",
    "tasks": "", "game": "\U000f0297", "mic": "\U000f036c", "mic_off": "\U000f036d",
    "fedora": "", "start": "\U000f035c",
}


def has_mark(text: str) -> bool:
    return MARK in text or any(m in text for m in OLD_MARKS)


# ── Colour helpers ───────────────────────────────────────────────────
def hx(color: str) -> str:
    return color.lstrip("#")


def rgb(color: str) -> tuple[int, int, int]:
    h = hx(color)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hx_(color: str) -> str:
    return "#" + hx(color)


def rgba(color: str, alpha: float) -> str:
    r, g, b = rgb(color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a towards b by t (0..1)."""
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def sgr(color: str) -> str:
    """Truecolour ANSI code (for fastfetch)."""
    r, g, b = rgb(color)
    return f"38;2;{r};{g};{b}"


def bevel(c: dict) -> dict:
    """Colours for Win98-style 3D edges, derived from the theme."""
    face = mix(c["surface"], c["text"], 0.10)
    return {"face": face, "hi": mix(face, c["text"], 0.6), "lo": mix(face, c["crust"], 0.85),
            "dk": c["crust"], "pressed": mix(face, c["crust"], 0.35), "title": c["accent"],
            "title2": mix(c["accent"], c["base"], 0.55)}


# ── Commands ─────────────────────────────────────────────────────────
def terminal_cmd(s: dict, app_id: str = "", run_cmd: str = "") -> str:
    term = s["general"]["terminal"]
    parts = [term]
    if app_id:
        parts += ["--class", app_id]
    if run_cmd:
        parts += (["-e"] if term == "alacritty" else []) + [run_cmd]
    return " ".join(parts)


def settings_cmd(s: dict, page: str = "") -> str:
    run_cmd = f"{LAUNCHER} settings --page {page}" if page else LAUNCHER
    return terminal_cmd(s, "swayforge-settings", run_cmd)


def btop_cmd(s: dict) -> str:
    return terminal_cmd(s, "swayforge-btop", "btop")


def browser_cmd(s: dict) -> str:
    b = s["general"]["browser"]
    return {
        "firefox": "firefox", "chromium": "chromium-browser", "brave": "brave-browser",
        "librewolf": "librewolf", "zen": "flatpak run app.zen_browser.zen",
    }.get(b, b)


def files_cmd(s: dict) -> str:
    f = s["general"]["file_manager"]
    if f == "yazi":
        return terminal_cmd(s, "yazi", "yazi")
    return {"thunar": "thunar", "nautilus": "nautilus"}.get(f, f)


def cs2_watcher() -> str:
    p = paths.HOME / ".local/bin/swayforge-cs2-watcher"
    return str(p) if p.exists() else ""


CS2_CFG = paths.XDG_CONFIG / "cs2translate.json"


def cs2_theme(ctx: "Ctx", dry: bool) -> None:
    """Theme colours + font for the CS2 overlay (only the "theme" key; position etc. stay)."""
    if dry or not (paths.XDG_DATA / "cs2translate").is_dir():
        return
    try:
        cfg = json.loads(CS2_CFG.read_text()) if CS2_CFG.exists() else {}
    except (OSError, ValueError):
        return                                  # broken file → don't touch it
    if not isinstance(cfg, dict) or cfg.get("theme_locked"):
        return
    c, font = ctx.c, ctx.s["theme"]["font"]
    new = {"bg": c["crust"], "text": c["text"], "orig": c["overlay"], "ct": c["blue"],
           "t": c["yellow"], "all": c["green"], "logo": c["accent"], "font": font, "mono": font}
    if cfg.get("theme") != new:
        cfg["theme"] = new
        CS2_CFG.parent.mkdir(parents=True, exist_ok=True)
        CS2_CFG.write_text(json.dumps(cfg, indent=2) + "\n")


# ── Context ──────────────────────────────────────────────────────────
@dataclass
class Ctx:
    s: dict
    si: SysInfo
    theme: themes.Theme
    c: dict
    wallpaper_kind: str = "image"
    wallpaper_path: str = ""

    @property
    def layout(self) -> layouts.Layout:
        return layouts.get(self.s["bar"]["layout"])

    @property
    def art_name(self) -> str:
        return asc.resolve(self.s, self.theme)

    def _ui(self) -> float:
        try:
            return max(0.2, min(1.0, float(self.s["look"].get("ui_opacity", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def _ua(self, color: str, alpha: float = 1.0) -> str:
        """Colour with the layout transparency applied (plain colour when untouched)."""
        # island layouts scale here; the others are faded afterwards by fade_css()
        a = round(alpha * (self._ui() if self.layout.id in ("modern", "minimal", "glass", "solid", "sidebar") else 1.0), 2)
        return hx_(color) if a >= 1.0 else rgba(color, a)

    def _uhex(self, alpha: float = 0.93) -> str:
        """Two hex digits of alpha for mako."""
        return f"{round(255 * alpha * self._ui()):02x}"

    def as_dict(self) -> dict:
        keys = []
        repl = {
            "{term}": terminal_cmd(self.s), "{browser}": browser_cmd(self.s),
            "{files}": files_cmd(self.s), "{btop}": btop_cmd(self.s),
            "{settings_page}": settings_cmd(self.s, "@@").replace("@@", ""),
            "{settings}": settings_cmd(self.s), "{sf}": LAUNCHER,
        }
        for _aid, label, key, cmd in settings.keybinds(self.s):
            if not key.strip():
                continue
            for k, v in repl.items():
                cmd = cmd.replace(k, v)
            keys.append((label, key, cmd))
        used_keys = {k for _l, k, _c in keys}
        sections = [x for x in self.s["prompt"]["sections"] if x in settings.PROMPT_SECTIONS]
        if "char" not in sections:
            sections.append("char")
        return dict(
            s=self.s, si=self.si, c=self.c, ansi=self.theme.ansi, dark=self.theme.dark,
            theme=self.theme, keys=keys, used_keys=used_keys, term_cmd=terminal_cmd(self.s), sf=LAUNCHER,
            wallpaper_kind=self.wallpaper_kind, wallpaper_path=self.wallpaper_path,
            outputs=sorted(self.s["display"]["outputs"].items()),
            custom_conf=str(paths.SWAY_CUSTOM), gen_dir=str(paths.GEN_DIR),
            spaceship_dir=str(paths.SPACESHIP_DIR), p=self.s["prompt"], sections=sections,
            hx=hx, rgba=rgba, mix=mix, ua=self._ua, uhex=self._uhex, ui=self._ui(), mark=MARK, cs2_watcher=cs2_watcher(),
            layout=self.layout.id, bv=bevel(self.c), user=os.environ.get("USER", "user"), font=self.s["theme"]["font"],
            art=asc.art(self.art_name), banner=asc.banner, extras=art_svg.extras(),
            ext_shell=external_shell(self.s),
        )


def external_shell(s: dict) -> str:
    """Command of the desktop shell that replaces swayforge's bar + notifications, or '' for swayforge's own."""
    if s["general"].get("shell", "swayforge") != "noctalia":
        return ""
    return "noctalia" if have("noctalia") or not have("noctalia-shell") else "noctalia-shell"


def make_ctx(s: dict, si: SysInfo | None = None) -> Ctx:
    si = si or detect()
    th = themes.get(s["theme"]["name"])
    return Ctx(s, si, th, th.with_accent(s["theme"].get("accent", "")))


_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(paths.TEMPLATES)),
    undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True,
    keep_trailing_newline=True,
)


def tpl(name: str, d: dict) -> str:
    return _env.get_template(name).render(**d)


# ── Waybar ───────────────────────────────────────────────────────────
def waybar_config(ctx: Ctx) -> dict:
    s, si, b, lay = ctx.s, ctx.si, ctx.s["bar"], ctx.layout.id
    text_only = lay == "wired"
    icons_only = lay == "sidebar"

    def f(icon: str, value: str, word: str = "") -> str:
        """Module format depending on the layout."""
        if text_only:
            return f"[{word} {value}]".replace("[ ", "[") if word else f"[{value}]"
        if icons_only:
            return icon
        return f"{icon}  {value}"

    net_mode = b.get("network", "name")

    def net_fmt(icon: str, value: str) -> str:
        if net_mode == "icon":
            return "[net]" if text_only else icon
        if net_mode == "ip" and value != "offline":
            value = "{ipaddr}"
        return f(icon, value, "net")

    wanted = [
        ("media", "mpris", True), ("gamemode", "custom/gamemode", True),
        ("cpu", "cpu", True), ("gpu", "custom/gpu", bool(si.gpu_busy)),
        ("memory", "memory", True), ("temperature", "temperature", True),
        ("taskmanager", "custom/taskmanager", True), ("network", "network", b.get("network") != "off"),
        ("bluetooth", "bluetooth", si.bluetooth), ("audio", "pulseaudio", True),
        ("mic", "pulseaudio#mic", True), ("backlight", "backlight", si.laptop),
        ("battery", "battery", si.laptop), ("idle_inhibitor", "idle_inhibitor", True),
        ("tray", "tray", True),
    ]
    status = [mod for key, mod, ok in wanted if b.get(key) and ok]
    if lay == "minimal":
        status = [m for m in status if m in ("tray",)]

    ws = "sway/workspaces"
    if lay in ("win98", "winxp", "win7"):
        left = ["custom/start", ws, "wlr/taskbar"]
        center: list[str] = []
        right = ["group/status", "custom/power"]
    elif lay == "win11":
        left, center = [ws], ["custom/start", "wlr/taskbar"]
        right = ["group/status", "custom/power"]
    elif lay == "touch":
        left, center = ["custom/start", "custom/osk"], [ws]
        right = ["group/status", "custom/power"]
    elif lay == "minimal":
        left, center, right = [], [ws, "clock"], status + ["custom/power"]
    elif lay == "sidebar":
        left, center, right = [ws], [], status + ["clock", "custom/power"]
    else:
        left = [ws, "sway/mode"] + (["sway/window"] if b["window_title"] else [])
        center, right = ["clock"], status + ["custom/power"]
        if lay == "cathedral":
            left, center, right = ["custom/orn-l"] + left, ["custom/orn-c1", "clock", "custom/orn-c2"], right + ["custom/orn-r"]

    clock_fmt = "  ".join(x for x in (b["date_format"], b["clock_format"]) if x)
    cathedral = lay == "cathedral"
    if cathedral:
        orn = f"<span color='{ctx.c['accent']}'>✠</span>"
        clock = {"format": f"{orn}  {{:{b['clock_format']}}}  {orn}",
                 "format-alt": f"{orn}  {{:%A · %d %B %Y}}  {orn}"}
        orn_mods = {"custom/orn-l": "☩ ❦ †", "custom/orn-r": "† ❦ ☩",
                    "custom/orn-c1": "⚜ ✧ ⚜ ❧", "custom/orn-c2": "❧ ⚜ ✧ ⚜"}
    elif text_only:
        clock = {"format": "[{:%H:%M:%S}]", "interval": 1, "format-alt": f"[{{:{clock_fmt}}}]"}
    elif icons_only:
        clock = {"format": "{:%H\n%M}", "format-alt": "{:%d\n%m}"}
    elif lay in ("win98", "winxp", "win7", "win11", "touch"):
        clock = {"format": f"{{:{b['clock_format']}}}", "format-alt": f"{{:{clock_fmt}}}"}
    else:
        clock = {"format": f"{I['clock']}  {{:{clock_fmt}}}", "format-alt": f"{I['clock']}  {{:{b['clock_format']}}}"}
    clock |= {
        "tooltip-format": "<tt>{calendar}</tt>",
        "calendar": {"mode": "month", "weeks-pos": "left", "on-scroll": 1,
                     "format": {"months": f"<span color='{ctx.c['accent']}'><b>{{}}</b></span>",
                                "weeks": f"<span color='{ctx.c['overlay']}'>W{{}}</span>",
                                "weekdays": f"<span color='{ctx.c['subtext']}'><b>{{}}</b></span>",
                                "today": f"<span color='{ctx.c['red']}'><b><u>{{}}</u></b></span>"}},
        "actions": {"on-scroll-up": "shift_up", "on-scroll-down": "shift_down", "on-click-right": "mode"},
    }

    temp = {"critical-threshold": 85, "format": f(I["temp"], "{temperatureC}°C", "tmp"),
            "interval": 5, "on-click": btop_cmd(s)}
    if si.hwmon_cpu:
        temp |= {"hwmon-path-abs": si.hwmon_cpu, "input-filename": "temp1_input"}

    position = ctx.layout.position
    cfg = {
        "layer": "top", "position": position, "spacing": 0,
        "modules-left": left, "modules-center": center, "modules-right": right,
        ws: {"disable-scroll": False, "all-outputs": False,
             "format": "{name}" if not text_only else "[{name}]"} | (
            {"format": "{icon}", "format-icons": {str(i): r for i, r in enumerate(
                ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]) if i} | {"default": "†"}}
            if lay == "cathedral" else {}),
        "sway/mode": {"format": "{}" if not text_only else "<{}>"},
        "sway/window": {"max-length": 50, "icon": False,
                        "format": "{}" if not text_only else ":: {}"},
        "clock": clock,
        "cpu": {"format": f(I["cpu"], "{usage}%", "cpu"), "interval": 3, "on-click": btop_cmd(s)},
        "memory": {"format": f(I["mem"], "{percentage}%", "mem"), "interval": 5, "on-click": btop_cmd(s),
                   "tooltip-format": "{used:0.1f} / {total:0.1f} GiB used"},
        "temperature": temp,
        "custom/taskmanager": {"format": "[top]" if text_only else I["tasks"],
                               "tooltip-format": "Task manager (btop)", "on-click": btop_cmd(s)},
        "custom/gamemode": {"exec": f"{LAUNCHER} gamemode status" + (" --text" if text_only else ""),
                            "return-type": "json", "interval": "once", "signal": 8, "format": "{}",
                            "on-click": f"{LAUNCHER} gamemode"},
        "network": {
            "format-wifi": net_fmt(I["wifi"], "{essid}"), "format-ethernet": net_fmt(I["eth"], "{ipaddr}"),
            "format-disconnected": net_fmt(I["offline"], "offline"), "interval": 5,
            "tooltip-format": "{ifname}: {ipaddr}/{cidr}\n↓ {bandwidthDownBytes}  ↑ {bandwidthUpBytes}",
            "on-click": settings_cmd(s, "network"),
            "on-click-right": terminal_cmd(s, "nmtui", "nmtui"),
        },
        "bluetooth": {"format": "[bt]" if text_only else I["bt"],
                      "format-connected": f(I["bt_on"], "{num_connections}", "bt"),
                      "format-off": "[bt off]" if text_only else I["bt_off"],
                      "format-disabled": "[bt off]" if text_only else I["bt_off"],
                      "tooltip-format-connected": "{device_enumerate}",
                      "tooltip-format-enumerate-connected": "{device_alias}",
                      "on-click": settings_cmd(s, "bluetooth"), "on-click-right": "blueman-manager"},
        "pulseaudio": {"format": f("{icon}", "{volume}%", "vol"),
                       "format-muted": f(I["mute"], "muted", "vol"),
                       "format-icons": {"headphone": I["head"], "default": I["vol"]},
                       "scroll-step": 5, "on-click": settings_cmd(s, "audio"),
                       "on-click-right": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
                       "on-click-middle": "pavucontrol"},
        "pulseaudio#mic": {"format": "{format_source}",
                           "format-source": "[mic]" if text_only else I["mic"],
                           "format-source-muted": "[mic off]" if text_only else I["mic_off"],
                           "tooltip-format": "Microphone: {source_volume}% – click to mute",
                           "on-click": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
                           "on-scroll-up": "wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 5%+",
                           "on-scroll-down": "wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 5%-"},
        "backlight": {"format": f(I["light"], "{percent}%", "lit"),
                      "on-scroll-up": "brightnessctl set 5%+", "on-scroll-down": "brightnessctl set 5%-"},
        "battery": {"states": {"warning": 25, "critical": 12},
                    "format": f("{icon}", "{capacity}%", "bat"),
                    "format-charging": f(I["charge"], "{capacity}%", "chg"),
                    "format-icons": I["bat"], "tooltip-format": "{timeTo}"},
        "idle_inhibitor": {"format": "{icon}",
                           "format-icons": {"activated": "[awake]" if text_only else I["awake"],
                                            "deactivated": "[idle]" if text_only else I["sleep"]},
                           "tooltip-format-activated": "Stay awake: on",
                           "tooltip-format-deactivated": "Stay awake: off"},
        "mpris": {"format": f(I["music"], "{title}", "play"), "format-paused": f(I["music"], "⏸ {title}", "pause"),
                  "max-length": 40},
        "tray": {"spacing": 10, "icon-size": 16},
        "custom/power": {"format": "[off]" if text_only else ("☠" if lay in ("cathedral", "dread") else I["power"]),
                         "tooltip-format": "Power menu",
                         "on-click": f"{LAUNCHER} power"},
    }
    if cathedral:
        for k, v in orn_mods.items():
            cfg[k] = {"format": f"<span color='{ctx.c['accent']}'>{v}</span>", "tooltip": False}
    if position == "left":
        cfg["width"] = max(44, b["height"] + 10)
    else:
        cfg["height"] = (max(b["height"], 56) if lay == "touch"
                         else b["height"] + {"win7": 6, "winxp": 2, "win11": 10}.get(lay, 0))
    if si.gpu_busy:
        cfg["custom/gpu"] = {"exec": f"cat {si.gpu_busy}", "interval": 3, "on-click": btop_cmd(s),
                             "format": f(I["gpu"], "{}%", "gpu"), "tooltip-format": "GPU load"}
    if lay in ("win98", "winxp", "win7", "win11", "touch"):
        cfg["custom/start"] = {"format": (f"{I['fedora']}  Start" if lay == "win98" else
                                          "\uf17a  start" if lay == "winxp" else I["fedora"]),
                               "tooltip-format": "Start menu – apps (Super+D)",
                               "on-click": f"{LAUNCHER} start", "on-click-right": f"{LAUNCHER} power"}
        cfg["wlr/taskbar"] = {"format": "{icon}  {title:.22}" if lay in ("win98", "winxp") else "{icon}",
                              "icon-size": 16 if lay in ("win98", "winxp") else 32 if lay == "touch" else 24,
                              "tooltip-format": "{title}", "on-click": "activate",
                              "on-click-middle": "close", "on-click-right": "fullscreen"}
        cfg[ws]["persistent-workspaces"] = {}
        if lay == "touch":
            cfg["custom/osk"] = {"format": "\U000f030c", "tooltip-format": "On-screen keyboard (wvkbd)",
                                 "on-click": "sh -c 'pgrep -x wvkbd-mobintl >/dev/null && "
                                             "pkill -RTMIN -x wvkbd-mobintl || exec wvkbd-mobintl -L 300'"}
        cfg["group/status"] = {"orientation": "horizontal", "modules": status + ["clock"]}
    return cfg


# ── Small generated files ────────────────────────────────────────────
def mangohud(ctx: Ctx) -> str:
    c = {k: hx(v) for k, v in ctx.c.items()}
    return f"""# {MARK} – delete this line to take the file over yourself
legacy_layout=false
toggle_hud=Shift_R+F12
position=top-left
round_corners={ctx.s['look']['radius']}
background_alpha=0.6
background_color={c['base']}
text_color={c['text']}
font_size=20
fps
frametime
frame_timing=1
gpu_stats
gpu_temp
gpu_color={c['red']}
cpu_stats
cpu_temp
cpu_color={c['blue']}
ram
ram_color={c['magenta']}
vram
vram_color={c['magenta']}
engine_color={c['accent']}
frametime_color={c['accent']}
"""


def discord_theme_dirs() -> list[tuple[Path, Path]]:
    """(theme folder, client folder) for each Discord mod found. Needs the client folder to exist already."""
    flat = paths.HOME / ".var/app/dev.vencord.Vesktop/config"
    homes = [
        (flat / "vesktop", "themes"), (C / "vesktop", "themes"),
        (flat / "Vencord", "themes"), (C / "Vencord", "themes"),
        (flat / "BetterDiscord", "themes"), (C / "BetterDiscord", "themes"),
    ]
    return [(h / sub, h) for h, sub in homes if h.is_dir()]


def palette_json(ctx: Ctx) -> str:
    """The active look as plain data – wolfforge (LibreWolf) and other tools read this."""
    return json.dumps({
        "theme": ctx.theme.id, "label": ctx.theme.label, "dark": ctx.theme.dark, "colors": ctx.c,
        "ansi": ctx.theme.ansi, "bevel": bevel(ctx.c), "font": ctx.s["theme"]["font"], "font_size": ctx.s["theme"]["font_size"],
        "radius": ctx.s["look"]["radius"], "layout": ctx.s["bar"]["layout"], "art": ctx.art_name,
        "art_lines": asc.art(ctx.art_name),
    }, indent=2, ensure_ascii=False) + "\n"


def fastfetch(ctx: Ctx) -> str:
    c = ctx.c
    cfg = {
        "$schema": "https://github.com/fastfetch-cli/fastfetch/raw/dev/doc/json_schema.json",
        "logo": {"type": "file", "source": str(paths.GEN_DIR / "fastfetch-logo.txt"),
                 "color": {"1": sgr(c["accent"]), "2": sgr(c["accent2"]),
                           "3": sgr(mix(c["accent"], c["base"], 0.45))},
                 "padding": {"top": 1, "right": 3}},
        "display": {"separator": "  ", "color": {"keys": sgr(c["accent"]), "title": sgr(c["accent2"])},
                    "key": {"width": 11}},
        "modules": [
            "title", {"type": "separator", "string": "─"},
            {"type": "os", "key": "\uf30a os"}, {"type": "kernel", "key": " kernel"},
            {"type": "uptime", "key": "\U000f0150 uptime"}, {"type": "packages", "key": "\U000f03d6 pkgs"},
            {"type": "wm", "key": " wm"}, {"type": "terminal", "key": " term"},
            {"type": "shell", "key": " shell"}, {"type": "cpu", "key": " cpu"},
            {"type": "gpu", "key": "\U000f08ae gpu"}, {"type": "memory", "key": "\U000f035b ram"},
            {"type": "disk", "key": "\U000f02ca disk", "folders": "/"},
            {"type": "localip", "key": "\U000f0a5f ip"}, "break",
            {"type": "colors", "symbol": "block"},
        ],
    }
    return f"// {MARK} – delete this line to take the file over yourself\n" + \
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"


def cava(ctx: Ctx) -> str:
    c = ctx.c
    return f"""; {MARK} – delete this line to take the file over yourself
[general]
bar_width = 2
bar_spacing = 1

[color]
background = default
gradient = 1
gradient_count = 4
gradient_color_1 = '{c['accent2']}'
gradient_color_2 = '{c['accent']}'
gradient_color_3 = '{c['yellow']}'
gradient_color_4 = '{c['red']}'
"""


def fontconfig(ctx: Ctx) -> str:
    font = ctx.s["theme"]["font"]
    aliases = "\n".join(
        f"  <alias binding=\"same\">\n    <family>{fam}</family>\n    <prefer>\n"
        f"      <family>{font}</family>\n      <family>Noto Color Emoji</family>\n"
        f"    </prefer>\n  </alias>"
        for fam in ("sans-serif", "serif", "monospace", "system-ui"))
    return ("<?xml version=\"1.0\"?>\n<!DOCTYPE fontconfig SYSTEM \"urn:fontconfig:fonts.dtd\">\n"
            f"<!-- {MARK}: makes {font} the default for every app (browser, GTK, Qt …) -->\n"
            f"<fontconfig>\n{aliases}\n</fontconfig>\n")


def gtk_settings(ctx: Ctx, gtk4: bool) -> str:
    t = ctx.s["theme"]
    lines = [f"# {MARK}", "[Settings]",
             f"gtk-application-prefer-dark-theme={'true' if ctx.theme.dark else 'false'}",
             f"gtk-icon-theme-name={icon_theme(ctx)}",
             f"gtk-cursor-theme-name={t['cursor_theme']}",
             f"gtk-cursor-theme-size={t['cursor_size']}",
             f"gtk-font-name={ui_font(ctx)} {t['font_size']}",
             f"gtk-decoration-layout={button_layout(ctx)}"]
    if not gtk4:
        lines.insert(2, f"gtk-theme-name={gtk_theme(ctx)}")
    return "\n".join(lines) + "\n"


def ui_font(ctx: Ctx) -> str:
    return ctx.s["theme"]["font"] if ctx.s["theme"]["font_everywhere"] else "Noto Sans"


def button_layout(ctx: Ctx) -> str:
    return "menu:close" if ctx.s["look"]["gtk_buttons"] else ":"


def gtk_theme(ctx: Ctx) -> str:
    return "adw-gtk3-dark" if ctx.theme.dark else "adw-gtk3"


def icon_theme(ctx: Ctx) -> str:
    it = ctx.s["theme"]["icon_theme"]
    if it == "auto":
        return "Papirus-Dark" if ctx.theme.dark else "Papirus-Light"
    return it


def environment(ctx: Ctx, shell: bool) -> str:
    t = ctx.s["theme"]
    env = {
        "QT_QPA_PLATFORM": "wayland;xcb",
        "QT_WAYLAND_DISABLE_WINDOWDECORATION": "1",
        "ELECTRON_OZONE_PLATFORM_HINT": "auto",
        "MOZ_ENABLE_WAYLAND": "1",
        "_JAVA_AWT_WM_NONREPARENTING": "1",
        "XCURSOR_THEME": t["cursor_theme"],
        "XCURSOR_SIZE": str(t["cursor_size"]),
    }
    q = (lambda v: f'"{v}"') if shell else (lambda v: v)
    return f"# {MARK}\n" + "".join(f"{k}={q(v)}\n" for k, v in env.items())


# ── Which file is responsible for what? (for the ✎ buttons) ──────────
C = paths.XDG_CONFIG
CONFIG_FILES: dict[str, tuple[str, Path]] = {
    "settings": ("swayforge settings", paths.SETTINGS_FILE),
    "sway": ("Sway – your additions", paths.SWAY_CUSTOM),
    "waybar": ("Waybar – modules & clicks", C / "waybar/config.jsonc"),
    "waybar_css": ("Waybar – look (CSS)", C / "waybar/style.css"),
    "rofi": ("Rofi launcher", C / "rofi/config.rasi"),
    "kitty": ("kitty", C / "kitty/kitty.conf"),
    "alacritty": ("Alacritty", C / "alacritty/alacritty.toml"),
    "zsh": ("zsh", paths.HOME / ".zshrc"),
    "spaceship": ("Spaceship prompt", paths.HOME / ".spaceshiprc.zsh"),
    "fastfetch": ("fastfetch", C / "fastfetch/config.jsonc"),
    "fonts": ("Fonts (fontconfig)", C / "fontconfig/conf.d/90-swayforge.conf"),
    "mako": ("Notifications (mako)", C / "mako/config"),
    "swaylock": ("Lock screen (swaylock)", C / "swaylock/config"),
    "gtk": ("GTK apps (CSS)", C / "gtk-3.0/gtk.css"),
    "btop": ("btop", C / "btop/btop.conf"),
    "mangohud": ("MangoHud", C / "MangoHud/MangoHud.conf"),
    "cava": ("cava", C / "cava/config"),
    "ascii": ("Your ASCII art folder", paths.CONFIG_DIR / "ascii/README.txt"),
}


def file_for(path: str, s: dict) -> str:
    """Settings path → responsible file (key in CONFIG_FILES)."""
    term = s["general"]["terminal"]
    table = [
        ("look.terminal", term), ("general.terminal", term), ("theme.font", "fonts"),
        ("theme.ascii", "ascii"), ("theme.icon", "gtk"), ("theme.cursor", "sway"), ("theme.", "settings"),
        ("look.radius", "waybar_css"), ("look.gtk", "gtk"), ("look.", "sway"),
        ("bar.layout", "waybar_css"), ("bar.height", "waybar"), ("bar.", "waybar"),
        ("input.", "sway"), ("display.", "sway"), ("shell.fastfetch", "fastfetch"),
        ("shell.", "zsh"), ("prompt.", "spaceship"), ("general.", "sway"),
        ("power.", "settings"), ("boot.", "settings"), ("login.", "settings"),
    ]
    for prefix, key in table:
        if path.startswith(prefix):
            return key
    return "settings"


# ── Writing with backups ─────────────────────────────────────────────
@dataclass
class Result:
    written: list[str] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    detached: list[str] = field(default_factory=list)
    backup_dir: Path | None = None


class Writer:
    def __init__(self, dry: bool = False):
        self.dry = dry
        self.res = Result()
        self.stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            self.manifest: set[str] = set(json.loads(MANIFEST.read_text()))
        except (OSError, ValueError):
            self.manifest = set()

    def _backup(self, path: Path) -> None:
        if self.res.backup_dir is None:
            self.res.backup_dir = paths.BACKUP_DIR / self.stamp
        rel = path.relative_to(paths.HOME) if path.is_relative_to(paths.HOME) else Path(path.name)
        dest = self.res.backup_dir / rel
        if not self.dry:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        self.res.backups.append(str(rel))

    def owned(self, path: Path, content: str) -> None:
        """File belongs to swayforge – unless you removed the marker."""
        if path.exists():
            old = path.read_text(errors="replace")
            if old == content:
                self.manifest.add(str(path))
                return
            if not has_mark(old):
                if str(path) in self.manifest:      # you took it over → hands off
                    self.res.detached.append(str(path))
                    return
                self._backup(path)                  # foreign file (old rice) → back up
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.manifest.add(str(path))
        self.res.written.append(str(path))

    def stub(self, path: Path, content: str, must_contain: str) -> None:
        """File belongs to you: only created when missing or when the include line is missing."""
        if path.exists():
            old = path.read_text(errors="replace")
            if must_contain in old:
                return
            self._backup(path)
            self.res.notes.append(f"{path} replaced (old version in backup)")
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.res.written.append(str(path))

    def save_manifest(self) -> None:
        if not self.dry:
            MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST.write_text(json.dumps(sorted(self.manifest), indent=0))


def prune_backups(keep: int = 15) -> None:
    if not paths.BACKUP_DIR.is_dir():
        return
    dirs = sorted(d for d in paths.BACKUP_DIR.iterdir() if d.is_dir())
    for d in dirs[:-keep]:
        shutil.rmtree(d, ignore_errors=True)


def wallpaper(ctx: Ctx, w: Writer) -> None:
    wp = ctx.s["theme"]["wallpaper"]
    if wp == "solid":
        ctx.wallpaper_kind = "solid"
        return
    if wp not in ("", "theme"):
        p = Path(os.path.expanduser(wp))
        if p.is_file() and livewall.is_video(p):
            ctx.wallpaper_kind, ctx.wallpaper_path = "video", str(p)
            script = (f"#!/bin/sh\n# {MARK} – starts the animated wallpaper (mpvpaper) unless it already plays\n"
                      f"command -v mpvpaper >/dev/null || exit 0\n"
                      f"pgrep -af mpvpaper | grep -qF {shlex.quote(str(p))} && exit 0\n"
                      f"pkill -x mpvpaper; sleep 0.3\n"
                      f"mpvpaper -f -o {shlex.quote(livewall.mpv_options(ctx.s))} ALL {shlex.quote(str(p))}\n"
                      f"pgrep -f '[l]ivewall guard' >/dev/null || nohup {LAUNCHER} livewall guard >/dev/null 2>&1 &\n")
            w.owned(paths.GEN_DIR / "livewall.sh", script)
            return
        if p.is_file():
            ctx.wallpaper_kind, ctx.wallpaper_path = "image", str(p)
            return
        w.res.notes.append(f"Wallpaper {p} not found – using the theme wallpaper")
    svg = paths.GEN_DIR / "wallpaper.svg"
    # the rendered picture lives in the wallpaper folder (visible, pickable, yours to keep),
    # one file per theme; only the SVG source stays in the generated folder
    png = paths.WALLPAPER_DIR / f"swayforge-{ctx.theme.id}.png"
    style = ctx.theme.wallpaper_style
    content = tpl(f"wallpaper-{style}.svg.j2", ctx.as_dict())
    changed = not svg.exists() or svg.read_text() != content or not png.exists()
    if not w.dry:
        svg.parent.mkdir(parents=True, exist_ok=True)
        svg.write_text(content)
        png.parent.mkdir(parents=True, exist_ok=True)
        if changed and have("rsvg-convert"):
            run(["rsvg-convert", "-w", "3840", "-h", "2160", "-o", str(png), str(svg)])
    ctx.wallpaper_kind = "image"
    ctx.wallpaper_path = str(png if have("rsvg-convert") else svg)


def validate_sway(content: str) -> str | None:
    """Returns an error message or None."""
    if not have("sway"):
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
        f.write(content)
        tmp = f.name
    try:
        r = run(["sway", "-C", "-c", tmp], timeout=20)
    except subprocess.TimeoutExpired:
        return None
    finally:
        os.unlink(tmp)
    if r.returncode != 0:
        msg = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "error" in l)
        return msg or (r.stdout + r.stderr).strip()[-800:]
    return None


SWAY_CUSTOM_STUB = """# Your own Sway settings. This file belongs to you –
# swayforge never overwrites it. It is loaded last, so it can override
# or extend anything in the generated config.
#
# Examples:
#   bindsym $mod+p exec keepassxc
#   for_window [app_id="mpv"] floating enable
#   assign [class="steam"] workspace number 9
#   gaps inner 20
#   input type:keyboard xkb_options caps:escape
"""

ASCII_README = """Put your own ASCII art here as <name>.txt (plain text, max ~40 columns wide).
It then appears in swayforge → Theme → ASCII art, in fastfetch, the boot screen
and the login screen.
"""


def render_all(s: dict | None = None, dry: bool = False, si: SysInfo | None = None) -> Result:
    from . import boot                      # avoid import cycle
    s = s or settings.load()
    paths.ensure_dirs()
    ctx = make_ctx(s, si)
    w = Writer(dry)
    wallpaper(ctx, w)
    d = ctx.as_dict()
    seen: dict[str, str] = {}
    for label, key, _cmd in d["keys"]:
        k = key.replace("$mod", s["general"]["mod"]).lower()
        if k in seen:
            w.res.notes.append(f"Duplicate shortcut: {key} ({seen[k]} / {label}) – the later one wins")
        seen[k] = label

    # Sway (validated)
    sway = tpl("sway.conf.j2", d)
    if not dry:
        if not paths.SWAY_CUSTOM.exists():
            paths.SWAY_CUSTOM.parent.mkdir(parents=True, exist_ok=True)
            paths.SWAY_CUSTOM.write_text(SWAY_CUSTOM_STUB)
        (paths.CONFIG_DIR / "ascii").mkdir(parents=True, exist_ok=True)
        if not (paths.CONFIG_DIR / "ascii/README.txt").exists():
            (paths.CONFIG_DIR / "ascii/README.txt").write_text(ASCII_README)
    err = validate_sway(sway)
    if err:
        w.res.errors.append("Sway config invalid – not applied:\n" + err)
    else:
        w.owned(C / "sway/config", sway)
    w.owned(C / "sway/environment", environment(ctx, shell=True))
    w.owned(C / "environment.d/90-swayforge.conf", environment(ctx, shell=False))

    # Screen sharing (Discord/Vesktop, browsers, OBS): portal routing for Sway
    w.owned(C / "xdg-desktop-portal/sway-portals.conf",
            f"# {MARK} – don't edit\n[preferred]\ndefault=gtk\n"
            "org.freedesktop.impl.portal.ScreenCast=wlr\norg.freedesktop.impl.portal.Screenshot=wlr\n")

    # Waybar: generated base + your config that includes it (your values win)
    w.owned(C / "waybar/swayforge.jsonc",
            f"// {MARK} – don't edit, put your own values in config.jsonc\n"
            + json.dumps(waybar_config(ctx), indent=2, ensure_ascii=False) + "\n")
    w.stub(C / "waybar/config.jsonc",
           '// Your Waybar config. Anything you add here wins over swayforge.jsonc.\n'
           '// Example: "clock": { "format": "{:%H:%M:%S}", "interval": 1 },\n'
           '{\n  "include": ["~/.config/waybar/swayforge.jsonc"]\n}\n',
           "swayforge.jsonc")
    w.owned(C / "waybar/swayforge.css", fade_css(tpl("waybar.css.j2", d), ctx._ui() if ctx.layout.id not in ("modern", "minimal", "glass", "solid") else 1.0))
    w.stub(C / "waybar/style.css",
           '@import "swayforge.css";\n\n/* Your own Waybar rules below – they override the theme. */\n',
           '@import "swayforge.css"')

    # Rofi
    w.owned(C / "rofi/themes/swayforge.rasi", fade_css(tpl("rofi.rasi.j2", d | {"icons": icon_theme(ctx)}), ctx._ui() if ctx.layout.id not in ("modern", "minimal", "glass", "solid", "sidebar") else 1.0, skip=()))
    w.stub(C / "rofi/config.rasi",
           '@theme "swayforge"\n\n/* Your own Rofi tweaks below, e.g.\n'
           'configuration { modi: "drun,run,window,filebrowser"; }\n*/\n',
           '@theme "swayforge"')

    # Notifications, lock screen
    w.owned(C / "mako/config", tpl("mako.j2", d))
    w.owned(C / "swaylock/config", tpl("swaylock.j2", d))

    # Terminals (both, so switching just works)
    w.owned(C / "kitty/swayforge.conf", tpl("kitty.j2", d))
    w.stub(C / "kitty/kitty.conf",
           "include swayforge.conf\n\n# Your own kitty settings below.\n", "include swayforge.conf")
    w.owned(C / "alacritty/swayforge.toml", tpl("alacritty.j2", d))
    w.stub(C / "alacritty/alacritty.toml",
           '[general]\nimport = ["~/.config/alacritty/swayforge.toml"]\n\n# Your own Alacritty settings below.\n',
           "swayforge.toml")

    # Your terminal for other apps: Thunar "Open Terminal Here", text files that open in a
    # terminal editor (GLib/gio asks xdg-terminal-exec), anything that uses exo-open
    term = s["general"]["terminal"]
    desktop_id = {"alacritty": "Alacritty.desktop"}.get(term, f"{term}.desktop")
    w.owned(C / "xdg-terminals.list", f"# {MARK} – your terminal for apps that need one\n{desktop_id}\n")
    run_flag = "-e " if term == "alacritty" else ""
    w.owned(paths.XDG_DATA / "xfce4/helpers/swayforge-terminal.desktop",
            f"# {MARK}\n[Desktop Entry]\nNoDisplay=true\nVersion=1.0\nType=X-XFCE-Helper\n"
            f"X-XFCE-Category=TerminalEmulator\nName={term}\nIcon={term}\n"
            f"X-XFCE-Commands={term}\nX-XFCE-CommandsWithParameter={term} {run_flag}%s\n")
    helpers = C / "xfce4/helpers.rc"
    old = helpers.read_text(errors="replace") if helpers.exists() else ""
    if "TerminalEmulator=" not in old and not dry:   # don't override a choice you made in Thunar
        helpers.parent.mkdir(parents=True, exist_ok=True)
        helpers.write_text(old + ("" if not old or old.endswith("\n") else "\n")
                           + "TerminalEmulator=swayforge-terminal\n")

    # Shell + prompt + fastfetch
    w.owned(paths.GEN_DIR / "zshrc.zsh", tpl("zsh.j2", d))
    w.owned(paths.GEN_DIR / "spaceship.zsh", tpl("spaceship.j2", d))
    if s["shell"]["zsh"]:
        w.stub(paths.HOME / ".zshrc",
               f'source "{paths.GEN_DIR}/zshrc.zsh"\n\n# Your own zsh stuff below.\n',
               "swayforge/generated/zshrc.zsh")
        w.stub(paths.HOME / ".spaceshiprc.zsh",
               "# Your Spaceship settings – they override swayforge's.\n"
               "# All options: https://spaceship-prompt.sh/options/\n"
               "# Example:\n#   SPACESHIP_CHAR_SYMBOL=\"λ \"\n#   SPACESHIP_DIR_TRUNC=0\n",
               "Spaceship")
    if not dry:                                     # no marker possible in a logo file
        (paths.GEN_DIR / "fastfetch-logo.txt").write_text(asc.fastfetch_logo(ctx.art_name))
    w.owned(C / "fastfetch/config.jsonc", fastfetch(ctx))
    if not dry:                                     # for wolfforge & other apps that follow the theme
        (paths.GEN_DIR / "palette.json").write_text(palette_json(ctx))

    # One font everywhere
    if s["theme"]["font_everywhere"]:
        w.owned(C / "fontconfig/conf.d/90-swayforge.conf", fontconfig(ctx))

    # GTK (your gtk.css imports the generated colours)
    w.owned(C / "gtk-3.0/settings.ini", gtk_settings(ctx, gtk4=False))
    w.owned(C / "gtk-4.0/settings.ini", gtk_settings(ctx, gtk4=True))
    gtkcss = tpl("gtk.css.j2", d)
    for v in ("gtk-3.0", "gtk-4.0"):
        w.owned(C / v / "swayforge.css", gtkcss)
        w.stub(C / v / "gtk.css", '@import url("swayforge.css");\n\n/* Your own GTK rules below. */\n',
               "swayforge.css")

    # Discord (Vesktop / Vencord / BetterDiscord) – only where such a client has been started once
    discord_css = tpl("discord.theme.css.j2", d)
    for folder, _client in discord_theme_dirs():
        w.owned(folder / "swayforge.theme.css", discord_css)

    # btop, MangoHud, cava
    w.owned(C / "btop/themes/swayforge.theme", tpl("btop.j2", d))
    btop_conf = C / "btop/btop.conf"
    if btop_conf.exists():
        txt = btop_conf.read_text()
        if 'color_theme = "swayforge"' not in txt:
            lines = [l for l in txt.splitlines() if not l.startswith("color_theme")]
            if not dry:
                btop_conf.write_text("\n".join(lines + ['color_theme = "swayforge"']) + "\n")
    elif not dry:
        btop_conf.parent.mkdir(parents=True, exist_ok=True)
        btop_conf.write_text('color_theme = "swayforge"\ntheme_background = False\nvim_keys = True\n'
                             'rounded_corners = False\n')
    w.owned(C / "MangoHud/MangoHud.conf", mangohud(ctx))
    w.owned(C / "cava/config", cava(ctx))

    # Boot screen + login (only prepared here; applying needs sudo → `swayforge boot apply`)
    boot.prepare(ctx, w)
    cs2_theme(ctx, dry)

    w.save_manifest()
    if w.res.detached:
        w.res.notes.append(f"{len(w.res.detached)} file(s) taken over by you – swayforge leaves them alone")
    if not dry:
        prune_backups()
    return w.res


# ── Live reload ──────────────────────────────────────────────────────
def reload(s: dict | None = None) -> list[str]:
    s = s or settings.load()
    done = []
    if os.environ.get("SWAYSOCK") and have("swaymsg"):
        r = run(["swaymsg", "reload"])          # also restarts Waybar & session (exec_always)
        done.append("Sway" if r.returncode == 0 else f"Sway error: {r.stdout.strip()}")
    if have("makoctl"):
        run(["makoctl", "reload"])
    run(["pkill", "-USR1", "-x", "kitty"])      # kitty reloads its config (Alacritty does it itself)
    if have("fc-cache"):
        subprocess.Popen(["fc-cache"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    session(s)
    return done


def apply_sounds(s: dict, ctx: Ctx) -> None:
    """Generate the sound pack and select it as the desktop's sound theme."""
    from . import sounds
    if not s["sound"]["enabled"]:
        return
    sounds.install(sounds.pack_for(s, ctx.theme.id, ctx.layout.id), float(s["sound"]["volume"]))
    if have("gsettings"):
        run(["gsettings", "set", "org.gnome.desktop.sound", "theme-name", "swayforge"])
        run(["gsettings", "set", "org.gnome.desktop.sound", "event-sounds", "true"])


_HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
_RGBA = re.compile(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)")


def fade_css(css: str, ui: float, skip: tuple[str, ...] = ("tooltip",)) -> str:
    """Make every background in a stylesheet `ui` times as opaque (text and borders stay)."""
    if ui >= 1.0:
        return css
    def fade(line: str) -> str:
        line = _RGBA.sub(lambda m: f"rgba({m[1]}, {m[2]}, {m[3]}, {round(float(m[4]) * ui, 2)})", line)
        return _HEX.sub(lambda m: rgba("#" + m[1], round(ui, 2)), line)
    out, sel, skipping = [], "", False
    for line in css.split("\n"):
        if line.rstrip().endswith("{"):
            sel = line.strip()
            skipping = sel.startswith(skip)
        elif "{" in line and "}" in line and not skipping:
            head, _, body = line.partition("{")
            if re.search(r"background", body) and not head.strip().startswith(skip):
                body = re.sub(r"(background[\w-]*\s*:[^;]*;)", lambda m: fade(m[1]), body)
                line = head + "{" + body
        elif re.match(r"\s*background[\w-]*\s*:", line) and not skipping:
            line = fade(line)
        if line.strip() == "}":
            skipping = False
        out.append(line)
    return "\n".join(out)


def fix_screenshare() -> None:
    """Screen share fixes that need no root: Flatpak clients get PipeWire access (Vesktop, Discord),
    and the portals are restarted once so they pick up the Sway routing."""
    stamp = paths.CONFIG_DIR / ".portal-restarted"
    if not stamp.exists() and have("systemctl"):
        run(["systemctl", "--user", "restart", "xdg-desktop-portal-wlr", "xdg-desktop-portal"])
        try:
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text("1")
        except OSError:
            pass
    if not have("flatpak"):
        return
    r = run(["flatpak", "list", "--app", "--columns=application"])
    for app in ("dev.vencord.Vesktop", "com.discordapp.Discord"):
        if app in r.stdout.split():
            run(["flatpak", "override", "--user", "--filesystem=xdg-run/pipewire-0",
                 "--socket=wayland", app])


def session(s: dict | None = None) -> None:
    """Runs at Sway start and after every change."""
    s = s or settings.load()
    # SwayFX installed/removed since the last render? Then adapt the config.
    conf = paths.XDG_CONFIG / "sway/config"
    if conf.exists() and has_mark(txt := conf.read_text()) and (("SwayFX effects" in txt) != detect().swayfx):
        render_all(s)
        if os.environ.get("SWAYSOCK"):
            run(["swaymsg", "reload"])
            return                     # reload calls session again
    ctx = make_ctx(s)
    if have("gsettings"):
        iface = "org.gnome.desktop.interface"
        font = f"{ui_font(ctx)} {s['theme']['font_size']}"
        for k, v in {
            "gtk-theme": gtk_theme(ctx), "icon-theme": icon_theme(ctx),
            "cursor-theme": s["theme"]["cursor_theme"], "cursor-size": str(s["theme"]["cursor_size"]),
            "font-name": font, "document-font-name": font,
            "monospace-font-name": f"{s['theme']['font']} {s['theme']['font_size']}",
            "color-scheme": "prefer-dark" if ctx.theme.dark else "prefer-light",
        }.items():
            run(["gsettings", "set", iface, k, v])
        run(["gsettings", "set", "org.gnome.desktop.wm.preferences", "button-layout", button_layout(ctx)])
    restart_idle(s)
    fix_screenshare()
    set_primary_output(s)
    apply_sounds(s, ctx)


def set_primary_output(s: dict) -> None:
    """XWayland only knows one 'primary' monitor – games open there. Point it at the main screen."""
    want = s["display"].get("primary")
    if not want or not have("xrandr") or not os.environ.get("SWAYSOCK"):
        return
    r = run(["swaymsg", "-t", "get_outputs", "-r"])
    try:
        outs = json.loads(r.stdout or "[]")
    except ValueError:
        return
    for o in outs:
        ident = " ".join(x for x in (o.get("make"), o.get("model"), o.get("serial")) if x and x != "Unknown")
        if want in (ident, o.get("name")):
            run(["xrandr", "--output", o["name"], "--primary"])
            return


def idle_args(s: dict) -> list[str]:
    p = s["power"]
    args = ["-w"]
    if p["lock_after"] > 0 and p.get("screensaver", "off") != "off":
        # the saver stands in for the lock: it starts at "lock after", the first input locks and closes it
        args += ["timeout", str(p["lock_after"] * 60), f"{LAUNCHER} screensaver start",
                 "resume", f"{LAUNCHER} screensaver wake"]
    elif p["lock_after"] > 0:
        args += ["timeout", str(p["lock_after"] * 60), "swaylock -f"]
    if p["screen_off_after"] > 0:
        args += ["timeout", str(p["screen_off_after"] * 60), 'swaymsg "output * power off"',
                 "resume", 'swaymsg "output * power on"']
    if p["suspend_after"] > 0:
        args += ["timeout", str(p["suspend_after"] * 60), "systemctl suspend"]
    if p["lock_before_sleep"]:
        args += ["before-sleep", "swaylock -f"]
    return args


def restart_idle(s: dict) -> None:
    if not (os.environ.get("SWAYSOCK") and have("swayidle")):
        return
    if (paths.GEN_DIR / "gamemode").exists():
        return                              # no locking in gaming mode
    run(["pkill", "-x", "swayidle"])
    subprocess.Popen(["swayidle", *idle_args(s)], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def apply(s: dict | None = None, live: bool = True) -> Result:
    s = s or settings.load()
    res = render_all(s)
    if live and not res.errors:
        res.notes += [f"reloaded: {x}" for x in reload(s)]
        follow_browser(res)
        sync_scan_timer(s, res)
    return res


def sync_scan_timer(s: dict, res: Result) -> None:
    """Weekly malware scan on/off (systemd user timer) – follows Settings → Security."""
    from . import security
    sec = s.get("security", {})
    want = bool(sec.get("weekly_scan")) and security.have("clamscan")
    timer = security.UNIT_DIR / "swayforge-scan.timer"
    svc = security.UNIT_DIR / "swayforge-scan.service"
    target = sec.get("weekly_target", "downloads")
    current = svc.read_text() if svc.exists() else ""
    if want and (not timer.exists() or f"scan {target} " not in current):
        security.set_weekly(True, LAUNCHER, target)
        res.notes.append(f"weekly malware scan on ({target})")
    elif not want and timer.exists():
        security.set_weekly(False, LAUNCHER)
        res.notes.append("weekly malware scan off")


def follow_browser(res: Result) -> None:
    """LibreWolf follows the theme too when wolfforge is installed (applies at its next start)."""
    exe = shutil.which("wolfforge") or str(paths.HOME / ".local/bin/wolfforge")
    if Path(exe).exists() and (paths.XDG_CONFIG / "wolfforge").is_dir():
        subprocess.Popen([exe, "apply", "--quiet"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res.notes.append("LibreWolf theme updated (wolfforge)")
