"""Settings page "Games": the CS2 chat translator and the Steam shader cache (steamtune)."""
from __future__ import annotations

import importlib.util
import re
import shlex
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Checkbox, Input, Label, Static

from .. import paths
from .common import HOLD
from .panels import Panel

CS2_DIR = paths.XDG_DATA / "cs2translate"
CS2_ARGS = paths.CONFIG_DIR / "cs2.args"
STEAMTUNE = paths.XDG_DATA / "steamtune" / "steamtune.py"
STEAMTUNE_BIN = paths.HOME / ".local/bin/steamtune"
CS2_BIN = paths.HOME / ".local/bin/cs2translate"
BLOCK_START, BLOCK_END = "# --- swayforge settings (Settings → Games) ---", "# --- end swayforge settings ---"

# option → (label, default, hint)
CS2_FIELDS = {
    "font-size": ("Font size", "12", "points"),
    "alpha": ("Background opacity", "0.7", "0.2 – 1.0"),
    "duration": ("Seconds a message stays", "15", ""),
    "lines": ("Messages shown at once", "6", ""),
    "lang": ("Translate into", "de", "language code, e.g. de, en, fr"),
}


def cs2_values() -> dict[str, str]:
    """Current values: defaults, overridden by the managed block of cs2.args."""
    vals = {k: v[1] for k, v in CS2_FIELDS.items()}
    vals["no-original"] = ""
    try:
        txt = CS2_ARGS.read_text()
    except OSError:
        return vals
    m = re.search(re.escape(BLOCK_START) + r"(.*?)" + re.escape(BLOCK_END), txt, re.S)
    for line in (m.group(1).splitlines() if m else []):
        parts = line.split()
        if parts and parts[0].startswith("--"):
            vals[parts[0][2:]] = parts[1] if len(parts) > 1 else "1"
    return vals


def cs2_save(vals: dict[str, str], hide_original: bool) -> None:
    lines = [f"--{k} {shlex.quote(v)}" for k, v in vals.items() if v]
    if hide_original:
        lines.append("--no-original")
    block = BLOCK_START + "\n" + "\n".join(lines) + "\n" + BLOCK_END
    try:
        txt = CS2_ARGS.read_text()
    except OSError:
        txt = ""
    if BLOCK_START in txt:
        txt = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), lambda _m: block, txt, flags=re.S)
    else:
        txt = txt.rstrip("\n") + ("\n\n" if txt.strip() else "") + block + "\n"
    CS2_ARGS.parent.mkdir(parents=True, exist_ok=True)
    CS2_ARGS.write_text(txt)


def steamtune_module():
    spec = importlib.util.spec_from_file_location("steamtune", STEAMTUNE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)           # type: ignore[union-attr]
    return mod


class GamesPanel(Panel):
    TITLE = "Games"

    def body(self) -> ComposeResult:
        yield from self.cs2_body()
        yield from self.steam_body()

    # ── CS2 chat translator ──────────────────────────────────────────
    def cs2_body(self) -> ComposeResult:
        yield Static("CS2 chat translator", classes="section")
        if not CS2_DIR.is_dir():
            yield Static("Not installed – installer → Own tools → cs2translate.", classes="hint")
            return
        v = cs2_values()
        yield Static("Colours follow your theme. Needs the launch option -condebug in Steam. "
                     "Changes apply the next time CS2 starts.", classes="hint")
        for k, (label, _d, hint) in CS2_FIELDS.items():
            yield Horizontal(Label(label, classes="flabel flabelbox"),
                             Input(v[k], id=f"gm_cs2_{k}"), Static(hint, classes="hint"), classes="frow")
        yield Horizontal(Label("Hide original text", classes="flabel flabelbox"),
                         Checkbox("only show the translation", bool(v["no-original"]), id="gm_cs2_no-original"),
                         classes="frow")
        yield Horizontal(Button("Save", id="gm_cs2_save", variant="primary"),
                         Button("Position overlay", id="gm_cs2_move"),
                         Button("Test in terminal", id="gm_cs2_test"),
                         Button("Own options ✎", id="gm_cs2_args"), classes="btnrow")

    # ── Steam shader cache ───────────────────────────────────────────
    def steam_body(self) -> ComposeResult:
        yield Static("Steam shader cache", classes="section")
        if not STEAMTUNE.is_file():
            yield Static("Not installed – installer → Own tools → steamtune.", classes="hint")
            return
        yield Static("Steam downloads each game's shader pre-cache as one big file, so GBs come down whenever "
                     "Valve updates it. Steam has no size limit of its own – set one per drive here. "
                     "Changing files needs Steam closed.", classes="hint")
        try:
            st = steamtune_module()
            root = st.root()
            libs = st.libraries(root) if root else []
        except Exception as e:
            yield Static(f"Could not read Steam: {e}", classes="warn")
            return
        if not libs:
            yield Static("No Steam found.", classes="hint")
        for i, lib in enumerate(libs):
            yield Static(f"[{i}] {lib}", id=f"gm_st_info{i}", classes="hint", markup=False)
            yield Horizontal(Label("Limit", classes="flabel flabelbox"),
                             Input(id=f"gm_st_limit{i}", placeholder="e.g. 30G · empty = none"),
                             Button("Set", id=f"gm_st_setlimit{i}"), classes="frow")
            yield Horizontal(Label("Keep cache on", classes="flabel flabelbox"),
                             Input(id=f"gm_st_move{i}", placeholder="folder on another drive, e.g. /mnt/games/sc"),
                             Button("Move", id=f"gm_st_domove{i}"),
                             Button("Back", id=f"gm_st_back{i}"), classes="frow")
        yield Horizontal(Label("Auto-update window", classes="flabel flabelbox"),
                         Input(id="gm_st_window", placeholder="e.g. 03-06 · empty = anytime"),
                         Button("Set", id="gm_st_setwindow"), classes="frow")
        yield Horizontal(Button("Status", id="gm_st_status", variant="primary"),
                         Button("Prune (preview)", id="gm_st_dry"),
                         Button("Prune now", id="gm_st_prune"), classes="btnrow")

    def refresh_data(self) -> None:
        if STEAMTUNE.is_file():
            self.load_steam()

    @work(thread=True, exclusive=True, group="games")
    def load_steam(self) -> None:
        try:
            st = steamtune_module()
            root = st.root()
            lims = st.load_cfg().get("limits", {})
            rows = []
            for i, lib in enumerate(st.libraries(root) if root else []):
                if lib.is_dir():
                    size = sum(b for _, b, _ in st.apps_in(lib, root))
                    lim = lims.get(str(lib))
                    rows.append((i, f"[{i}] {lib} · cache {st.human(size)} · drive free "
                                    f"{st.human(st.shutil.disk_usage(lib).free)}", str(lim) if lim else "",
                                 st.window(root)))
                else:
                    rows.append((i, f"[{i}] {lib} · not mounted", "", st.window(root)))
        except Exception:
            return
        self.app.call_from_thread(self._loaded, rows)

    def _loaded(self, rows: list) -> None:
        for i, text, lim, _win in rows:
            try:
                self.query_one(f"#gm_st_info{i}", Static).update(text)
                if lim and not self.query_one(f"#gm_st_limit{i}", Input).value:
                    self.query_one(f"#gm_st_limit{i}", Input).value = _human_in(int(lim))
            except Exception:
                pass

    # ── buttons ──────────────────────────────────────────────────────
    def steamtune(self, *args: str) -> None:
        r = subprocess.run([str(STEAMTUNE_BIN), *args], capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip().splitlines()
        self.app.notify(out[-1] if out else "done", severity="information" if r.returncode == 0 else "warning",
                        timeout=8)
        self.load_steam()

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        bid = ev.button.id or ""
        if not bid.startswith("gm_"):
            return
        ev.stop()
        hold = HOLD
        if bid == "gm_cs2_save":
            vals = {k: self.query_one(f"#gm_cs2_{k}", Input).value.strip() for k in CS2_FIELDS}
            cs2_save(vals, self.query_one("#gm_cs2_no-original", Checkbox).value)
            self.app.notify("Saved – applies the next time CS2 starts (restart the watcher: swayforge apply)")
        elif bid == "gm_cs2_move":
            subprocess.Popen([str(CS2_BIN), "--move"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.app.notify("Drag the overlay over the CS2 chat, then press Esc", timeout=6)
        elif bid == "gm_cs2_test":
            self.app.spawn_term(f"{shlex.quote(str(CS2_BIN))} --terminal --debug; {hold}")      # type: ignore[attr-defined]
        elif bid == "gm_cs2_args":
            self.app.open_file(CS2_ARGS)                                                          # type: ignore[attr-defined]
        elif bid == "gm_st_status":
            self.app.spawn_term(f"{shlex.quote(str(STEAMTUNE_BIN))}; {hold}")                    # type: ignore[attr-defined]
        elif bid in ("gm_st_dry", "gm_st_prune"):
            sub = "prune --dry" if bid == "gm_st_dry" else "prune"
            self.app.spawn_term(f"{shlex.quote(str(STEAMTUNE_BIN))} {sub}; {hold}")             # type: ignore[attr-defined]
        elif bid == "gm_st_setwindow":
            self.steamtune("window", self.query_one("#gm_st_window", Input).value.strip() or "off")
        elif bid.startswith("gm_st_setlimit"):
            n = bid.removeprefix("gm_st_setlimit")
            self.steamtune("limit", n, self.query_one(f"#gm_st_limit{n}", Input).value.strip() or "off")
        elif bid.startswith("gm_st_domove"):
            n = bid.removeprefix("gm_st_domove")
            dest = self.query_one(f"#gm_st_move{n}", Input).value.strip()
            if dest:
                self.app.spawn_term(f"{shlex.quote(str(STEAMTUNE_BIN))} move {n} {shlex.quote(dest)}; {hold}")  # type: ignore[attr-defined]
        elif bid.startswith("gm_st_back"):
            n = bid.removeprefix("gm_st_back")
            self.app.spawn_term(f"{shlex.quote(str(STEAMTUNE_BIN))} move {n} back; {hold}")      # type: ignore[attr-defined]


def _human_in(n: int) -> str:
    """Bytes → the short form the limit field takes (30G, 500M)."""
    for unit, f in (("T", 10 ** 12), ("G", 10 ** 9), ("M", 10 ** 6)):
        if n >= f:
            v = n / f
            return f"{v:g}{unit}" if v == int(v) else f"{v:.1f}{unit}"
    return str(n)
