"""Renders README screenshots in a headless Sway with a throw-away HOME (your desktop is untouched).

    python3 scripts/make_screenshots.py requiem:cathedral:760x380:"60 640" catppuccin-mocha:win11 ...

Output: docs/img/<theme>_<layout>.png (1920x1080). Needs sway, waybar, kitty, grim, swaybg.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/img"

STAGE = r"""#!/bin/sh
# staged terminal content: art, fake system info, colour blocks
python3 - <<'PY'
import sys
sys.path.insert(0, "{root}")
from swayforge import ascii as asc, settings, themes
s = settings.load()
t = themes.get(s["theme"]["name"])
c = t.colors
def fg(h): h = h.lstrip("#"); return "\033[38;2;%d;%d;%dm" % tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
art = asc.art(t.style.get("ascii", "forge"))
info = ["you@forge", "─" * 18, "os      Fedora Linux 44 (Sway)", "wm      Sway", "term    kitty", "shell   zsh 5.9",
        "cpu     AMD Ryzen 7 7800X3D", "gpu     AMD Radeon RX 7800 XT", "ram     6.2 GiB / 31.2 GiB"]
for i in range(max(len(art), len(info))):
    a = art[i] if i < len(art) else ""
    print(fg(c["accent"]) + a.ljust(max(len(x) for x in art) + 4)[:70] + fg(c["text"]) + (info[i] if i < len(info) else ""))
print()
print("".join("\033[48;2;%d;%d;%dm   " % tuple(int(c[k].lstrip('#')[j:j+2], 16) for j in (0, 2, 4)) for k in
      ("surface", "red", "green", "yellow", "blue", "magenta", "cyan", "text")) + "\033[0m")
print()
print(fg(c["subtext"]) + "~/swayforge on main via v3.14")
print(fg(c["accent"]) + "❯ " + fg(c["text"]) + "swayforge theme --next")
PY
exec sleep 600
"""


def shot(theme: str, layout: str, size: str = "1250x860", pos: str = "center") -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="swayforge-shot-"))
    env = dict(os.environ, HOME=str(tmp), XDG_CONFIG_HOME=str(tmp / ".config"),
               XDG_DATA_HOME=str(tmp / ".local/share"), XDG_STATE_HOME=str(tmp / ".local/state"),
               XDG_CACHE_HOME=str(tmp / ".cache"), PYTHONPATH=str(ROOT))
    env.pop("SWAYSOCK", None)
    env.pop("WAYLAND_DISPLAY", None)
    for sub in (".local/share/fonts", ".local/share/icons", ".icons"):     # fonts/icons live in the real HOME
        src = Path.home() / sub
        if src.exists():
            (tmp / sub).parent.mkdir(parents=True, exist_ok=True)
            (tmp / sub).symlink_to(src)
    runtime = tmp / "run"
    runtime.mkdir(mode=0o700)
    env["XDG_RUNTIME_DIR"] = str(runtime)
    code = (f"from swayforge import settings, render\n"
            f"s = settings.load(); s['theme']['name'] = {theme!r}; s['bar']['layout'] = {layout!r}\n"
            f"s['theme']['wallpaper'] = 'theme'; settings.save(s)\n"
            f"r = render.render_all(s); print(r.errors)\n"
            f"from swayforge import paths; print(paths.WALLPAPER_DIR / 'swayforge-{theme}.png')\n")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=ROOT)
    wall = out.stdout.strip().splitlines()[-1]
    if not wall.endswith(".png") or not Path(wall).exists():
        sys.exit(f"render failed: {out.stdout}{out.stderr}")
    stage = tmp / "stage.sh"
    stage.write_text(STAGE.replace("{root}", str(ROOT)))
    conf = tmp / "sway.conf"
    conf.write_text(f"""output HEADLESS-1 resolution 1920x1080 position 0 0
output * bg {wall} fill
default_border pixel 2
gaps inner 8
gaps outer 8
font pango:DejaVu Sans Mono 11
for_window [app_id=kitty] floating enable, resize set {size.replace('x', ' ')}, move position {pos}
exec waybar
exec kitty --config {tmp}/.config/kitty/kitty.conf -e sh {stage}
""")
    env |= {"WLR_BACKENDS": "headless", "WLR_LIBINPUT_NO_DEVICES": "1", "WLR_RENDERER": "pixman"}
    chk = subprocess.run(["sway", "-C", "-c", str(conf)], env=env, capture_output=True, text=True)
    if chk.returncode:
        print(chk.stdout + chk.stderr)
    sway = subprocess.Popen(["sway", "-c", str(conf)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            time.sleep(0.2)
            socks = list(runtime.glob("wayland-*")) + list(runtime.glob("sway-ipc*"))
            if any(p.name.startswith("wayland-") and not p.name.endswith(".lock") for p in socks):
                break
        env["WAYLAND_DISPLAY"] = next(p.name for p in runtime.glob("wayland-*") if not p.name.endswith(".lock"))
        time.sleep(5)
        png = OUT / f"{theme}_{layout}.png"
        subprocess.run(["grim", str(png)], env=env, check=True)
        return png
    finally:
        sway.terminate()
        try:
            sway.wait(5)
        except subprocess.TimeoutExpired:
            sway.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        th, lay, *extra = arg.split(":")      # theme:layout[:WxH[:x y]] – small window shows the wallpaper
        print(shot(th, lay, *(extra or [])))
