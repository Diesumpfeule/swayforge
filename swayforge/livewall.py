"""Animated wallpapers – cheap on purpose.

* A video / GIF in your Wallpapers folder works like any picture (it plays through mpvpaper).
* "Make live wallpaper" renders a short seamless loop in your theme colours (ffmpeg, small, 12 fps).
* Why it is light: hardware video decoding, no audio, a tiny low-res loop for the generated ones,
  and a guard that PAUSES the video whenever a fullscreen window covers it, on battery
  (optional), in gaming mode and while the screen is locked/idle-blanked.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from . import paths, settings
from .system import have, run

VIDEO_EXT = set(paths.VIDEO_EXT)
SOCK = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "swayforge-livewall.sock"
GUARD_PID = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "swayforge-livewall-guard.pid"
CACHE = paths.STATE_DIR / "thumbs"

STYLES = {
    "aurora": "Aurora – slow drifting colour clouds",
    "tide": "Tide – wide waves",
}


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXT


# ── thumbnails for the preview (first frame) ─────────────────────────
def thumb(path: str, width: int = 640) -> str:
    """PNG of a video's first moments (cached) – used by the picture preview."""
    if not have("ffmpeg"):
        raise RuntimeError("ffmpeg is needed for video previews")
    st = Path(path).stat()
    key = hashlib.sha1(f"{path}{st.st_mtime_ns}{st.st_size}{'' if width == 640 else width}".encode()).hexdigest()[:16]
    out = CACHE / f"{key}.png"
    if not out.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1", "-i", path,
                 "-frames:v", "1", "-vf", f"scale={width}:-2", str(out)])
        if not out.exists():                       # clips shorter than 1 s
            r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                     "-frames:v", "1", "-vf", f"scale={width}:-2", str(out)])
        if not out.exists():
            raise RuntimeError((r.stderr or "ffmpeg failed").strip().splitlines()[-1][:80])
    return str(out)


# ── generating a loop from the theme ─────────────────────────────────
def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def encoders() -> list[tuple[str, str, list[str]]]:
    """(codec, file extension, extra args) in order of preference, only what this ffmpeg can do."""
    have_enc = run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    out = []
    if " libx264 " in have_enc:
        out.append(("libx264", ".mp4", ["-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p"]))
    if " libvpx-vp9 " in have_enc:
        out.append(("libvpx-vp9", ".webm", ["-crf", "38", "-b:v", "0", "-deadline", "good", "-cpu-used", "5",
                                              "-pix_fmt", "yuv420p"]))
    out.append(("mpeg4", ".mp4", ["-q:v", "6", "-pix_fmt", "yuv420p"]))
    return out


def expression(style: str, base: tuple, a1: tuple, a2: tuple, dur: int) -> dict[str, str]:
    """ffmpeg geq expressions; every time term is a whole number of cycles over `dur` → seamless loop.
    Kept dark and calm: the theme's own background with soft glows of its two accent colours."""
    t = f"2*PI*T/{dur}"
    if style == "tide":
        f1 = f"(0.5+0.5*sin(2*PI*(Y/H*2.5+X/W*0.6)-{t}))"
        f2 = f"(0.5+0.5*sin(2*PI*(Y/H*1.2-X/W*0.9)+2*{t}))"
    else:
        f1 = f"(0.5+0.5*sin(2*PI*X/W*1.3+{t})*cos(2*PI*Y/H*1.1-{t}))"
        f2 = f"(0.5+0.5*sin(2*PI*(X/W*0.8+Y/H*0.7)+2*{t}))"
    chans = {}
    for name, i in (("r", 0), ("g", 1), ("b", 2)):
        chans[name] = f"{base[i]}+({a1[i]}-{base[i]})*0.20*{f1}*{f1}+({a2[i]}-{base[i]})*0.14*{f2}*{f2}"
    return chans


def generate(style: str = "aurora", s: dict | None = None, dur: int = 16) -> Path:
    """Render the loop into the Wallpapers folder. Takes ~20-40 s once. Returns the file."""
    from . import render
    if not have("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed (sudo dnf install ffmpeg-free)")
    s = s or settings.load()
    ctx = render.make_ctx(s)
    c = ctx.c
    ex = expression(style, _rgb(c["mantle"]), _rgb(c["accent"]), _rgb(c["accent2"]), dur)
    vf = f"nullsrc=s=800x450:r=12:d={dur},format=gbrp,geq=" + ":".join(f"{k}='{v}'" for k, v in ex.items())
    paths.WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    last = ""
    for codec, ext, extra in encoders():
        out = paths.WALLPAPER_DIR / f"swayforge-live-{ctx.theme.id}-{style}{ext}"
        r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", vf,
                 "-an", "-c:v", codec, *extra, str(out)])
        if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
            return out
        lines = (r.stderr or "").strip().splitlines()
        last = lines[-1] if lines else "failed"
        out.unlink(missing_ok=True)
    raise RuntimeError(f"ffmpeg could not encode the loop: {last}")


# ── playing it (called from the Sway config) ─────────────────────────
def mpv_options(s: dict) -> str:
    opts = ["no-audio", "loop-file=inf", "hwdec=auto-safe", "vo=gpu", "cache=no", "framedrop=vo",
            "panscan=1.0", "no-osc", "no-osd-bar", "load-scripts=no", "ytdl=no",
            f"input-ipc-server={SOCK}"]
    fps = int(s["theme"].get("live_fps", 0) or 0)
    if fps > 0:
        opts.append(f"vf=fps={fps}")               # note: software path (no hwdec) – only if you want a lower rate
    return " ".join(opts)


def start_command(s: dict, path: str) -> str:
    """Shell command for Sway's exec_always: replaces a running player."""
    mp = shutil.which("mpvpaper") or "mpvpaper"
    return (f"pkill -x mpvpaper; sleep 0.3; "
            f"exec {mp} -f -o {shell_quote(mpv_options(s))} ALL {shell_quote(path)}")


def shell_quote(x: str) -> str:
    import shlex
    return shlex.quote(x)


def stop() -> None:
    run(["pkill", "-x", "mpvpaper"])
    guard_stop()


def _send(cmd: list) -> bool:
    try:
        with socket.socket(socket.AF_UNIX) as c:
            c.settimeout(1)
            c.connect(str(SOCK))
            c.sendall((json.dumps({"command": cmd}) + "\n").encode())
        return True
    except OSError:
        return False


# ── the guard: pause while nobody can see it ─────────────────────────
def _fullscreen_visible(tree: dict) -> bool:
    """Is there a fullscreen window on a workspace that is currently shown on some output?"""
    def walk(node: dict, visible: bool) -> bool:
        if node.get("type") == "workspace":
            visible = bool(node.get("visible") or node.get("focused"))
        if visible and node.get("fullscreen_mode", 0) and node.get("type") in ("con", "floating_con") \
                and node.get("app_id") != "swayforge-saver":
            return True
        return any(walk(ch, visible) for ch in node.get("nodes", []) + node.get("floating_nodes", []))
    return walk(tree, False)


def _on_battery() -> bool:
    for p in Path("/sys/class/power_supply").glob("A*"):
        try:
            return (p / "online").read_text().strip() == "0"
        except OSError:
            continue
    return False


def should_pause(s: dict) -> bool:
    if (paths.GEN_DIR / "gamemode").exists():
        return True
    if s["theme"].get("live_pause_battery", True) and _on_battery():
        return True
    if run(["pgrep", "-x", "swaylock"]).returncode == 0 or run(["pgrep", "-f", "--", "class swayforge-saver"]).returncode == 0:
        return True
    if s["theme"].get("live_pause_fullscreen", True):
        r = run(["swaymsg", "-t", "get_tree", "-r"])
        try:
            return _fullscreen_visible(json.loads(r.stdout))
        except ValueError:
            return False
    return False


def guard() -> int:
    """Long-running: wakes up on window/workspace events (and every 30 s for battery/lock), pauses or resumes mpv."""
    GUARD_PID.write_text(str(os.getpid()))
    paused = None
    p = subprocess.Popen(["swaymsg", "-t", "subscribe", "-m", '["window","workspace"]'],
                         stdout=subprocess.PIPE, text=True, bufsize=1)
    import select
    try:
        while True:
            s = settings.load()
            want = should_pause(s)
            if want != paused and _send(["set_property", "pause", want]):
                paused = want
            r, _, _ = select.select([p.stdout], [], [], 30)
            if r:
                if not p.stdout.readline():
                    return 0                           # sway ended
                time.sleep(0.15)                       # let a burst of events settle
                while select.select([p.stdout], [], [], 0)[0]:
                    if not p.stdout.readline():
                        return 0
    finally:
        p.kill()
        GUARD_PID.unlink(missing_ok=True)


def guard_stop() -> None:
    try:
        os.kill(int(GUARD_PID.read_text()), 15)
    except (OSError, ValueError):
        pass
