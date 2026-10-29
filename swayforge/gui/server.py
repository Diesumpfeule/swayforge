"""swayforge app – the graphical settings app.

A small local web server (standard library only) serves the interface from ./static and a JSON
API on top of the same modules the terminal app uses (settings, themes, layouts, render). It only
listens on 127.0.0.1 and every API call needs the random token from the start URL.

The classic terminal settings app is untouched: this is a second front end, not a replacement.
"""
from __future__ import annotations

import copy
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shlex
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, layouts, paths, settings, themes
from ..anim import MOTIONS

STATIC = Path(__file__).resolve().parent / "static"
THUMBS = Path(os.environ.get("XDG_CACHE_HOME") or paths.HOME / ".cache") / "swayforge/studio-thumbs"
MAX_WALLS = 4000
PAGE = 24
IDLE_EXIT = 25.0            # seconds without a heartbeat from the window → quit (browser fallback)

# Settings the Studio may change directly (path → kind). Everything else stays in the terminal app.
EDITABLE = {
    "theme.accent": "str", "theme.font_size": "int", "theme.animate": "bool", "theme.wallpaper": "str",
    "theme.live_pause_fullscreen": "bool", "theme.live_pause_battery": "bool",
    "bar.layout": "str", "bar.height": "int",
    "look.radius": "int", "look.gaps_inner": "int", "look.gaps_outer": "int", "look.border": "int",
    "look.ui_opacity": "float", "look.terminal_opacity": "float", "look.fx_blur": "bool",
    "look.fx_shadows": "bool", "look.fx_dim_inactive": "float", "look.title_bars": "bool",
    "look.smart_gaps": "bool", "look.terminal_padding": "int",
    "power.screensaver": "str", "power.lock_after": "int", "power.screen_off_after": "int",
    "power.suspend_after": "int", "power.lock_before_sleep": "bool", "power.inhibit_fullscreen": "bool",
    "sound.enabled": "bool", "sound.volume": "float",
}
# … plus every option of the shared settings forms (the same list the terminal app shows)
CHOICES: dict[str, list] = {}


def _from_fields() -> None:
    from ..fields import FIELDS
    for fs in FIELDS.values():
        for f in fs:
            if isinstance(f, str):
                continue
            kind = {"choice": "choice"}.get(f.kind, f.kind)
            EDITABLE.setdefault(f.path, kind)
            if f.kind == "choice":
                CHOICES[f.path] = [v for _, v in f.options]
    EDITABLE["theme.motion"] = "choice"
    CHOICES["theme.motion"] = list(MOTIONS)
    EDITABLE.update({"display.allow_tearing": "bool", "boot.style": "str", "boot.text": "str",
                     "theme.ascii": "str"})


_from_fields()

RANGES = {"look.ui_opacity": (0.2, 1.0), "look.terminal_opacity": (0.3, 1.0), "look.fx_dim_inactive": (0.0, 0.5),
          "look.radius": (0, 24), "look.gaps_inner": (0, 40), "look.gaps_outer": (0, 40), "look.border": (0, 8),
          "theme.font_size": (8, 20), "bar.height": (20, 60), "sound.volume": (0.0, 1.0),
          "power.lock_after": (0, 240), "power.screen_off_after": (0, 240), "power.suspend_after": (0, 480),
          "look.terminal_padding": (0, 40), "input.mouse_speed": (-1.0, 1.0), "input.repeat_rate": (1, 100),
          "input.repeat_delay": (100, 2000), "power.nightlight_temp": (1500, 6500), "prompt.dir_trunc": (0, 20)}


PAGE_IDS = {"clipboard", "privacy", "display", "audio", "bluetooth", "network", "power", "boot", "security", "apps", "cleanup",
            "mounts", "system", "about", "games"}


class State:
    """Settings being edited (staged) next to the saved ones."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.s = settings.load()
        self.saved = copy.deepcopy(self.s)
        self.applying = False
        self.last_result: dict = {}
        self.last_ping = time.time()
        self.walls: list[Path] | None = None

    @property
    def dirty(self) -> bool:
        return self.s != self.saved


def _theme_json(t: themes.Theme) -> dict:
    return {"id": t.id, "label": t.label, "dark": t.dark, "colors": t.colors, "ansi": t.ansi,
            "style": t.style, "custom": t.custom}


def _coerce(kind: str, value, path: str = ""):
    if kind == "choice":
        opts = CHOICES.get(path, [])
        for o in opts:                          # the option list decides the type
            if str(o) == str(value):
                return o
        raise ValueError("not one of the choices")
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(float(value))
    if kind == "float":
        return round(float(value), 2)
    return str(value)


def scan_walls(root: Path, limit: int = MAX_WALLS) -> list[Path]:
    out: list[Path] = []
    if not root.is_dir():
        return out
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in fn:
            if Path(f).suffix.lower() in paths.WALLPAPER_EXT:
                out.append(Path(dp) / f)
                if len(out) >= limit:
                    return sorted(out, key=lambda p: str(p).lower())
    return sorted(out, key=lambda p: str(p).lower())


def thumbnail(path: Path, width: int = 480) -> tuple[bytes, str]:
    """(bytes, mime) – cached JPEG for pictures, the first frame for videos, SVG as is."""
    if path.suffix.lower() == ".svg":
        return path.read_bytes(), "image/svg+xml"
    st = path.stat()
    key = hashlib.sha1(f"{path}{st.st_mtime_ns}{st.st_size}{width}".encode()).hexdigest()[:20]
    out = THUMBS / f"{key}.jpg"
    if not out.exists():
        THUMBS.mkdir(parents=True, exist_ok=True)
        src = path
        from .. import livewall
        if livewall.is_video(path):
            src = Path(livewall.thumb(str(path), max(640, width)))
        try:
            from PIL import Image
        except ImportError:                       # no Pillow: send the original
            return src.read_bytes(), mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        with Image.open(src) as im:
            im.thumbnail((width, width * 10 // 16))
            im.convert("RGB").save(out, "JPEG", quality=82)
    return out.read_bytes(), "image/jpeg"


def theme_wallpaper_svg(s: dict, theme_id: str) -> str:
    """The theme's own generated wallpaper as SVG (what 'Theme wallpaper' shows)."""
    from .. import render
    s2 = copy.deepcopy(s)
    s2["theme"]["name"] = theme_id
    ctx = render.make_ctx(s2)
    return render.tpl(f"wallpaper-{ctx.theme.wallpaper_style}.svg.j2", ctx.as_dict())


def make_handler(state: State, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "swayforge-app"

        def log_message(self, *a) -> None:      # quiet
            pass

        # ── helpers ────────────────────────────────────────────────
        def _send(self, code: int, body: bytes, mime: str, cache: bool = False) -> None:
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json")

        def _authorised(self, q: dict) -> bool:
            return secrets.compare_digest(self.headers.get("X-Token", "") or q.get("t", [""])[0], token)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 1_000_000:
                return {}
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                return {}
            return data if isinstance(data, dict) else {}

        # ── GET ────────────────────────────────────────────────────
        def do_GET(self) -> None:                 # noqa: N802
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self._static("index.html")
            if u.path.startswith("/static/"):
                return self._static(u.path[len("/static/"):])
            if not u.path.startswith("/api/"):
                return self._send(404, b"not found", "text/plain")
            if not self._authorised(q):
                return self._send(403, b"forbidden", "text/plain")
            try:
                self._api_get(u.path[5:], q)
            except Exception as e:              # noqa: BLE001 – report, don't crash the server
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def _static(self, rel: str) -> None:
            f = (STATIC / rel).resolve()
            if not f.is_relative_to(STATIC) or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if f.suffix == ".js":
                mime = "text/javascript"
            self._send(200, f.read_bytes(), mime + ("; charset=utf-8" if mime.startswith("text") else ""))

        def _api_get(self, name: str, q: dict) -> None:
            state.last_ping = time.time()
            if name == "state":
                from ..screensaver import SAVERS
                from ..system import detect
                si = detect()
                with state.lock:
                    s = copy.deepcopy(state.s)
                    dirty = state.dirty
                return self._json({
                    "version": __version__, "settings": s, "dirty": dirty, "editable": EDITABLE, "ranges": RANGES,
                    "themes": [_theme_json(t) for t in themes.all_themes().values()],
                    "layouts": layouts.all_layouts(),
                    "maker": {"modules": {k: v[1] for k, v in layouts.MODULES.items()}, "ws_styles": layouts.WS_STYLES,
                              "text_modes": layouts.TEXT_MODES, "default": layouts.CUSTOM_DEFAULT},
                    "accents": themes.ACCENT_CHOICES, "savers": SAVERS,
                    "swayfx": si.swayfx, "in_sway": bool(os.environ.get("SWAYSOCK")),
                    "user": os.environ.get("USER", "user"),
                    "applying": state.applying, "result": state.last_result,
                })
            if name == "fields":
                from ..fields import FIELDS
                from .. import settings as st
                return self._json({
                    "forms": {pid: [f if isinstance(f, str) else {"path": f.path, "label": f.label, "kind": f.kind,
                                                                   "options": f.options, "help": f.help} for f in fs]
                              for pid, fs in FIELDS.items()},
                    "keys": [{"id": a, "label": lab, "default": k} for a, lab, k, _c in st.KEY_ACTIONS],
                    "prompt_sections": st.PROMPT_SECTIONS,
                    "art": list(__import__("swayforge.ascii", fromlist=["all_art"]).all_art()),
                    "motions": MOTIONS,
                    "color_keys": themes.COLOR_KEYS, "color_labels": themes.COLOR_LABELS})
            if name == "page":
                from . import actions
                pid = q.get("id", [""])[0]
                fn = getattr(actions, f"page_{pid}", None)
                if pid not in PAGE_IDS or fn is None:
                    return self._json({"error": "unknown page"}, 404)
                with state.lock:
                    s = copy.deepcopy(state.s)
                kw = {"rescan": True} if pid == "network" and q.get("rescan") else {}
                return self._json(fn(s, **kw))
            if name == "wallpacks":
                from . import actions
                return self._json(actions.wallpacks_page())
            if name == "status":
                return self._json({"applying": state.applying, "result": state.last_result, "dirty": state.dirty})
            if name == "wallpapers":
                if state.walls is None or q.get("rescan"):
                    state.walls = scan_walls(paths.WALLPAPER_DIR)
                needle = (q.get("q", [""])[0]).lower()
                items = [p for p in state.walls if needle in str(p).lower()] if needle else state.walls
                page = max(0, int(q.get("page", ["0"])[0]))
                chunk = items[page * PAGE:(page + 1) * PAGE]
                from .. import livewall
                return self._json({
                    "total": len(items), "page": page, "pages": max(1, -(-len(items) // PAGE)),
                    "folder": str(paths.WALLPAPER_DIR),
                    "items": [{"path": str(p), "name": p.name, "video": livewall.is_video(p),
                               "folder": str(p.parent.relative_to(paths.WALLPAPER_DIR))
                               if p.parent != paths.WALLPAPER_DIR else ""} for p in chunk]})
            if name == "clipimg":
                from .. import clipboard
                try:
                    got = clipboard.get(int(q.get("id", ["0"])[0]))
                except ValueError:
                    got = None
                if not got or not got[0].startswith("image/"):
                    return self._send(404, b"not found", "text/plain")
                return self._send(200, got[1], got[0])
            if name == "thumb":
                p = Path(q.get("p", [""])[0])
                if state.walls is None:
                    state.walls = scan_walls(paths.WALLPAPER_DIR)
                if p not in state.walls:              # only pictures from your wallpaper folder
                    return self._send(404, b"not found", "text/plain")
                try:
                    w = max(200, min(1920, int(q.get("w", ["480"])[0])))
                except ValueError:
                    w = 480
                body, mime = thumbnail(p, w - w % 160)          # few sizes → few cache files
                return self._send(200, body, mime, cache=True)
            if name == "themewall":
                tid = q.get("id", [""])[0]
                if tid not in themes.all_themes():
                    tid = themes.get(tid).id               # merged/removed theme → what it falls back to
                with state.lock:
                    s = copy.deepcopy(state.s)
                body = theme_wallpaper_svg(s, tid).encode()
                return self._send(200, body, "image/svg+xml", cache=True)
            return self._json({"error": "unknown"}, 404)

        # ── POST ───────────────────────────────────────────────────
        def do_POST(self) -> None:                # noqa: N802
            u = urlparse(self.path)
            if not u.path.startswith("/api/") or not self._authorised({}):
                return self._send(403, b"forbidden", "text/plain")
            data = self._body()
            try:
                self._api_post(u.path[5:], data)
            except Exception as e:              # noqa: BLE001
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def _api_post(self, name: str, d: dict) -> None:
            state.last_ping = time.time()
            if name == "ping":
                return self._json({"ok": True})
            if name == "set":
                path, value = str(d.get("path", "")), d.get("value")
                kind = EDITABLE.get(path)
                if not kind:
                    return self._json({"error": f"{path} can't be changed here"}, 400)
                try:
                    val = _coerce(kind, value, path)
                except (TypeError, ValueError):
                    return self._json({"error": f"“{value}” doesn't fit here"}, 400)
                if kind == "str" and (len(str(val)) > 200 or "\n" in str(val)):
                    return self._json({"error": "too long"}, 400)
                if path in RANGES:
                    lo, hi = RANGES[path]
                    val = type(val)(min(hi, max(lo, val))) if isinstance(val, (int, float)) and not isinstance(val, bool) else val
                if path == "bar.layout" and not layouts.exists(val):
                    return self._json({"error": "unknown layout"}, 400)
                if path == "power.screensaver":
                    from ..screensaver import SAVERS
                    if val not in SAVERS:
                        return self._json({"error": "unknown screensaver"}, 400)
                if path == "theme.wallpaper" and val not in ("theme", "solid"):
                    if state.walls is None:
                        state.walls = scan_walls(paths.WALLPAPER_DIR)
                    if Path(val) not in state.walls:
                        return self._json({"error": "not in your wallpaper folder"}, 400)
                with state.lock:
                    settings.set_(state.s, path, val)
                return self._json({"ok": True, "value": val, "dirty": state.dirty})
            if name == "theme":
                tid = str(d.get("id", ""))
                all_t = themes.all_themes()
                if tid not in all_t:
                    return self._json({"error": "unknown theme"}, 400)
                with state.lock:
                    old = all_t.get(state.s["theme"]["name"])
                    changed = themes.apply_style(state.s, all_t[tid], old)
                    state.s["theme"]["name"] = tid
                    s = copy.deepcopy(state.s)
                return self._json({"ok": True, "changed": changed, "settings": s, "dirty": state.dirty})
            if name == "revert":
                with state.lock:
                    state.s = copy.deepcopy(state.saved)
                    s = copy.deepcopy(state.s)
                return self._json({"ok": True, "settings": s, "dirty": False})
            if name == "apply":
                if state.applying:
                    return self._json({"ok": False, "busy": True})
                threading.Thread(target=_apply, args=(state,), daemon=True).start()
                return self._json({"ok": True})
            if name == "classic":
                page = str(d.get("page", ""))
                if not re.fullmatch(r"[a-z]{0,20}", page):
                    return self._json({"error": "unknown page"}, 400)
                _open_classic(state, page)
                return self._json({"ok": True})
            if name == "do":
                return self._do(d)
            if name == "preview-saver":
                name_ = str(d.get("name", "matrix"))
                from .. import render
                from ..screensaver import SAVERS
                if name_ in SAVERS and name_ != "off":
                    _spawn_term(state, f"{render.LAUNCHER} screensaver preview {name_}")
                return self._json({"ok": True})
            return self._json({"error": "unknown"}, 404)

        def _do(self, d: dict) -> None:
            from . import actions as A
            act = str(d.get("action", ""))
            try:
                if act in CHANGES_SETTINGS:
                    with state.lock:
                        out = _dispatch(state, A, act, d)
                else:                           # slow device work must not block the rest of the app
                    out = _dispatch(state, A, act, d)
            except A.Fail as e:
                return self._json({"ok": False, "msg": str(e)})
            if isinstance(out, dict):
                return self._json({"ok": True, **out, "dirty": state.dirty})
            return self._json({"ok": True, "msg": out or "", "dirty": state.dirty})

    return Handler


CHANGES_SETTINGS = {"outputs", "keys", "autostart", "sections", "theme_save", "theme_from_wallpaper",
                    "theme_delete", "theme_import", "layout_save", "layout_delete", "history",
                    "live_wallpaper", "shell_toggle", "boot_install", "system"}


def _dispatch(state: State, A, act: str, d: dict):
    """Studio buttons → actions.py. Settings changes stay staged until Apply, like everywhere else."""
    s = state.s
    v = d.get("verb", "")
    if act == "audio":
        return A.audio(str(d.get("kind")), str(v), d.get("value"))
    if act == "bluetooth":
        return A.bluetooth(str(v), str(d.get("mac", "")), bool(d.get("on", True)))
    if act == "network":
        return A.network(state, str(v), d)
    if act == "power_profile":
        return A.power_profile(str(d.get("profile", "")))
    if act == "security":
        return A.security_action(state, str(v), d)
    if act == "apps_remove":
        return A.apps_remove(state, str(d.get("id", "")))
    if act == "apps_search":
        return A.apps_search(state, str(d.get("term", "")))
    if act == "apps_install":
        return A.apps_install(state, d.get("n"))
    if act == "widgets":
        return A.widgets_action(state, str(v))
    if act == "clipboard":
        return A.clipboard_action(state, str(v), d)
    if act == "privacy":
        return A.privacy_action(state, str(v), d)
    if act == "cleanup":
        return A.cleanup_run(state, [str(x) for x in d.get("ids", [])])
    if act == "wipe":
        return A.wipe(state, d)
    if act == "mounts":
        return A.mounts_action(state, str(v), d)
    if act == "system":
        return A.system_action(state, str(v), d)
    if act == "open_file":
        return A.open_file(state, str(d.get("key", "")))
    if act == "about":
        return A.about_action(state, str(v))
    if act == "games":
        return A.games_action(state, str(v), d)
    if act == "sound_test":
        return A.sound_test(str(d.get("event", "")) if re.fullmatch(r"[a-z-]*", str(d.get("event", ""))) else "")
    if act == "outputs":
        A.set_outputs(s, list(d.get("outputs", [])), str(d.get("primary", "")))
        return "Display changes are staged – Apply to use them"
    if act == "keys":
        keys = {}
        known = {a: k for a, _l, k, _c in settings.KEY_ACTIONS}
        for aid, val in dict(d.get("keys", {})).items():
            val = str(val).strip()
            if aid in known and val != known[aid]:
                if val and not re.fullmatch(r"[\w$+-]{1,40}", val):
                    raise A.Fail(f"“{val}” is not a key combination like $mod+Shift+x")
                keys[aid] = val
        s["keys"] = keys
        return ""
    if act == "autostart":
        lines = [str(x).strip() for x in d.get("lines", []) if str(x).strip()]
        if any(len(x) > 300 for x in lines):
            raise A.Fail("A line is too long")
        s["autostart"]["extra"] = lines[:40]
        return ""
    if act == "sections":
        chosen = set(map(str, d.get("sections", [])))
        s["prompt"]["sections"] = [x for x in settings.PROMPT_SECTIONS if x in chosen]
        return ""
    if act == "theme_save":
        return A.theme_save(state, str(d.get("label", "")), dict(d.get("colors", {})))
    if act == "theme_delete":
        return A.theme_delete(state, str(d.get("id", "")))
    if act == "theme_export":
        return A.theme_export(str(d.get("id", "")))
    if act == "theme_import":
        return A.theme_import(state, str(d.get("text", "")))
    if act == "layout_save":
        return A.layout_save(state, dict(d.get("layout", {})), str(d.get("id", "")))
    if act == "layout_delete":
        return A.layout_delete(state, str(d.get("id", "")))
    if act == "theme_from_wallpaper":
        return A.theme_from_wallpaper(state, str(d.get("mode", "auto")))
    if act == "live_wallpaper":
        return A.live_wallpaper(state, str(d.get("style", "")))
    if act == "wallpacks":
        return A.wallpacks_download(state, [str(x) for x in d.get("keys", [])])
    if act == "shell_toggle":
        return {"shell": A.shell_toggle(state)}
    if act == "history":
        from .. import history
        if v == "list":
            return {"entries": history.entries()}
        if v not in ("undo", "restore"):
            raise A.Fail("unknown")
        try:
            res = history.undo() if v == "undo" else history.restore(str(d.get("id", "")))
        except ValueError as e:
            raise A.Fail(str(e)) from None
        if res.errors:
            raise A.Fail("; ".join(res.errors[:3]))
        state.s = settings.load()
        state.saved = copy.deepcopy(state.s)
        return {"msg": "Back to that version – applied", "entries": history.entries()}
    if act == "boot_install":
        if v not in ("boot", "login", "restore"):
            raise A.Fail("unknown")
        from .. import boot, render
        snap = copy.deepcopy(s)
        settings.save(snap)
        render.apply(snap)
        state.saved = snap
        script = {"boot": "apply-boot.sh", "login": "apply-login.sh", "restore": "restore-sddm.sh"}[v]
        A.term(state, f"bash {shlex.quote(str(boot.BOOT_DIR / script))}; {A.HOLD}")
        return "Runs in a terminal (it asks for your password)"
    raise A.Fail("unknown action")


def _apply(state: State) -> None:
    from .. import render
    state.applying = True
    t0 = time.time()
    try:
        with state.lock:
            snap = copy.deepcopy(state.s)
        settings.save(snap)
        res = render.apply(snap)
        with state.lock:
            state.saved = snap
        state.last_result = {"ok": not res.errors, "errors": res.errors[:5], "notes": res.notes[:8],
                             "seconds": round(time.time() - t0, 1), "at": time.time()}
    except Exception as e:                      # noqa: BLE001
        state.last_result = {"ok": False, "errors": [f"{type(e).__name__}: {e}"], "notes": [], "at": time.time()}
    finally:
        state.applying = False


def _spawn_term(state: State, cmd: str) -> None:
    import shlex
    import subprocess
    from .. import render
    full = render.terminal_cmd(state.s, "swayforge-task", f"sh -c {shlex.quote(cmd)}")
    subprocess.Popen(shlex.split(full), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_classic(state: State, page: str) -> None:
    import shlex
    import subprocess
    from .. import render
    subprocess.Popen(shlex.split(render.settings_cmd(state.s, page)), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str, State]:
    """Start the server in a thread. Returns (server, start URL, state)."""
    state = State()
    token = secrets.token_urlsafe(18)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, token))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/#t={token}"
    return srv, url, state
