"""swayforge Studio – graphical settings next to the terminal app (`swayforge gui`)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

APP_ID = "swayforge-studio"


def _native_window(url: str) -> bool:
    """A real window via GTK 4 + WebKitGTK (Fedora: python3-gobject webkitgtk6.0). False if missing."""
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("WebKit", "6.0")
        from gi.repository import Gtk, WebKit
    except (ImportError, ValueError):
        return False

    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        return False
    Gtk.Window.set_default_icon_name("preferences-desktop-theme")
    app = Gtk.Application(application_id="org.swayforge.Studio")

    def activate(a):
        win = Gtk.ApplicationWindow(application=a, title="swayforge Studio")
        win.set_default_size(1280, 820)
        view = WebKit.WebView()
        if os.environ.get("SWAYFORGE_DEBUG"):
            view.get_settings().set_enable_developer_extras(True)
        view.load_uri(url)
        win.set_child(view)
        win.present()

    app.connect("activate", activate)
    app.run([])
    return True


def _browser_window(url: str) -> bool:
    """Fallback: a Chromium-type browser in app mode (own window, no tabs), else any browser."""
    for exe in ("chromium-browser", "chromium", "google-chrome", "brave-browser"):
        if shutil.which(exe):
            subprocess.Popen([exe, f"--app={url}", f"--class={APP_ID}", "--window-size=1280,820",
                              f"--user-data-dir={os.path.expanduser('~/.cache/swayforge/studio-browser')}"],
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    for exe in ("librewolf", "firefox"):
        if shutil.which(exe):
            subprocess.Popen([exe, "--new-window", url], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", url], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    import argparse
    from .server import IDLE_EXIT, serve
    ap = argparse.ArgumentParser(prog="swayforge gui", description="swayforge Studio – graphical settings")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--browser", action="store_true", help="open in the browser instead of a native window")
    ap.add_argument("--serve", action="store_true", help="only print the URL and keep serving (Ctrl+C ends)")
    a = ap.parse_args(argv)
    srv, url, state = serve(a.port)
    if a.serve:
        print(url, flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    if not a.browser and _native_window(url):
        srv.shutdown()
        return 0
    if not _browser_window(url):
        print("No window toolkit or browser found. Open this address yourself:\n" + url)
    print("swayforge Studio runs at", url, flush=True)
    # The page pings every few seconds; when the window is gone, stop (but never mid-apply).
    state.last_ping = time.time() + 30          # give the browser time to start
    while time.time() - state.last_ping < IDLE_EXIT or state.applying:
        time.sleep(2)
    srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
