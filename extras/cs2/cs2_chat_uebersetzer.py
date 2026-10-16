#!/usr/bin/env python3
"""
CS2 Chat-Übersetzer für Linux
------------------------------
Liest die Datei console.log, die CS2 mit der Startoption -condebug selbst schreibt,
und übersetzt Chatnachrichten live auf Deutsch.

Das Tool greift NICHT auf den Spielprozess, den Speicher oder Spieldateien zu,
es liest nur eine Textdatei, die das Spiel selbst schreibt.

Übersetzung über Google (gtx-Schnittstelle), bei Sperre automatisch über MyMemory.
Keine Zusatzpakete nötig.

Setup:
  1. sudo dnf install python3-tkinter
  2. Steam -> CS2 -> Eigenschaften -> Startoptionen:  -condebug
  3. Im Terminal starten:  python3 cs2_chat_uebersetzer.py

Prüfmodus (zeigt JEDE neue Zeile der Log, nicht nur Chat):
     python3 cs2_chat_uebersetzer.py --alles
"""
import argparse
import glob
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
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak-Steam
    "~/snap/steam/common/.local/share/Steam",
]

# Beispiele: "[ALL] Name: hi"   "[CT] Name﹫CT Start: rotate"
CHAT_RE = re.compile(r"\[(ALL|CT|T|TEAM)\]\s*(.+?)(?:\s*[@﹫＠][^:]*)?:\s+(.+)$")
INVISIBLE = dict.fromkeys(map(ord, "‎‏​﻿"), None)

# Startlogo (r"..." damit die Backslashes erhalten bleiben)
LOGO = r"""
  ___ ___ ___    ___ _         _
 / __/ __|_  )  / __| |_  __ _| |_
| (__\__ \/ /  | (__| ' \/ _` |  _|
 \___|___/___|  \___|_||_\__,_|\__|
        Übersetzer  →  Deutsch
"""
LOGO_SEKUNDEN = 4


def candidate_logs():
    """Alle möglichen console.log-Pfade, auch aus weiteren Steam-Bibliotheken."""
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
        p = (lib / CS2_REL)
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
        return max(existing, key=lambda p: p.stat().st_mtime)  # die zuletzt beschriebene
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
    """Wie 'tail -f'. Kommt mit Neustart des Spiels (Datei neu angelegt) klar."""
    while not path.exists():
        status("Warte auf console.log … (ist -condebug gesetzt und CS2 gestartet?)")
        time.sleep(1)
    with open(path, encoding="utf-8", errors="replace") as f:
        old = [l.rstrip("\r\n") for l in f]
    for l in [l for l in old if parse_chat(l)][-history:] if history > 0 else []:
        yield ("alt", l)
    f = open(path, encoding="utf-8", errors="replace")
    f.seek(0, os.SEEK_END)
    inode = os.fstat(f.fileno()).st_ino
    buf, count = "", 0
    status(f"Verbunden. Lese neue Zeilen … (0 bisher)")
    while True:
        chunk = f.readline()
        if chunk:
            buf += chunk
            if buf.endswith("\n"):
                count += 1
                if count % 20 == 1:
                    status(f"Verbunden. {count} neue Logzeilen gelesen")
                yield ("neu", buf.rstrip("\r\n"))
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
            status("Log wurde neu angelegt (Spiel neu gestartet), lese weiter …")


class Translator:
    """Mehrere kostenlose Dienste, automatischer Wechsel bei Sperre/Fehler.
    Braucht nur die Python-Standardbibliothek."""

    UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cs2-chat-uebersetzer"}

    def __init__(self, target, status):
        self.target = target
        self.status = status
        self.backends = [("Google", self._google), ("MyMemory", self._mymemory)]
        self.blocked_until = {}

    def _get_json(self, url):
        import json
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
        if "DISTINCT LANGUAGES" in out.upper():  # war schon in der Zielsprache
            return text
        if data.get("responseStatus") not in (200, "200") or "MYMEMORY WARNING" in out.upper():
            raise RuntimeError(out or "MyMemory-Fehler")
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
                self.blocked_until[name] = time.time() + 60  # 1 Minute Pause für diesen Dienst
                self.status(f"{name} gerade nicht erreichbar ({last_err}), nutze anderen Dienst")
        raise RuntimeError(last_err or "kein Dienst verfügbar")


def worker(log_path, target, out_q, history, show_all):
    def status(text):
        print(f"[Status] {text}", flush=True)
        out_q.put(("status", text))

    tr = Translator(target, status)
    cache = {}
    for kind, line in follow(log_path, history, status):
        parsed = parse_chat(line)
        if not parsed:
            if show_all and kind == "neu":
                print(f"  log | {line}", flush=True)
                out_q.put(("raw", line))
            continue
        channel, name, msg = parsed
        if msg not in cache:
            try:
                cache[msg] = tr.translate(msg) or msg
            except Exception as e:
                # nicht cachen, damit es beim nächsten Mal erneut versucht wird
                translated = f"{msg}  (Übersetzung fehlgeschlagen: {e})"
                print(f"[{channel}] {name}: {translated}", flush=True)
                out_q.put(("chat", (channel, name, msg, translated, True)))
                continue
        translated = cache[msg]
        same = translated.strip().lower() == msg.lower()
        print(f"[{channel}] {name}: {translated}" + ("" if same else f"   ({msg})"), flush=True)
        out_q.put(("chat", (channel, name, msg, translated, same)))


def run_gui(out_q, alpha, log_path):
    import tkinter as tk

    root = tk.Tk()
    root.title("CS2 Chat → Deutsch")
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
    text.insert("end", f"Lese: {log_path}\n", "orig")
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


CONFIG = Path(os.path.expanduser("~/.config/cs2_chat_uebersetzer.json"))


def load_cfg():
    import json
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {}


def save_cfg(cfg):
    import json
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, indent=2))
    except OSError as e:
        print(f"Konnte Position nicht speichern: {e}")


def make_click_through(win):
    """Maus-Klicks gehen durch das Overlay ins Spiel (X11/XWayland, über libXext)."""
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
            # ShapeInput=2, ShapeSet=0, leere Rechteckliste = keine Klickfläche
            xext.XShapeCombineRectangles(dpy, wid, 2, 0, 0, None, 0, 0, 0)
        x11.XFlush(dpy)
        win._x11_dpy = dpy  # offen halten
        return True
    except Exception as e:
        print(f"Durchklicken nicht möglich ({e}). Overlay funktioniert trotzdem.")
        return False


def run_overlay(out_q, args):
    import tkinter as tk

    cfg = load_cfg()
    root = tk.Tk()
    root.title("CS2 Chat Overlay")
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    width = args.breite
    height = int(sh * 0.22)
    x = args.x if args.x is not None else cfg.get("x", 20)
    # Standard: links, etwas oberhalb vom CS2-Chat
    y = args.y if args.y is not None else cfg.get("y", int(sh * 0.40))

    # Farben/Schrift: optional aus "theme" in der Config (swayforge trägt dort das System-Theme ein)
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
    font = (FONT, args.schrift, "bold")
    small = (FONT, max(args.schrift - 3, 7))
    lines = []  # (frame, ablaufzeit)

    hint = None
    if args.verschieben:
        hint = tk.Label(root, text="Overlay mit der Maus an die gewünschte Stelle ziehen.\n"
                                   "Position wird gespeichert. Danach ohne --verschieben starten.",
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
            print(f"Position gespeichert: x={cfg['x']} y={cfg['y']}", flush=True)

        # Bindung am Hauptfenster gilt auch für alle Unter-Elemente
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
        lines.append((f, time.time() + args.dauer))
        while len(lines) > args.zeilen:
            lines.pop(0)[0].destroy()

    if args.verschieben:
        add_line("CT", "Beispiel", "Hallo, das ist eine übersetzte Nachricht", "hello, this is a message")
        add_line("T", "Spieler", "Wir gehen B")

    # Startlogo: zeigt, dass der Übersetzer läuft, und verschwindet dann
    splash = tk.Label(box, text=LOGO.strip("\n"), fg=th.get("logo", ALL), bg=BG, justify="left",
                      font=(MONO, 9, "bold"))
    splash.pack(side="top", anchor="w", padx=8, pady=4)
    logo_aktiv = [True]

    def logo_weg():
        logo_aktiv[0] = False
        splash.destroy()

    root.after(LOGO_SEKUNDEN * 1000, logo_weg)

    def poll():
        while not out_q.empty():
            kind, data = out_q.get()
            if kind == "chat":
                channel, name, msg, tr, same = data
                add_line(channel, name, tr, None if same or args.ohne_original else msg)
            elif kind == "raw" and args.alles:
                add_line("ALL", "log", data)
        now = time.time()
        while lines and lines[0][1] < now and not args.verschieben:
            lines.pop(0)[0].destroy()
        # Fenster unsichtbar, wenn nichts anzuzeigen ist
        try:
            root.attributes("-alpha", args.alpha if (lines or args.verschieben or logo_aktiv[0]) else 0.0)
        except tk.TclError:
            pass
        root.lift()
        root.after(200, poll)

    poll()
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description="CS2-Chat live übersetzen")
    ap.add_argument("--fenster", action="store_true", help="Normales Fenster statt Overlay")
    ap.add_argument("--verschieben", action="store_true",
                    help="Overlay mit der Maus positionieren (Position wird gespeichert)")
    ap.add_argument("--x", type=int, help="Overlay-Position links (Pixel)")
    ap.add_argument("--y", type=int, help="Overlay-Position oben (Pixel)")
    ap.add_argument("--breite", type=int, default=520, help="Overlay-Breite (Standard 520)")
    ap.add_argument("--schrift", type=int, default=12, help="Schriftgröße (Standard 12)")
    ap.add_argument("--zeilen", type=int, default=6, help="Max. sichtbare Nachrichten (Standard 6)")
    ap.add_argument("--dauer", type=int, default=15, help="Sekunden bis eine Nachricht verschwindet")
    ap.add_argument("--ohne-original", action="store_true", help="Originaltext nicht anzeigen")
    ap.add_argument("--log", help="Pfad zu console.log (in Anführungszeichen!). Sonst automatische Suche.")
    ap.add_argument("--lang", default="de", help="Zielsprache, Standard: de")
    ap.add_argument("--terminal", action="store_true", help="Kein Fenster, nur Terminal")
    ap.add_argument("--alles", action="store_true", help="Prüfmodus: jede neue Logzeile anzeigen")
    ap.add_argument("--verlauf", type=int, default=5, help="Alte Chatnachrichten beim Start (Standard 5)")
    ap.add_argument("--alpha", type=float, default=0.7, help="Fenster-Transparenz 0.2–1.0")
    args = ap.parse_args()

    log_path = Path(os.path.expanduser(args.log)) if args.log else find_log()
    if not log_path:
        print("CS2-Ordner nicht gefunden. Gesucht wurde in:")
        for p in candidate_logs():
            print("  ", p)
        sys.exit("Gib den Pfad mit --log \"PFAD\" an.")
    print(LOGO, flush=True)
    print(f"Lese: {log_path}", flush=True)

    out_q = queue.Queue()
    threading.Thread(target=worker, args=(log_path, args.lang, out_q, args.verlauf, args.alles),
                     daemon=True).start()

    if not args.terminal:
        try:
            if args.fenster:
                run_gui(out_q, args.alpha, log_path)
            else:
                run_overlay(out_q, args)
            return
        except Exception as e:
            print(f"Fenster geht nicht ({e}), nur Terminal-Ausgabe.", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
