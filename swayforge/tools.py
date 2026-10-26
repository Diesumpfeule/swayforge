"""Small helpers called from shortcuts and the bar."""
from __future__ import annotations

import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

from . import layouts, paths, render, settings, themes
from .system import have, notify, run


def rofi_menu(options: list[str], prompt: str, width: str = "360px", lines: int | None = None,
              extra: list[str] | None = None, message: str = "") -> str | None:
    if not have("rofi"):
        return None
    lines = lines or len(options)
    theme = (f"window {{ width: {width}; location: center; anchor: center; x-offset: 0; y-offset: 0; }} "
             f"listview {{ lines: {lines}; }}")
    args = ["rofi", "-dmenu", "-i", "-p", prompt, "-theme-str", theme, *(extra or [])]
    if message:
        args += ["-mesg", message]
    r = subprocess.run(args, input="\n".join(options), text=True, capture_output=True)
    return r.stdout.strip() or None


def _wired() -> bool:
    return layouts.get(settings.load()["bar"]["layout"]).id == "wired"


def power() -> None:
    I = render.I
    wired = _wired()
    opts = {
        ("[lock]" if wired else "\U000f033e  Lock"): ["swaylock", "-f"],
        ("[logout]" if wired else "\U000f0343  Log out"): ["swaymsg", "exit"],
        ("[suspend]" if wired else "\U000f04b2  Suspend"): ["systemctl", "suspend"],
        ("[reboot]" if wired else "\U000f0709  Reboot"): ["systemctl", "reboot"],
        ("[shutdown]" if wired else f"{I['power']}  Shut down"): ["systemctl", "poweroff"],
    }
    choice = rofi_menu(list(opts), "> power" if wired else "Power", width="420px")
    if not choice or choice not in opts:
        return
    if opts[choice][-1] in ("exit", "reboot", "poweroff"):
        sure = rofi_menu(["Yes", "No"], choice.strip("[] ").split("  ")[-1].lower() + "?", width="280px")
        if sure != "Yes":
            return
    subprocess.Popen(opts[choice], start_new_session=True)


def sound(action: str, event: str = "bell") -> None:
    """swayforge sound test|play EVENT|build – the generated system sounds."""
    import time
    from . import sounds
    s = settings.load()
    pack = sounds.pack_for(s, s["theme"]["name"], s["bar"]["layout"])
    sounds.install(pack, float(s["sound"]["volume"]), force=action == "build")
    if action == "build":
        print(f"sound pack '{pack}' written to {sounds.THEME_DIR}")
    elif action == "play":
        sounds.play(event)
    else:
        for ev in ("desktop-login", "message-new-instant", "dialog-warning", "dialog-error", "complete"):
            print(ev)
            sounds.play(ev)
            time.sleep(2.2)


def start() -> None:
    """Start menu for the Win98/Win7 layouts: rofi with the layout's start-menu look."""
    subprocess.Popen(["rofi", "-show", "drun"], start_new_session=True)


def keys() -> None:
    s = settings.load()
    rows = []
    for _aid, label, key, _cmd in settings.keybinds(s):
        if key.strip():
            rows.append(f"{key.replace('$mod', 'Super'):<26} {label}")
    rows += [f"{'Super+h/j/k/l or arrows':<26} Move focus",
             f"{'Super+Shift+h/j/k/l/arrows':<26} Move window",
             f"{'Super+1…0':<26} Switch workspace",
             f"{'Super+Shift+1…0':<26} Move window to workspace",
             f"{'Super+mouse drag':<26} Move (left) / resize (right) window"]
    if s["general"]["mod"] == "Mod1":
        rows = [r.replace("Super", "Alt") for r in rows]
    rofi_menu(rows, "Shortcuts", width="760px", lines=min(len(rows), 18))


def clip() -> None:
    if not (have("cliphist") and have("wl-copy")):
        return
    hist = run(["cliphist", "list"]).stdout.splitlines()
    choice = rofi_menu(hist, "Clipboard", width="760px", lines=12)
    if choice:
        dec = subprocess.run(["cliphist", "decode"], input=choice.encode(), capture_output=True)
        subprocess.run(["wl-copy"], input=dec.stdout)


def shot(mode: str) -> None:
    out_dir = Path(os.environ.get("XDG_PICTURES_DIR", paths.HOME / "Pictures")) / "Screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    f = out_dir / time.strftime("Screenshot_%Y-%m-%d_%H-%M-%S.png")
    if mode in ("area", "edit"):
        geo = run(["slurp"]).stdout.strip()
        if not geo:
            return
        args = ["grim", "-g", geo]
    else:
        focused = run(["swaymsg", "-t", "get_outputs", "-r"]).stdout
        name = next((o["name"] for o in json.loads(focused or "[]") if o.get("focused")), None)
        args = ["grim"] + (["-o", name] if name else [])
    if mode == "edit":
        grim = subprocess.run(args + ["-"], capture_output=True)
        subprocess.Popen(["swappy", "-f", "-", "-o", str(f)], stdin=subprocess.PIPE).communicate(grim.stdout)
        return
    subprocess.run(args + [str(f)])
    if f.exists():
        with open(f, "rb") as fh:
            subprocess.run(["wl-copy", "--type", "image/png"], stdin=fh)
        notify("Screenshot saved", f"{f.name} – also on the clipboard")


def theme_cmd(name: str | None, nxt: bool, list_: bool) -> int:
    all_t = themes.all_themes()
    if list_:
        cur = settings.load()["theme"]["name"]
        for tid, t in all_t.items():
            print(("* " if tid == cur else "  ") + f"{tid:<20} {t.label}")
        return 0
    s = settings.load()
    if nxt:
        ids = list(all_t)
        cur = s["theme"]["name"]
        name = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
    if not name or name not in all_t:
        print("Unknown theme. Available:", ", ".join(all_t))
        return 1
    themes.apply_style(s, all_t[name], all_t.get(s["theme"]["name"]))
    s["theme"]["name"] = name
    settings.save(s)
    res = render.apply(s)
    notify("Theme changed", all_t[name].label)
    for e in res.errors:
        print(e)
    return 1 if res.errors else 0


def theme_from_wallpaper(image: str, mode: str = "auto", save_as: str = "") -> int:
    from . import wallpalette
    img = os.path.abspath(os.path.expanduser(image))
    if not os.path.isfile(img):
        print(f"{image}: not found")
        return 1
    try:
        t = wallpalette.make_theme(img, mode, label=save_as,
                                   tid=themes.slug(save_as) if save_as else wallpalette.LIVE_ID)
    except ImportError:
        print("Needs Pillow: sudo dnf install python3-pillow")
        return 1
    s = settings.load()
    s["theme"]["wallpaper"] = img
    s["theme"]["accent"] = ""
    print(f"{t.label}: {'dark' if t.dark else 'light'} theme → ~/.config/swayforge/themes/{t.id}.toml")
    settings.save(s)
    return theme_cmd(t.id, False, False)


def layout_cmd(name: str | None, nxt: bool, list_: bool) -> int:
    s = settings.load()
    cur = layouts.get(s["bar"]["layout"]).id
    if list_:
        for l in layouts.LAYOUTS.values():
            print(("* " if l.id == cur else "  ") + f"{l.id:<10} {l.label} – {l.desc}")
        return 0
    ids = list(layouts.LAYOUTS)
    if nxt:
        name = ids[(ids.index(cur) + 1) % len(ids)]
    if name not in layouts.LAYOUTS:
        print("Unknown layout. Available:", ", ".join(ids))
        return 1
    s["bar"]["layout"] = name
    settings.save(s)
    res = render.apply(s)
    notify("Layout changed", layouts.LAYOUTS[name].label)
    return 1 if res.errors else 0


# ── Export / import (for quick resets) ───────────────────────────────
EXPORT_FILES = [
    paths.CONFIG_DIR, paths.SWAY_CUSTOM,
    paths.XDG_CONFIG / "waybar/style.css", paths.XDG_CONFIG / "kitty/kitty.conf",
    paths.XDG_CONFIG / "alacritty/alacritty.toml", paths.XDG_CONFIG / "rofi/config.rasi",
    paths.XDG_CONFIG / "waybar/config.jsonc", paths.XDG_CONFIG / "gtk-3.0/gtk.css",
    paths.XDG_CONFIG / "gtk-4.0/gtk.css", paths.HOME / ".zshrc", paths.HOME / ".spaceshiprc.zsh",
    paths.XDG_DATA / "cs2translate", paths.XDG_CONFIG / "cs2translate.json", paths.XDG_CONFIG / "steamtune.json",
    paths.XDG_CONFIG / "wolfforge",
]


def export(dest: str) -> int:
    out = Path(os.path.expanduser(dest))
    if out.is_dir():
        out = out / time.strftime("swayforge-backup-%Y%m%d.tar.gz")
    with tarfile.open(out, "w:gz") as tar:
        for p in EXPORT_FILES:
            if p.exists():
                tar.add(p, arcname=str(p.relative_to(paths.HOME)))
    print(f"Saved: {out}")
    print("After a reset:  ./install.sh --restore", out.name)
    return 0


def import_(src: str) -> int:
    f = Path(os.path.expanduser(src))
    if not f.is_file():
        print(f"File not found: {f}")
        return 1
    with tarfile.open(f) as tar:
        members = [m for m in tar.getmembers()
                   if not m.name.startswith("/") and ".." not in Path(m.name).parts
                   and (m.isfile() or m.isdir())]
        stamp = paths.BACKUP_DIR / time.strftime("%Y%m%d-%H%M%S-import")
        for m in members:
            target = paths.HOME / m.name
            if m.isfile() and target.exists():
                (stamp / m.name).parent.mkdir(parents=True, exist_ok=True)
                (stamp / m.name).write_bytes(target.read_bytes())
        tar.extractall(paths.HOME, members=members, filter="data")
    print(f"Restored from {f.name}")
    return 0


# ── Volume / brightness with on-screen display ───────────────────────
def osd(kind: str, arg: str) -> None:
    state = paths.GEN_DIR / "osd-id"
    if kind == "volume":
        if arg == "mute":
            run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        else:
            step = arg.lstrip("+-")
            run(["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@",
                 f"{step}%{'+' if arg.startswith('+') else '-'}"])
        out = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]).stdout
        try:
            val = round(float(out.split()[1]) * 100)
        except (IndexError, ValueError):
            val = 0
        muted = "MUTED" in out
        title = "Muted" if muted else f"Volume {val}%"
        icon = "audio-volume-muted" if muted else ("audio-volume-high" if val > 66 else
                                                   "audio-volume-medium" if val > 33 else "audio-volume-low")
    elif kind == "mic":
        run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"])
        out = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"]).stdout
        muted = "MUTED" in out
        val = 0 if muted else 100
        title = "Microphone off" if muted else "Microphone on"
        icon = "microphone-sensitivity-muted" if muted else "microphone-sensitivity-high"
    elif kind == "brightness":
        step = arg.lstrip("+-")
        run(["brightnessctl", "-q", "set", f"{step}%{'+' if arg.startswith('+') else '-'}"])
        try:
            cur = int(run(["brightnessctl", "get"]).stdout.strip())
            mx = int(run(["brightnessctl", "max"]).stdout.strip())
            val = round(cur * 100 / mx)
        except ValueError:
            val = 0
        title, icon = f"Brightness {val}%", "display-brightness"
    else:
        return
    if not have("notify-send"):
        return
    cmd = ["notify-send", "-a", "swayforge", "-c", "osd", "-i", icon, "-h", f"int:value:{min(val, 100)}",
           "-p", title]
    try:
        cmd[1:1] = ["-r", state.read_text().strip()]
    except OSError:
        pass
    r = run(cmd)
    if r.stdout.strip().isdigit():
        state.write_text(r.stdout.strip())


# ── Gaming mode ──────────────────────────────────────────────────────
def gamemode(action: str = "toggle", text: bool = False) -> None:
    flag = paths.GEN_DIR / "gamemode"
    on = flag.exists()
    if action == "status":
        label = ("[game on]" if on else "[game]") if text else render.I["game"]
        print(json.dumps({"text": label, "class": "on" if on else "off",
                          "tooltip": "Gaming mode ON – click to leave" if on else
                          "Gaming mode: no gaps, do not disturb, no locking, full performance"},
                         ensure_ascii=False))
        return
    if not on:
        prev = run(["powerprofilesctl", "get"]).stdout.strip() if have("powerprofilesctl") else ""
        flag.write_text(prev)
        run(["swaymsg", "gaps inner all set 0; gaps outer all set 0; [all] border none"])
        run(["makoctl", "mode", "-a", "do-not-disturb"])
        run(["pkill", "-x", "swayidle"])
        if prev:
            run(["powerprofilesctl", "set", "performance"])
        notify("Gaming mode on", "No gaps, notifications muted, no locking")
    else:
        prev = flag.read_text().strip()
        flag.unlink()
        run(["makoctl", "mode", "-r", "do-not-disturb"])
        if prev and have("powerprofilesctl"):
            run(["powerprofilesctl", "set", prev])
        run(["swaymsg", "reload"])                # restores gaps/borders + swayidle
        notify("Gaming mode off")
    run(["pkill", "-RTMIN+8", "waybar"])
