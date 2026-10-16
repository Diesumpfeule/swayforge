"""Installed apps, cleanup and the drive wiper – pages of the settings app."""
from __future__ import annotations

import os
import shlex

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Select, Static

from .. import apps, catalog, cleanup, mounts, render
from ..system import have
from .panels import Panel


# ── Installed apps ───────────────────────────────────────────────────
class AppsPanel(Panel):
    TITLE = "Installed apps"
    NEEDS = ("rpm",)

    def body(self) -> ComposeResult:
        yield Static("Grouped like the installer. [b]Other[/b] = what you installed yourself (dnf/Flatpak). "
                     "Size = the app's own packages, shared libraries not counted. Uninstalling opens a "
                     "terminal and dnf/flatpak ask once more.", classes="hint")
        yield Horizontal(Input(placeholder="filter …", id="ap_filter"),
                         Select([], prompt="all groups", id="ap_group"),
                         Button("↻", id="ap_refresh", classes="small"), classes="btnrow")
        yield Static("loading …", id="ap_sum", classes="hint")
        table = DataTable(id="ap_table", cursor_type="row", zebra_stripes=True)
        yield table
        yield Static("", id="ap_detail", classes="hint")
        yield Horizontal(Button("Uninstall …", id="ap_remove", disabled=True),
                         Button("Install more (installer)", id="ap_installer"), classes="btnrow")

    def on_mount(self) -> None:
        t = self.query_one("#ap_table", DataTable)
        t.add_column("App", key="app", width=34)
        t.add_column("Source", key="src", width=20)
        t.add_column("Size", key="size", width=10)
        self.entries: list[apps.Entry] = []
        self.loaded = False
        self.cat = catalog.load()
        self.labels = {g.id: g.label for g in self.cat.groups} | {apps.OTHER: "Other (yours)"}

    def on_show(self) -> None:
        if not self.loaded:
            self.refresh_data()

    @work(thread=True, exclusive=True, group="apps")
    def refresh_data(self) -> None:
        entries = apps.inventory(self.cat)
        self.app.call_from_thread(self._loaded, entries)

    def _loaded(self, entries: list[apps.Entry]) -> None:
        self.entries, self.loaded = entries, True
        groups = [g for g in list(self.labels) if any(e.group == g for e in entries)]
        sel = self.query_one("#ap_group", Select)
        with self.prevent(Select.Changed):
            sel.set_options([(self.labels[g], g) for g in groups])
        self.fill()

    def fill(self) -> None:
        t = self.query_one("#ap_table", DataTable)
        t.clear()
        q = self.query_one("#ap_filter", Input).value.strip().lower()
        gsel = self.query_one("#ap_group", Select).value
        total, n = 0, 0
        for g, glabel in self.labels.items():
            if isinstance(gsel, str) and g != gsel:
                continue
            rows = [e for e in self.entries if e.group == g and (
                not q or q in f"{e.label} {e.source} {' '.join(e.rpms + e.flatpaks)}".lower())]
            if not rows:
                continue
            gsize = sum(e.size for e in rows)
            t.add_row(Text(f"▾ {glabel}  ({len(rows)})", style="bold"), "",
                      Text(apps.human(gsize), style="bold"), key=f"hdr:{g}")
            for e in sorted(rows, key=lambda e: (-e.size if g == apps.OTHER else 0, e.label.lower())):
                src = Text(e.source, style="yellow" if "Flatpak" in e.source else
                           "cyan" if e.source in ("COPR", "RPM Fusion") else "")
                name = Text("  " + e.label) + (Text("  base", style="dim") if e.locked else Text(""))
                t.add_row(name, src, apps.human(e.size), key=e.id)
                total += e.size
                n += 1
        self.query_one("#ap_sum", Static).update(f"{n} apps · {apps.human(total)}")
        self.current = None
        self._show(None)

    def _show(self, e: apps.Entry | None) -> None:
        btn = self.query_one("#ap_remove", Button)
        det = self.query_one("#ap_detail", Static)
        if not e:
            btn.disabled = True
            det.update("Pick an app with ↑↓ or a click.")
            return
        what = ", ".join(e.rpms + e.flatpaks)
        if e.locked:
            det.update(f"[b]{e.label}[/b] – part of the swayforge desktop base ({what}). "
                       "Removing it would break Sway, so it can't be uninstalled here.")
            btn.disabled = True
        else:
            det.update(f"[b]{e.label}[/b] · {e.source} · {apps.human(e.size)} · packages: {what}")
            btn.disabled = False

    @on(DataTable.RowHighlighted, "#ap_table")
    def highlighted(self, ev: DataTable.RowHighlighted) -> None:
        key = ev.row_key.value if ev.row_key else None
        self.current = next((e for e in self.entries if e.id == key), None)
        self._show(self.current)

    @on(Input.Changed, "#ap_filter")
    @on(Select.Changed, "#ap_group")
    def refilter(self, ev) -> None:
        ev.stop()
        if self.loaded:
            self.fill()

    @on(Button.Pressed, "#ap_refresh, #ap_remove, #ap_installer")
    def buttons(self, ev: Button.Pressed) -> None:
        ev.stop()
        if ev.button.id == "ap_refresh":
            self.loaded = False
            self.query_one("#ap_sum", Static).update("loading …")
            self.refresh_data()
        elif ev.button.id == "ap_installer":
            self.app.spawn_term(f"{shlex.quote(render.LAUNCHER)} install")   # type: ignore[attr-defined]
        elif self.current and not self.current.locked:
            hold = "echo; read -n1 -rsp 'Done – press any key to close'"
            self.app.spawn_term(f"{self.current.remove_cmd()}; {hold}")      # type: ignore[attr-defined]
            self.app.notify(f"Uninstalling {self.current.label} in a terminal – press ↻ afterwards")


class ClCheck(Checkbox):
    BUTTON_INNER = "✓"


# ── Cleanup & drives ─────────────────────────────────────────────────
class WipeConfirm(ModalScreen[bool]):
    """Last stop before a wipe: shows the drive and wants its name typed."""
    CSS = """
    WipeConfirm { align: center middle; }
    #wc_box { width: 72; height: auto; border: thick $error; background: $panel; padding: 1 2; }
    #wc_box Static { margin-bottom: 1; }
    #wc_box .btnrow { height: auto; }
    """

    def __init__(self, d: dict, mode: str, fs: str, label: str) -> None:
        super().__init__()
        self.d, self.mode, self.fs, self.label = d, mode, fs, label

    def compose(self) -> ComposeResult:
        d = self.d
        with Vertical(id="wc_box"):
            yield Static("[b $error]Wipe this drive? Everything on it will be gone – no undo.[/]")
            yield Static(f"[b]{d['path']}[/b]   {d['model']} · {apps.human(d['size'])} · {d['kind']}\n"
                         f"partitions: {', '.join(d['parts']) or 'none'}\n"
                         f"{cleanup.MODES[self.mode]}\n"
                         + ("[yellow]no discard support → zero-fill instead[/]\n"
                            if self.mode == "discard" and not d["discard"] else "") +
                         f"then: {cleanup.FILESYSTEMS[self.fs]}")
            yield Static(f"Type [b]{d['name']}[/b] to confirm:")
            yield Input(id="wc_name")
            yield Horizontal(Button("Cancel", id="wc_no"),
                             Button("Wipe", id="wc_yes", variant="error", disabled=True), classes="btnrow")

    @on(Input.Changed, "#wc_name")
    def typed(self, ev: Input.Changed) -> None:
        self.query_one("#wc_yes", Button).disabled = ev.value.strip() != self.d["name"]

    @on(Input.Submitted, "#wc_name")
    def submitted(self, ev: Input.Submitted) -> None:
        if ev.value.strip() == self.d["name"]:
            self.dismiss(True)

    @on(Button.Pressed)
    def pressed(self, ev: Button.Pressed) -> None:
        ev.stop()
        self.dismiss(ev.button.id == "wc_yes")

    def key_escape(self) -> None:
        self.dismiss(False)


class CleanupPanel(Panel):
    TITLE = "Cleanup & drives"

    def body(self) -> ComposeResult:
        yield Static("System cleanup", classes="section")
        yield Static("Tick what you want gone, then Clean. Everything runs in a terminal with the plain "
                     "command shown, so you see what happens (sudo asks for your password).", classes="hint")
        yield Vertical(Static("measuring …", classes="hint"), id="cl_items")
        yield Horizontal(Button("Clean selected", id="cl_run", variant="primary"),
                         Button("↻", id="cl_refresh", classes="small"),
                         Button("What uses my disk? (ncdu)", id="cl_ncdu"),
                         Button("BleachBit", id="cl_bleach"), classes="btnrow")
        yield Static("Wipe a USB stick, SD card or external SSD", classes="section")
        yield Static("Only removable drives that hold nothing of the running system are listed – your "
                     "internal disks never show up here. Quick = new and empty in seconds. Secure = every "
                     "block overwritten or discarded, for giving a drive away.", classes="hint")
        yield Horizontal(Label("Drive", classes="flabel flabelbox"),
                         Select([], prompt="pick a drive …", id="wp_drive"),
                         Button("↻", id="wp_refresh", classes="small"), classes="frow")
        yield Horizontal(Label("Erase", classes="flabel flabelbox"),
                         Select([(v, k) for k, v in cleanup.MODE_SHORT.items()], value="quick",
                                allow_blank=False, id="wp_mode"), classes="frow")
        yield Horizontal(Label("Then format as", classes="flabel flabelbox"),
                         Select([(v, k) for k, v in cleanup.FS_SHORT.items()], value="exfat",
                                allow_blank=False, id="wp_fs"), classes="frow")
        yield Horizontal(Label("Name", classes="flabel flabelbox"),
                         Input("USB", id="wp_label", max_length=11), classes="frow")
        yield Static("", id="wp_info", classes="hint")
        yield Horizontal(Button("Wipe drive …", id="wp_go", variant="error", disabled=True),
                         Button("nwipe (advanced)", id="wp_nwipe"), classes="btnrow")

    def on_mount(self) -> None:
        self.items: list[cleanup.Item] = []
        self.drives: list[dict] = []

    def on_show(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self.measure()
        self.scan_drives()

    @work(thread=True, exclusive=True, group="cleanup")
    def measure(self) -> None:
        items = cleanup.items(measure=True)
        self.app.call_from_thread(self._items, items)

    def _items(self, items: list[cleanup.Item]) -> None:
        old = {cb.id[3:]: cb.value for cb in self.query("#cl_items Checkbox")}
        self.items = items
        box = self.query_one("#cl_items", Vertical)
        box.remove_children()
        rows = []
        for it in items:
            default = it.id not in ("coredumps",) and (it.size != 0)
            rows.append(Horizontal(ClCheck(cleanup.describe(it), value=old.get(it.id, default),
                                            id=f"cl_{it.id}", classes="clcheck"),
                                   Static(f"[dim]{it.desc}[/]", classes="cldesc"), classes="clrow"))
        known = sum(i.size for i in items if i.size > 0)
        rows.append(Static(f"[b]≈ {apps.human(known)}[/b] can be freed (plus what can't be measured "
                           "without root)", classes="hint"))
        box.mount_all(rows)

    @work(thread=True, exclusive=True, group="drives")
    def scan_drives(self) -> None:
        drives = cleanup.wipeable_drives()
        self.app.call_from_thread(self._drives, drives)

    def _drives(self, drives: list[dict]) -> None:
        self.drives = drives
        sel = self.query_one("#wp_drive", Select)
        prev = sel.value
        with self.prevent(Select.Changed):
            sel.set_options([(cleanup.drive_label(d), d["name"]) for d in drives])
            if prev in [d["name"] for d in drives]:
                sel.value = prev
        sel.disabled = not drives
        self._drive_info()

    def _drive(self) -> dict | None:
        v = self.query_one("#wp_drive", Select).value
        return next((d for d in self.drives if d["name"] == v), None)

    def _drive_info(self) -> None:
        d = self._drive()
        info = self.query_one("#wp_info", Static)
        self.query_one("#wp_go", Button).disabled = d is None
        if not d:
            info.update("No removable drive found – plug one in and press ↻." if not self.drives
                        else f"{len(self.drives)} removable drive(s) – pick one.")
            return
        mode = self.query_one("#wp_mode", Select).value
        fs = self.query_one("#wp_fs", Select).value
        txt = (f"{cleanup.MODES.get(str(mode), '')}\nthen {cleanup.FILESYSTEMS.get(str(fs), '')}\n"
               f"{d['path']} · partitions: {', '.join(d['parts']) or 'none'}")
        if d["mounted"]:
            txt += f" · mounted at {', '.join(d['mounted'])} (will be unmounted)"
        if mode == "discard" and not d["discard"]:
            txt += "\n[yellow]This drive doesn't report discard support – it will be zero-filled instead.[/]"
        if mode == "zero":
            txt += (f"\nZero-fill of {apps.human(d['size'])} takes a while. On flash memory wear levelling can "
                    "keep stray old blocks – for secrets, encrypt from the start.")
        info.update(txt)

    @on(Select.Changed, "#wp_drive, #wp_mode, #wp_fs")
    def drive_changed(self, ev: Select.Changed) -> None:
        ev.stop()
        self._drive_info()

    @on(Checkbox.Changed, ".clcheck")
    @on(Input.Changed, "#wp_label")
    def local(self, ev) -> None:
        ev.stop()

    @on(Button.Pressed, "#cl_run, #cl_refresh, #cl_ncdu, #cl_bleach, #wp_refresh, #wp_go, #wp_nwipe")
    def buttons(self, ev: Button.Pressed) -> None:
        ev.stop()
        bid = ev.button.id
        app = self.app
        hold = "echo; read -n1 -rsp 'Done – press any key to close'"
        if bid == "cl_run":
            chosen = [it for it in self.items if self.query_one(f"#cl_{it.id}", Checkbox).value]
            if not chosen:
                app.notify("Nothing ticked", severity="warning")
                return
            script = "; ".join(f"echo; echo '── {it.label}: {it.cmd.replace(chr(39), '')}'; {it.cmd}" for it in chosen)
            app.spawn_term(f"{script}; {hold}")                                   # type: ignore[attr-defined]
            app.notify("Cleaning in a terminal – press ↻ afterwards to re-measure")
        elif bid == "cl_refresh":
            self.measure()
        elif bid == "cl_ncdu":
            if not have("ncdu"):
                app.notify("ncdu isn't installed – installer → System → Cleanup tools", severity="warning")
                return
            app.spawn_term("ncdu ~")                                              # type: ignore[attr-defined]
        elif bid == "cl_bleach":
            if not have("bleachbit"):
                app.notify("BleachBit isn't installed – installer → System → Cleanup tools", severity="warning")
                return
            import subprocess
            subprocess.Popen(["bleachbit"], start_new_session=True, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif bid == "wp_refresh":
            self.scan_drives()
        elif bid == "wp_nwipe":
            if not have("nwipe"):
                app.notify("nwipe isn't installed – installer → USB & SD → Drive wiping", severity="warning")
                return
            app.spawn_term(f"sudo nwipe; {hold}")                                 # type: ignore[attr-defined]
        elif bid == "wp_go":
            d = self._drive()
            if not d:
                return
            mode = str(self.query_one("#wp_mode", Select).value)
            fs = str(self.query_one("#wp_fs", Select).value)
            label = self.query_one("#wp_label", Input).value.strip() or "USB"

            def go(ok: bool | None) -> None:
                if not ok:
                    app.notify("Cancelled – nothing changed")
                    return
                L = shlex.quote(render.LAUNCHER)
                app.spawn_term(f"{L} wipe {shlex.quote(d['name'])} --mode {mode} --fs {fs} "  # type: ignore[attr-defined]
                               f"--label {shlex.quote(label)} --size {d['size']} --confirm {shlex.quote(d['name'])}; "
                               f"{hold}")
                app.notify(f"Wiping {d['name']} in a terminal")
            app.push_screen(WipeConfirm(d, mode, fs, label), go)


# ── Mount drives permanently ─────────────────────────────────────────
class MountsPanel(Panel):
    TITLE = "Mount drives"

    def body(self) -> ComposeResult:
        yield Static("Pick a drive, give it a name, Mount: it appears at /mnt/NAME and in Thunar's sidebar, "
                     "now and after every reboot. Internal SSDs and external drives both work. A missing "
                     "drive never blocks booting, and /etc/fstab is backed up and checked first – "
                     "a broken line is undone automatically.", classes="hint")
        yield Static("Add a drive", classes="section")
        yield Horizontal(Label("Drive", classes="flabel flabelbox"),
                         Select([], prompt="pick a drive …", id="mt_drive"),
                         Button("↻", id="mt_refresh", classes="small"), classes="frow")
        yield Horizontal(Label("Name", classes="flabel flabelbox"),
                         Input(id="mt_name", max_length=32, placeholder="e.g. games, data, backup"),
                         classes="frow")
        yield Static("", id="mt_info", classes="hint")
        yield Horizontal(Button("Mount permanently", id="mt_add", variant="primary", disabled=True),
                         classes="btnrow")
        yield Static("Mounted by swayforge", classes="section")
        yield Vertical(id="mt_list")

    def on_mount(self) -> None:
        self.cands: list[dict] = []

    def on_show(self) -> None:
        self.refresh_data()

    @work(thread=True, exclusive=True, group="mounts")
    def refresh_data(self) -> None:
        c, e = mounts.candidates(), mounts.entries()
        self.app.call_from_thread(self._loaded, c, e)

    def _loaded(self, cands: list[dict], ents: list[dict]) -> None:
        self.cands = cands
        sel = self.query_one("#mt_drive", Select)
        with self.prevent(Select.Changed):
            sel.set_options([(mounts.describe(c), c["name"]) for c in cands])
        sel.disabled = not cands
        self._info()
        box = self.query_one("#mt_list", Vertical)
        box.remove_children()
        if not ents:
            box.mount(Static("none yet", classes="hint"))
        for e in ents:
            state = "[green]● mounted[/]" if e["mounted"] else "[yellow]○ not mounted[/]"
            box.mount(Horizontal(Static(f"{state}  [b]{e['target']}[/b]  {e['label']} · {e['fstype']}",
                                        classes="mtrow"),
                                 Button("Open", name=f"mt_open:{e['target']}"),
                                 Button("Remove", name=f"mt_rm:{e['target']}"),
                                 classes="btnrow"))

    def _cand(self) -> dict | None:
        v = self.query_one("#mt_drive", Select).value
        return next((c for c in self.cands if c["name"] == v), None)

    def _info(self) -> None:
        c = self._cand()
        name = mounts.clean_name(self.query_one("#mt_name", Input).value)
        info = self.query_one("#mt_info", Static)
        self.query_one("#mt_add", Button).disabled = not (c and name)
        if not c:
            info.update("Nothing new to mount – every drive with a file system is already set up."
                        if not self.cands else "")
            return
        line = mounts.fstab_line(c, name or "NAME", os.getuid(), os.getgid())
        extra = ""
        if c["fstype"] == "ntfs":
            extra = "\nWindows drive: works read/write; turn off Windows “Fast Startup” or it stays locked."
        info.update(f"→ /mnt/{name or 'NAME'}\nfstab: {line}{extra}")

    @on(Select.Changed, "#mt_drive")
    def picked(self, ev: Select.Changed) -> None:
        ev.stop()
        c = self._cand()
        inp = self.query_one("#mt_name", Input)
        if c and not inp.value.strip():
            inp.value = mounts.default_name(c)
        self._info()

    @on(Input.Changed, "#mt_name")
    def named(self, ev: Input.Changed) -> None:
        ev.stop()
        self._info()

    @on(Button.Pressed)
    def buttons(self, ev: Button.Pressed) -> None:
        bid, name = ev.button.id or "", ev.button.name or ""
        if not (bid.startswith("mt_") or name.startswith("mt_")):
            return
        ev.stop()
        app = self.app
        L = shlex.quote(render.LAUNCHER)
        hold = "echo; read -n1 -rsp 'Done – press any key to close'"
        if bid == "mt_refresh":
            self.refresh_data()
        elif bid == "mt_add":
            c = self._cand()
            n = mounts.clean_name(self.query_one("#mt_name", Input).value)
            if c and n:
                app.spawn_term(f"{L} mount add {shlex.quote(c['name'])} {shlex.quote(n)}; {hold}")  # type: ignore[attr-defined]
                app.notify("Mounting in a terminal – press ↻ afterwards")
        elif name.startswith("mt_rm:"):
            app.spawn_term(f"{L} mount remove {shlex.quote(name[6:])}; {hold}")                   # type: ignore[attr-defined]
            app.notify("Removing in a terminal – the data on the drive stays")
        elif name.startswith("mt_open:"):
            import subprocess
            subprocess.Popen(["xdg-open", name[8:]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
