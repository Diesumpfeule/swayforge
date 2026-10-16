#!/usr/bin/env python3
"""
cs2translate – live Counter-Strike 2 chat translation for Linux
----------------------------------------------------------------
Reads console.log, which CS2 writes itself when started with the launch option
-condebug, and translates chat messages live (into German by default, --lang changes it).

The tool does NOT touch the game process, its memory or game files – it only
reads a text file the game writes itself.

Translation via Google (gtx endpoint), falls back to MyMemory when blocked.
No extra packages needed besides Tkinter for the overlay.

Setup:
  1. sudo dnf install python3-tkinter
  2. Steam -> CS2 -> Properties -> Launch options:  -condebug
  3. Run:  python3 cs2translate.py

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
INVISIBLE = dict.fromkeys(map(ord, "‎‏​﻿"), None)

# Start logo (r"..." keeps the backslashes)
LOGO = r"""
  ___ ___ ___    ___ _         _
 / __/ __|_  )  / __| |_  __ _| |_
| (__\__ \/ /  | (__| ' \/ _` |  _|
 \___|___/___|  \___|_||_\__,_|\__|
        translate  →  {lang}
"""
LOGO_SECONDS = 4

CONFIG = Path(os.path.expanduser("~/.config/cs2translate.json"))
OLD_CONFIG = Path(os.path.expanduser("~/.config/cs2_chat_uebersetzer.json"))   # earlier versions


def candidate_logs():
    """Every possible console.log path, including extra Steam libraries."""
    libs = []
    for root in STEAM_ROOTS:
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
    tk.Label(root, textvariable=status_var, bg="#222", fg="#aaa", anchor="w",
             font=("DejaVu Sans", 8), padx=6).pack(fill="x", side="bottom")
    text = tk.Text(root, bg="#111", fg="#ddd", font=("DejaVu Sans", 11),
                   wrap="word", bd=0, padx=8, pady=6)
    text.pack(fill="both", expand=True)
    text.tag_config("ct", foreground="#5aa9ff")
    text.tag_config("t", foreground="#f0b44a")
    text.tag_config("all", foreground="#9be37a")
    text.tag_config("orig", foreground="#777", font=("DejaVu Sans", 9))
    text.tag_config("raw", foreground="#555", font=("DejaVu Sans Mono", 8))
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


def make_click_through(win):
    """Mouse clicks go through the overlay into the game (X11/XWayland, via libXext)."""
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


def run_overlay(out_q, args):
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
    FONT = th.get("font", "DejaVu Sans")
    MONO = th.get("mono", "DejaVu Sans Mono")
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

    def poll():
        while not out_q.empty():
            kind, data = out_q.get()
            if kind == "chat":
                channel, name, msg, tr, same = data
                add_line(channel, name, tr, None if same or args.no_original else msg)
            elif kind == "raw" and args.debug:
                add_line("ALL", "log", data)
        now = time.time()
        while lines and lines[0][1] < now and not args.move:
            lines.pop(0)[0].destroy()
        # invisible while there's nothing to show
        try:
            root.attributes("-alpha", args.alpha if (lines or args.move or logo_on[0]) else 0.0)
        except tk.TclError:
            pass
        root.lift()
        root.after(200, poll)

    poll()
    root.mainloop()


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
    args = ap.parse_args([OLD_FLAGS.get(a, a) for a in sys.argv[1:]])

    log_path = Path(os.path.expanduser(args.log)) if args.log else find_log()
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
