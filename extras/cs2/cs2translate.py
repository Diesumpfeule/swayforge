#!/usr/bin/env python3
"""
cs2translate – live Counter-Strike 2 chat translation for Linux and Windows
-----------------------------------------------------------------------------
Reads console.log, which CS2 writes itself when started with the launch option
-condebug, and translates chat messages live (into German by default, --lang changes it).

The tool does NOT touch the game process, its memory or game files – it only
reads a text file the game writes itself.

Translation via Google (gtx endpoint), falls back to MyMemory when blocked.
No extra packages needed besides Tkinter for the overlay.

Setup (Linux):
  1. sudo dnf install python3-tkinter
  2. Steam -> CS2 -> Properties -> Launch options:  -condebug
  3. Run:  python3 cs2translate.py
Setup (Windows 11): download cs2translate.exe from the GitHub releases, set -condebug,
  double-click it once – it then starts and stops with CS2 by itself.

Debug mode (shows EVERY new log line, not just chat):
     python3 cs2translate.py --debug --terminal
"""
import argparse
import glob
import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

WINDOWS = sys.platform == "win32"
CS2_REL = "steamapps/common/Counter-Strike Global Offensive/game/csgo/console.log"
STEAM_ROOTS = [
    "~/.local/share/Steam",
    "~/.steam/steam",
    "~/.steam/root",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak Steam
    "~/snap/steam/common/.local/share/Steam",
]

# Examples: "[ALL] Name: hi"   "[CT] Name﹫CT Start: rotate"
CHAT_RE = re.compile(r"\[(ALL|CT|T|TEAM)\]\s*(.+?)(?:\s*[@﹫＠][^:]*)?:\s+(.+)$")
INVISIBLE = dict.fromkeys(map(ord, "\u200e\u200f\u200b\ufeff"), None)

# Start logo (r"..." keeps the backslashes)
LOGO = r"""
 :+@@@@@: =@@@@@- @@*@@*.
.@@=      @@-.    :   @@=
-%%       -*%%%%-   :*%+
.##=      :   =## :*#+.
 :+*****: ******= ******=
@@@@@@@@- @@@@@@+     @@@=   @@@:  @@ =@@@@@- @@=        @@@=   @@@@@@@@- @@@@@@-
   @@-    @@= -@@    +@+@@:  @@@@: @@ @@-.    @@=       +@+@@:     @@-    @@=...
   %%-    %%%*%%-   -%% -%%  %%-*%:%% -*%%%%- %%=      -%% -%%     %%-    %%%%%%:
   ##-    ##=:+##   #######= ##- *### :   =## ##=      #######=    ##-    ##=
   **-    **=  +** +**   :** **-  *** ******= ******+ +**   :**    **-    ******+
        translate  →  {lang}
"""
LOGO_SECONDS = 4

if WINDOWS:
    CONFIG = Path(os.environ.get("APPDATA") or os.path.expanduser("~")) / "cs2translate" / "config.json"
else:
    CONFIG = Path(os.path.expanduser("~/.config/cs2translate.json"))
OLD_CONFIG = Path(os.path.expanduser("~/.config/cs2_chat_uebersetzer.json"))   # earlier versions


def windows_steam_roots():
    """Steam's folder from the registry, plus the usual install places."""
    roots = []
    try:
        import winreg
        for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                               (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                               (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(winreg.QueryValueEx(k, val)[0].replace("/", "\\"))
            except OSError:
                pass
    except ImportError:
        pass
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    roots += [os.path.join(pf86, "Steam"), os.path.join(pf, "Steam")]
    return roots


def candidate_logs():
    """Every possible console.log path, including extra Steam libraries."""
    libs = []
    for root in (windows_steam_roots() if WINDOWS else STEAM_ROOTS):
        r = Path(os.path.expanduser(root))
        if not r.exists():
            continue
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
                    libs.append(Path(p.replace("\\\\", "\\")))
            except OSError:
                pass
    if WINDOWS:                       # libraries on other drives: D:\SteamLibrary …
        import string
        for letter in string.ascii_uppercase[2:]:
            drive = Path(f"{letter}:\\")
            try:
                ok = drive.exists()
            except OSError:
                ok = False
            if ok:
                for name in ("SteamLibrary", "Steam", "Games\\Steam", "Program Files (x86)\\Steam"):
                    libs.append(drive / name)
    else:
        for pattern in ("/run/media/*/*", "/mnt/*", "/media/*/*"):
            for d in glob.glob(pattern):
                for name in ("SteamLibrary", "steam", "Steam", ""):
                    libs.append(Path(d) / name)
    seen, out = set(), []
    for lib in libs:
        p = lib / CS2_REL
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def find_log():
    cands = candidate_logs()
    existing = [p for p in cands if p.exists()]
    if existing:
        return max(existing, key=lambda p: p.stat().st_mtime)  # the most recently written one
    for p in cands:
        if p.parent.exists():
            return p
    return None


def parse_chat(line):
    m = CHAT_RE.search(line.translate(INVISIBLE))
    if not m:
        return None
    channel, name, msg = m.groups()
    return channel, name.strip(), msg.strip()


def follow(path: Path, history, status):
    """Like 'tail -f'. Copes with the game restarting (file recreated)."""
    while not path.exists():
        status("Waiting for console.log … (is -condebug set and CS2 running?)")
        time.sleep(1)
    with open(path, encoding="utf-8", errors="replace") as f:
        old = [l.rstrip("\r\n") for l in f]
    for l in [l for l in old if parse_chat(l)][-history:] if history > 0 else []:
        yield ("old", l)
    f = open(path, encoding="utf-8", errors="replace")
    f.seek(0, os.SEEK_END)
    inode = os.fstat(f.fileno()).st_ino
    buf, count = "", 0
    status("Connected. Reading new lines … (0 so far)")
    while True:
        chunk = f.readline()
        if chunk:
            buf += chunk
            if buf.endswith("\n"):
                count += 1
                if count % 20 == 1:
                    status(f"Connected. {count} new log lines read")
                yield ("new", buf.rstrip("\r\n"))
                buf = ""
            continue
        time.sleep(0.15)
        try:
            st = os.stat(path)
        except FileNotFoundError:
            continue
        if st.st_ino != inode or st.st_size < f.tell():
            f.close()
            f = open(path, encoding="utf-8", errors="replace")
            inode = os.fstat(f.fileno()).st_ino
            buf = ""
            status("Log was recreated (game restarted), reading on …")


class Translator:
    """Several free services, automatic switch when one blocks or fails.
    Only needs the Python standard library."""

    UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cs2translate"}

    def __init__(self, target, status):
        self.target = target
        self.status = status
        self.backends = [("Google", self._google), ("MyMemory", self._mymemory)]
        self.blocked_until = {}

    def _get_json(self, url):
        import urllib.request
        req = urllib.request.Request(url, headers=self.UA)
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode("utf-8"))

    def _google(self, text):
        from urllib.parse import quote
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&dt=t"
               f"&sl=auto&tl={self.target}&q={quote(text)}")
        data = self._get_json(url)
        return "".join(seg[0] for seg in data[0] if seg and seg[0])

    def _mymemory(self, text):
        from urllib.parse import quote
        url = (f"https://api.mymemory.translated.net/get?q={quote(text)}"
               f"&langpair=Autodetect|{self.target}")
        data = self._get_json(url)
        out = (data.get("responseData") or {}).get("translatedText") or ""
        if "DISTINCT LANGUAGES" in out.upper():  # already in the target language
            return text
        if data.get("responseStatus") not in (200, "200") or "MYMEMORY WARNING" in out.upper():
            raise RuntimeError(out or "MyMemory error")
        return out

    def translate(self, text):
        last_err = None
        for name, fn in self.backends:
            if time.time() < self.blocked_until.get(name, 0):
                continue
            try:
                result = fn(text)
                if result:
                    return result
            except Exception as e:
                last_err = f"{name}: {getattr(e, 'code', '') or e.__class__.__name__}"
                self.blocked_until[name] = time.time() + 60  # pause this service for a minute
                self.status(f"{name} unavailable right now ({last_err}), using another service")
        raise RuntimeError(last_err or "no service available")


def worker(log_path, target, out_q, history, show_all):
    def status(text):
        print(f"[status] {text}", flush=True)
        out_q.put(("status", text))

    tr = Translator(target, status)
    cache = {}
    for kind, line in follow(log_path, history, status):
        parsed = parse_chat(line)
        if not parsed:
            if show_all and kind == "new":
                print(f"  log | {line}", flush=True)
                out_q.put(("raw", line))
            continue
        channel, name, msg = parsed
        if msg not in cache:
            try:
                cache[msg] = tr.translate(msg) or msg
            except Exception as e:
                # not cached, so it's retried next time
                translated = f"{msg}  (translation failed: {e})"
                print(f"[{channel}] {name}: {translated}", flush=True)
                out_q.put(("chat", (channel, name, msg, translated, True)))
                continue
        translated = cache[msg]
        same = translated.strip().lower() == msg.lower()
        print(f"[{channel}] {name}: {translated}" + ("" if same else f"   ({msg})"), flush=True)
        out_q.put(("chat", (channel, name, msg, translated, same)))


def run_window(out_q, alpha, log_path):
    import tkinter as tk

    root = tk.Tk()
    root.title("CS2 Chat translation")
    root.geometry("560x300+40+40")
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", alpha)
    except tk.TclError:
        pass
    status_var = tk.StringVar(value=f"Log: {log_path}")
    ui, mono = ("Segoe UI", "Consolas") if WINDOWS else ("DejaVu Sans", "DejaVu Sans Mono")
    tk.Label(root, textvariable=status_var, bg="#222", fg="#aaa", anchor="w",
             font=(ui, 8), padx=6).pack(fill="x", side="bottom")
    text = tk.Text(root, bg="#111", fg="#ddd", font=(ui, 11),
                   wrap="word", bd=0, padx=8, pady=6)
    text.pack(fill="both", expand=True)
    text.tag_config("ct", foreground="#5aa9ff")
    text.tag_config("t", foreground="#f0b44a")
    text.tag_config("all", foreground="#9be37a")
    text.tag_config("orig", foreground="#777", font=(ui, 9))
    text.tag_config("raw", foreground="#555", font=(mono, 8))
    text.insert("end", f"Reading: {log_path}\n", "orig")
    text.config(state="disabled")

    def poll():
        while not out_q.empty():
            kind, data = out_q.get()
            if kind == "status":
                status_var.set(data)
                continue
            text.config(state="normal")
            if kind == "raw":
                text.insert("end", data + "\n", "raw")
            else:
                channel, name, msg, tr, same = data
                tag = {"CT": "ct", "T": "t"}.get(channel, "all")
                text.insert("end", f"[{channel}] {name}: ", tag)
                text.insert("end", tr + "\n")
                if not same:
                    text.insert("end", f"    {msg}\n", "orig")
            if int(text.index("end-1c").split(".")[0]) > 500:
                text.delete("1.0", "100.0")
            text.see("end")
            text.config(state="disabled")
        root.after(150, poll)

    poll()
    root.mainloop()


def load_cfg():
    for f in (CONFIG, OLD_CONFIG):
        try:
            return json.loads(f.read_text())
        except Exception:
            continue
    return {}


def save_cfg(cfg):
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, indent=2))
    except OSError as e:
        print(f"Couldn't save the position: {e}")


def make_click_through_windows(win):
    """Windows: layered + transparent extended style → clicks fall through to the game; the
    overlay never takes focus and has no taskbar button."""
    import ctypes
    try:
        user32 = ctypes.windll.user32
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x00080000, 0x00000020
        WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x00000080, 0x08000000, 0x00000008
        get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        put = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get.restype = ctypes.c_ssize_t
        put.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        style = get(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        put(ctypes.c_void_p(hwnd), GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        return True
    except Exception as e:
        print(f"Click-through not possible ({e}). The overlay works anyway.")
        return False


def make_click_through(win):
    """Mouse clicks go through the overlay into the game (X11/XWayland, via libXext)."""
    if WINDOWS:
        return make_click_through_windows(win)
    import ctypes
    import ctypes.util
    try:
        x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
        xext = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xext") or "libXext.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        xext.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return False
        win.update_idletasks()
        ids = {win.winfo_id()}
        try:
            ids.add(int(win.wm_frame(), 16))
        except Exception:
            pass
        for wid in ids:
            # ShapeInput=2, ShapeSet=0, empty rectangle list = no clickable area
            xext.XShapeCombineRectangles(dpy, wid, 2, 0, 0, None, 0, 0, 0)
        x11.XFlush(dpy)
        win._x11_dpy = dpy  # keep it open
        return True
    except Exception as e:
        print(f"Click-through not possible ({e}). The overlay works anyway.")
        return False


def _hex_rgba(c, a):
    c = c.lstrip("#")
    return f"rgba({int(c[0:2], 16)}, {int(c[2:4], 16)}, {int(c[4:6], 16)}, {a:.2f})"


def layer_shell_available():
    """Wayland (Sway, Hyprland, KDE …) + gtk-layer-shell: a real overlay – see-through background,
    sits above fullscreen games, clicks go through."""
    if WINDOWS or not os.environ.get("WAYLAND_DISPLAY") or os.environ.get("CS2T_BACKEND") == "tk":
        return False
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell  # noqa: F401
        import cairo  # noqa: F401  (empty input region = click-through)
        return True
    except (ImportError, ValueError):
        return False


def run_overlay_layershell(out_q, args):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    import cairo
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell
    from html import escape

    cfg = load_cfg()
    th = cfg.get("theme") or {}
    BG, TEXT, ORIG = th.get("bg", "#0b0b0b"), th.get("text", "#ffffff"), th.get("orig", "#8a8a8a")
    FONT, MONO = th.get("font", "DejaVu Sans"), th.get("mono", "DejaVu Sans Mono")
    colors = {"CT": th.get("ct", "#6fb6ff"), "T": th.get("t", "#f2b84b")}
    ALL = th.get("all", "#9be37a")

    mon = Gdk.Display.get_default().get_monitor(0)
    sw = mon.get_geometry().width if mon else 1920
    sh = mon.get_geometry().height if mon else 1080
    height = int(sh * 0.22)
    pos = {"x": args.x if args.x is not None else cfg.get("x", 20),
           "y": args.y if args.y is not None else cfg.get("y", int(sh * 0.40))}
    bottom = pos["y"] + height                     # grows upwards from here, like the Tk overlay

    win = Gtk.Window(title="CS2 Chat Overlay")
    vis = win.get_screen().get_rgba_visual()
    if vis:
        win.set_visual(vis)
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, "cs2translate")
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_exclusive_zone(win, -1)
    for edge in (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.BOTTOM):
        GtkLayerShell.set_anchor(win, edge, True)
    try:
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND if args.move
                                        else GtkLayerShell.KeyboardMode.NONE)
    except AttributeError:                       # older gtk-layer-shell
        GtkLayerShell.set_keyboard_interactivity(win, bool(args.move))

    def margins(x, bot):
        # a saved position can come from another monitor layout (e.g. x=1920 from the old Tk
        # overlay) – keep the overlay on this screen instead of placing it off-screen
        if not 0 <= x <= sw - args.width - 16:
            x = 20
        return (x,
                min(max(0, sh - bot), max(0, sh - 60)))

    def place():
        left, bot = margins(pos["x"], bottom)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, left)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.BOTTOM, bot)
    place()

    css = Gtk.CssProvider()
    css.load_from_data(f"""
        window {{ background: {_hex_rgba(BG, args.alpha)}; border-radius: 6px; }}
        label {{ font-family: "{FONT}"; font-size: {args.font_size}pt; font-weight: bold; color: {TEXT}; }}
        label.orig {{ font-size: {max(args.font_size - 3, 7)}pt; font-weight: normal; color: {ORIG}; }}
        label.logo {{ font-family: "{MONO}"; font-size: 9pt; color: {th.get("logo", ALL)}; }}
        label.hint {{ background: #333; color: #fff; font-size: 9pt; font-weight: normal; padding: 4px; }}
        window.empty {{ background: transparent; }}
    """.encode())
    Gtk.StyleContext.add_provider_for_screen(win.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    box.set_size_request(args.width, -1)
    box.set_margin_start(8)
    box.set_margin_end(8)
    box.set_margin_top(4)
    box.set_margin_bottom(4)
    win.add(box)
    lines = []

    def label(markup, cls=None):
        lb = Gtk.Label()
        lb.set_markup(markup)
        lb.set_xalign(0)
        lb.set_line_wrap(True)
        lb.set_max_width_chars(max(20, args.width // 9))
        if cls:
            lb.get_style_context().add_class(cls)
        return lb

    def add_line(channel, name, text, orig=None):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        row.pack_start(label(f'<span foreground="{colors.get(channel, ALL)}">{escape(name)}:</span> '
                             f'{escape(text)}'), False, False, 0)
        if orig:
            row.pack_start(label("   " + escape(orig), "orig"), False, False, 0)
        box.pack_start(row, False, False, 0)
        row.show_all()
        lines.append((row, time.time() + args.duration))
        while len(lines) > args.lines:
            lines.pop(0)[0].destroy()

    if args.move:
        box.pack_start(label("Drag the overlay where you want it – the position is saved. Esc = done.",
                             "hint"), False, False, 0)
        drag = {}

        def press(_w, e):
            drag.update(x=e.x, y=e.y)

        def motion(_w, e):
            if drag:
                pos["x"] += int(e.x - drag["x"])
                nonlocal_bottom[0] += int(e.y - drag["y"])
                place2()

        def release(_w, _e):
            drag.clear()
            cfg.update(x=pos["x"], y=nonlocal_bottom[0] - height)
            save_cfg(cfg)
            print(f"Position saved: x={cfg['x']} y={cfg['y']}", flush=True)

        nonlocal_bottom = [bottom]

        def place2():
            left, bot = margins(pos["x"], nonlocal_bottom[0])
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, left)
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.BOTTOM, bot)

        win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                       | Gdk.EventMask.POINTER_MOTION_MASK)
        win.connect("button-press-event", press)
        win.connect("motion-notify-event", motion)
        win.connect("button-release-event", release)
        win.connect("key-press-event", lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        add_line("CT", "Example", "Hello, this is a translated message", "hallo, das ist eine Nachricht")
        add_line("T", "Player", "We go B")

    logo = label(escape(LOGO.format(lang=args.lang.upper()).strip("\n")), "logo")
    box.pack_start(logo, False, False, 0)
    state = {"logo": True, "shown": False, "hint": False}

    def logo_off():
        state["logo"] = False
        logo.destroy()
        return False
    GLib.timeout_add(LOGO_SECONDS * 1000, logo_off)

    def click_through(*_a):
        if not args.move and win.get_window():
            win.input_shape_combine_region(cairo.Region())   # empty input region = clicks go through

    win.connect("realize", click_through)
    win.connect("map", click_through)

    def poll():
        while not out_q.empty():
            kind, data = out_q.get()
            if kind == "status" and data.startswith("Waiting") and not state["hint"]:
                state["hint"] = True
                add_line("ALL", "cs2translate", "waiting for CS2 – is -condebug set in Steam's launch options?")
            elif kind == "chat":
                channel, name, msg, tr, same = data
                add_line(channel, name, tr, None if same or args.no_original else msg)
            elif kind == "raw" and args.debug:
                add_line("ALL", "log", data)
        now = time.time()
        while lines and lines[0][1] < now and not args.move:
            lines.pop(0)[0].destroy()
        # Nothing to show: the window stays mapped (re-mapping a layer surface is unreliable)
        # but becomes fully transparent and tiny – clicks go through it anyway.
        show = bool(lines or args.move or state["logo"])
        ctx = win.get_style_context()
        if show and not state["shown"]:
            ctx.remove_class("empty")
        elif not show and state["shown"]:
            ctx.add_class("empty")                        # never 0×0 – the empty box keeps a few px
        win.resize(1, 1)                                  # shrink to the messages
        state["shown"] = show
        return True

    GLib.timeout_add(200, poll)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    state["shown"] = True
    poll()
    Gtk.main()


def run_overlay(out_q, args):
    if layer_shell_available():
        try:
            return run_overlay_layershell(out_q, args)
        except Exception as e:                    # fall back to the X11 window
            print(f"Wayland overlay failed ({e}) – using the X11 window instead.", flush=True)
    import tkinter as tk

    cfg = load_cfg()
    root = tk.Tk()
    root.title("CS2 Chat Overlay")
    sh = root.winfo_screenheight()
    width = args.width
    height = int(sh * 0.22)
    x = args.x if args.x is not None else cfg.get("x", 20)
    # default: left, a bit above the CS2 chat
    y = args.y if args.y is not None else cfg.get("y", int(sh * 0.40))

    # colours/font: optional "theme" in the config (swayforge fills it with your system theme)
    th = cfg.get("theme") or {}
    BG = th.get("bg", "#0b0b0b")
    TEXT = th.get("text", "#ffffff")
    ORIG = th.get("orig", "#8a8a8a")
    FONT = th.get("font", "Segoe UI" if WINDOWS else "DejaVu Sans")
    MONO = th.get("mono", "Consolas" if WINDOWS else "DejaVu Sans Mono")
    root.overrideredirect(True)
    root.configure(bg=BG)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", args.alpha)
    except tk.TclError:
        pass

    box = tk.Frame(root, bg=BG)
    box.pack(side="bottom", fill="x", anchor="sw")
    colors = {"CT": th.get("ct", "#6fb6ff"), "T": th.get("t", "#f2b84b")}
    ALL = th.get("all", "#9be37a")
    font = (FONT, args.font_size, "bold")
    small = (FONT, max(args.font_size - 3, 7))
    lines = []  # (frame, expiry time)

    if args.move:
        hint = tk.Label(root, text="Drag the overlay where you want it.\n"
                                   "The position is saved. Then start without --move.",
                        bg="#333", fg="#fff", font=small, justify="left")
        hint.pack(side="top", fill="x")
        drag = {}

        def start(e):
            drag["dx"], drag["dy"] = e.x_root - root.winfo_x(), e.y_root - root.winfo_y()

        def move(e):
            root.geometry(f"+{e.x_root - drag['dx']}+{e.y_root - drag['dy']}")

        def stop(_e):
            cfg.update(x=root.winfo_x(), y=root.winfo_y())
            save_cfg(cfg)
            print(f"Position saved: x={cfg['x']} y={cfg['y']}", flush=True)

        # bindings on the main window apply to all child widgets too
        root.bind("<ButtonPress-1>", start)
        root.bind("<B1-Motion>", move)
        root.bind("<ButtonRelease-1>", stop)
        root.bind("<Escape>", lambda _e: root.destroy())
    else:
        root.after(300, lambda: make_click_through(root))

    def add_line(channel, name, text, orig=None):
        f = tk.Frame(box, bg=BG)
        row = tk.Frame(f, bg=BG)
        row.pack(anchor="w")
        tk.Label(row, text=f"{name}:", fg=colors.get(channel, ALL), bg=BG,
                 font=font).pack(side="left")
        tk.Label(row, text=" " + text, fg=TEXT, bg=BG, font=font, justify="left",
                 wraplength=width - 120, anchor="w").pack(side="left")
        if orig:
            tk.Label(f, text="   " + orig, fg=ORIG, bg=BG, font=small, anchor="w",
                     wraplength=width - 40, justify="left").pack(anchor="w")
        f.pack(side="top", anchor="w", fill="x", padx=8, pady=1)
        lines.append((f, time.time() + args.duration))
        while len(lines) > args.lines:
            lines.pop(0)[0].destroy()

    if args.move:
        add_line("CT", "Example", "Hello, this is a translated message", "hallo, das ist eine Nachricht")
        add_line("T", "Player", "We go B")

    # start logo: shows the translator is running, then disappears
    splash = tk.Label(box, text=LOGO.format(lang=args.lang.upper()).strip("\n"), fg=th.get("logo", ALL),
                      bg=BG, justify="left", font=(MONO, 9, "bold"))
    splash.pack(side="top", anchor="w", padx=8, pady=4)
    logo_on = [True]

    def logo_off():
        logo_on[0] = False
        splash.destroy()

    root.after(LOGO_SECONDS * 1000, logo_off)

    hint_shown = []
    shown = [True]
    bottom = y + height                       # the overlay grows upwards from here
    last_geo = [""]

    def fit():
        """Only as tall as the messages – a small box instead of a big dark rectangle where the
        desktop can't make windows see-through."""
        if args.move:
            return
        root.update_idletasks()
        h = max(box.winfo_reqheight() + 4, 24)
        geo = f"{width}x{h}+{x}+{bottom - h}"
        if geo != last_geo[0]:
            last_geo[0] = geo
            root.geometry(geo)

    def poll():
        while not out_q.empty():
            kind, data = out_q.get()
            if kind == "status" and data.startswith("Waiting") and not hint_shown:
                hint_shown.append(1)
                add_line("ALL", "cs2translate", "waiting for CS2 – is -condebug set in Steam's launch options?")
            if kind == "chat":
                channel, name, msg, tr, same = data
                add_line(channel, name, tr, None if same or args.no_original else msg)
            elif kind == "raw" and args.debug:
                add_line("ALL", "log", data)
        now = time.time()
        while lines and lines[0][1] < now and not args.move:
            lines.pop(0)[0].destroy()
        # nothing to show → hide the window completely. (Unmapping works on every desktop;
        # an alpha of 0 is ignored by compositors that don't support X11 opacity, e.g. Sway.)
        show = bool(lines or args.move or logo_on[0])
        if show != shown[0]:
            shown[0] = show
            if show:
                root.deiconify()
                root.attributes("-topmost", True)
            else:
                root.withdraw()
        if show:
            fit()
            if not WINDOWS:
                root.lift()
        root.after(200, poll)

    poll()
    root.mainloop()


# ── Starting with CS2 (watch mode), autostart, settings window ──────
OPTION_KEYS = ("lang", "font_size", "width", "lines", "duration", "no_original", "alpha")
DEFAULTS = {"lang": "de", "font_size": 12, "width": 520, "lines": 6, "duration": 15,
            "no_original": False, "alpha": 0.7}
LANGS = ["de", "en", "fr", "es", "it", "pt", "nl", "pl", "tr", "ru", "uk", "sv", "zh-CN", "ja", "ko"]
NO_WINDOW = 0x08000000                                  # CREATE_NO_WINDOW (Windows)


def self_cmd():
    """How to start this program again (frozen .exe or python + script)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = sys.executable
    if WINDOWS and exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"                 # no console window
    return [exe, os.path.abspath(__file__)]


def options():
    opts = dict(DEFAULTS)
    opts.update({k: v for k, v in (load_cfg().get("options") or {}).items() if k in OPTION_KEYS})
    return opts


def cs2_running():
    import subprocess
    try:
        if WINDOWS:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cs2.exe", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, creationflags=NO_WINDOW).stdout
            return "cs2.exe" in out.lower()
        return subprocess.run(["pgrep", "-x", "cs2"], capture_output=True).returncode == 0
    except OSError:
        return False


def single_instance(name):
    """True if this is the only watcher (Windows: named mutex, elsewhere: lock file)."""
    if WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        single_instance.handle = k32.CreateMutexW(None, False, f"Local\\{name}")
        return k32.GetLastError() != 183                # ERROR_ALREADY_EXISTS
    import fcntl
    single_instance.fh = open(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), f"{name}.lock"), "w")
    try:
        fcntl.flock(single_instance.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def watcher_running():
    if WINDOWS:
        import ctypes
        h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, "Local\\cs2translate-watch")
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    import fcntl
    try:
        with open(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "cs2translate-watch.lock"), "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except OSError:
        return True


def spawn(extra):
    import subprocess
    kw = {"creationflags": 0x00000008 | 0x00000200 | NO_WINDOW} if WINDOWS else {"start_new_session": True}
    return subprocess.Popen(self_cmd() + extra, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


def watch():
    """Background helper: overlay on while CS2 runs, off when it closes."""
    if not single_instance("cs2translate-watch"):
        print("Already watching for CS2.")
        return
    print("Watching for CS2 … (Ctrl+C to stop)", flush=True)
    child = None
    while True:
        running = cs2_running()
        if running and (child is None or child.poll() is not None):
            child = spawn(["--history", "0"])
        elif not running and child is not None:
            if child.poll() is None:
                child.terminate()
            child = None
        time.sleep(4)


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart(on=None):
    """Windows: start the watcher at login (HKCU Run key). Returns the current state."""
    if not WINDOWS:
        return False
    import winreg
    cmd = " ".join(f'"{c}"' for c in self_cmd()) + " --watch"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
        if on is True:
            winreg.SetValueEx(k, "cs2translate", 0, winreg.REG_SZ, cmd)
        elif on is False:
            try:
                winreg.DeleteValue(k, "cs2translate")
            except OSError:
                pass
        try:
            winreg.QueryValueEx(k, "cs2translate")
            return True
        except OSError:
            return False


def settings_window():
    """Small settings dialog – what a double-click on cs2translate.exe opens."""
    import tkinter as tk
    from tkinter import ttk

    cfg = load_cfg()
    opts = options()
    first = "options" not in cfg
    root = tk.Tk()
    root.title("cs2translate")
    root.resizable(False, False)
    pad = {"padx": 10, "pady": 4}
    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    ui = ("Segoe UI", 10) if WINDOWS else ("DejaVu Sans", 10)
    ttk.Label(frm, text="cs2translate", font=(ui[0], 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(frm, text="Live translation of the CS2 chat as an overlay.").grid(row=1, column=0, columnspan=2,
                                                                              sticky="w", pady=(0, 8))
    v = {"lang": tk.StringVar(value=opts["lang"]), "font_size": tk.IntVar(value=opts["font_size"]),
         "width": tk.IntVar(value=opts["width"]), "lines": tk.IntVar(value=opts["lines"]),
         "duration": tk.IntVar(value=opts["duration"]), "alpha": tk.DoubleVar(value=opts["alpha"]),
         "show_orig": tk.BooleanVar(value=not opts["no_original"])}
    rows = [("Translate into", ttk.Combobox(frm, textvariable=v["lang"], values=LANGS, width=10)),
            ("Font size", ttk.Spinbox(frm, from_=8, to=28, textvariable=v["font_size"], width=8)),
            ("Overlay width (px)", ttk.Spinbox(frm, from_=300, to=1600, increment=20, textvariable=v["width"], width=8)),
            ("Messages at once", ttk.Spinbox(frm, from_=1, to=15, textvariable=v["lines"], width=8)),
            ("Seconds visible", ttk.Spinbox(frm, from_=3, to=120, textvariable=v["duration"], width=8)),
            ("Opacity", ttk.Scale(frm, from_=0.2, to=1.0, variable=v["alpha"], length=160)),
            ("", ttk.Checkbutton(frm, text="Show the original text under the translation", variable=v["show_orig"]))]
    for i, (label, w) in enumerate(rows, start=2):
        ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", **pad)
        w.grid(row=i, column=1, sticky="w", **pad)
    r = len(rows) + 2
    auto = tk.BooleanVar(value=autostart() if not first else True)
    if WINDOWS:
        ttk.Checkbutton(frm, text="Start with Windows (overlay appears whenever CS2 runs)",
                        variable=auto).grid(row=r, column=0, columnspan=2, sticky="w", **pad)
        r += 1
    log = find_log()
    found = log is not None and log.exists()
    info = (f"✓ CS2 log found: {log}" if found else
            "! console.log not found yet – in Steam: CS2 → Properties → Launch options:  -condebug\n"
            "   and set CS2 to Fullscreen Windowed (Video settings).")
    ttk.Label(frm, text=info, wraplength=520, foreground="#2a7" if found else "#c70").grid(
        row=r, column=0, columnspan=2, sticky="w", pady=(8, 4))
    r += 1
    status = tk.StringVar(value="")
    ttk.Label(frm, textvariable=status).grid(row=r, column=0, columnspan=2, sticky="w")
    r += 1

    def save(close=False):
        try:
            new = {"lang": v["lang"].get().strip() or "de", "font_size": int(v["font_size"].get()),
                   "width": int(v["width"].get()), "lines": int(v["lines"].get()),
                   "duration": int(v["duration"].get()), "alpha": round(float(v["alpha"].get()), 2),
                   "no_original": not v["show_orig"].get()}
        except (tk.TclError, ValueError):
            status.set("Please enter numbers only.")
            return
        c = load_cfg()
        c["options"] = new
        save_cfg(c)
        if WINDOWS:
            try:
                autostart(bool(auto.get()))
            except OSError as e:
                status.set(f"Autostart couldn't be set: {e}")
        if not watcher_running():
            spawn(["--watch"])
        status.set("Saved. The overlay appears by itself while CS2 runs.")
        if close:
            root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=r, column=0, columnspan=2, sticky="e", pady=(10, 0))
    ttk.Button(btns, text="Position overlay …", command=lambda: (save(), spawn(["--move"]))).pack(side="left", padx=4)
    ttk.Button(btns, text="Test", command=lambda: spawn(["--test"])).pack(side="left", padx=4)
    ttk.Button(btns, text="Save", command=save).pack(side="left", padx=4)
    ttk.Button(btns, text="Save & close", command=lambda: save(True)).pack(side="left", padx=4)
    ttk.Label(frm, text="Proof of concept, written by Claude (Anthropic) – no warranty.",
              foreground="#888").grid(row=r + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))
    root.mainloop()


def self_test():
    """Quick check that runs anywhere (used by the Windows build on GitHub)."""
    assert parse_chat("[ALL] Ivan: привет всем") == ("ALL", "Ivan", "привет всем")
    assert parse_chat("[T] Bob﹫T Start: go mid") == ("T", "Bob", "go mid")
    assert parse_chat("Damage given to bot") is None
    print("platform:", sys.platform, "| config:", CONFIG)
    print("searching:", *[str(p) for p in candidate_logs()[:6]], sep="\n  ")
    print("defaults:", options())
    print("command to start again:", self_cmd())
    print("self-test ok")


# options of the earlier German version still work, silently
OLD_FLAGS = {"--fenster": "--window", "--verschieben": "--move", "--breite": "--width",
             "--schrift": "--font-size", "--zeilen": "--lines", "--dauer": "--duration",
             "--ohne-original": "--no-original", "--alles": "--debug", "--verlauf": "--history"}


def main():
    ap = argparse.ArgumentParser(
        description="Translate the CS2 chat live",
        epilog="Proof of concept, written by Claude (Anthropic). No warranty – use at your own risk.")
    ap.add_argument("--window", action="store_true", help="normal window instead of overlay")
    ap.add_argument("--move", action="store_true",
                    help="position the overlay with the mouse (position is saved)")
    ap.add_argument("--x", type=int, help="overlay position from the left (pixels)")
    ap.add_argument("--y", type=int, help="overlay position from the top (pixels)")
    ap.add_argument("--width", type=int, default=520, help="overlay width (default 520)")
    ap.add_argument("--font-size", dest="font_size", type=int, default=12,
                    help="font size (default 12)")
    ap.add_argument("--lines", type=int, default=6, help="max. messages shown at once (default 6)")
    ap.add_argument("--duration", type=int, default=15,
                    help="seconds until a message disappears (default 15)")
    ap.add_argument("--no-original", dest="no_original", action="store_true",
                    help="hide the original text")
    ap.add_argument("--log", help='path to console.log (in "quotes"!). Otherwise found automatically.')
    ap.add_argument("--lang", default="de", help="target language, default: de (German)")
    ap.add_argument("--terminal", action="store_true", help="no window, terminal output only")
    ap.add_argument("--debug", action="store_true", help="show every new log line")
    ap.add_argument("--history", type=int, default=5,
                    help="old chat messages shown at start (default 5)")
    ap.add_argument("--alpha", type=float, default=0.7, help="window transparency 0.2–1.0")
    ap.add_argument("--watch", action="store_true", help="stay in the background: overlay while CS2 runs")
    ap.add_argument("--settings", action="store_true", help="settings window (default on Windows)")
    ap.add_argument("--autostart", choices=["on", "off"], help="Windows: start the watcher at login")
    ap.add_argument("--test", action="store_true", help="show the overlay with sample messages")
    ap.add_argument("--self-test", dest="self_test", action="store_true", help=argparse.SUPPRESS)
    ap.set_defaults(**{k: v for k, v in options().items()})   # your saved settings
    argv = [OLD_FLAGS.get(a, a) for a in sys.argv[1:]]
    args = ap.parse_args(argv)

    if args.self_test:
        self_test()
        return
    if args.autostart:
        print("autostart:", autostart(args.autostart == "on"))
        return
    if args.watch:
        watch()
        return
    if args.settings or (WINDOWS and not argv):
        settings_window()
        return
    if args.test:
        args.move = True

    log_path = Path(os.path.expanduser(args.log)) if args.log else find_log()
    if not log_path and args.move:                    # positioning works without the game
        log_path = Path(os.path.expanduser("~")) / "cs2-console.log-not-found"
    if not log_path:
        print("CS2 folder not found. Searched in:")
        for p in candidate_logs():
            print("  ", p)
        sys.exit('Give the path with --log "PATH".')
    print(LOGO.format(lang=args.lang.upper()), flush=True)
    print(f"Reading: {log_path}", flush=True)

    out_q = queue.Queue()
    threading.Thread(target=worker, args=(log_path, args.lang, out_q, args.history, args.debug),
                     daemon=True).start()

    if not args.terminal:
        try:
            if args.window:
                run_window(out_q, args.alpha, log_path)
            else:
                run_overlay(out_q, args)
            return
        except Exception as e:
            print(f"No window possible ({e}), terminal output only.", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
