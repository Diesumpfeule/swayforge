"""Audio, Bluetooth and network pages of the settings app (pactl, bluetoothctl, nmcli)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (Button, Input, Label, ListItem, ListView, ProgressBar, Select,
                             Static, Switch)

from rich.markup import escape

from .. import paths
from ..system import have, run
from .common import HOLD


def _sh(*cmd: str, timeout: float = 15) -> subprocess.CompletedProcess:
    try:
        return run(list(cmd), timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


class Panel(VerticalScroll):
    """Base: loads data in the background as soon as the page becomes visible."""
    TITLE = ""
    NEEDS: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="pagetitle")
        missing = [c for c in self.NEEDS if not have(c)]
        if missing:
            yield Static(f"Missing: {', '.join(missing)} – the installer sets this up.", classes="warn")
        yield from self.body()

    def body(self) -> ComposeResult:  # pragma: no cover
        yield from ()

    def on_show(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:  # pragma: no cover
        pass

    def stop(self, ev) -> None:
        ev.stop()


# ── Audio ────────────────────────────────────────────────────────────
class AudioPanel(Panel):
    TITLE = "Audio"
    NEEDS = ("pactl", "wpctl")

    def body(self) -> ComposeResult:
        for kind, label in (("sink", "Output (speakers/headphones)"), ("source", "Input (microphone)")):
            yield Static(label, classes="section")
            yield Horizontal(Label("Device", classes="flabel flabelbox"),
                             Select([], allow_blank=True, prompt="…", id=f"au_{kind}"), classes="frow")
            yield Horizontal(Label("Volume", classes="flabel flabelbox"),
                             Button("−", id=f"au_{kind}_down", classes="small"),
                             ProgressBar(total=150, show_eta=False, show_percentage=False, id=f"au_{kind}_bar"),
                             Static("", id=f"au_{kind}_val", classes="volval"),
                             Button("+", id=f"au_{kind}_up", classes="small"), classes="frow")
            yield Horizontal(Label("Muted", classes="flabel flabelbox"),
                             Switch(id=f"au_{kind}_mute"), classes="frow")
        yield Horizontal(Button("Refresh", id="au_refresh"),
                         Button("Advanced (pavucontrol)", id="au_pavu"), classes="btnrow")
        yield Static("Tip: in the bar, scroll on the speaker = volume, right-click = mute, "
                     "click = this page.", classes="hint")

    @work(thread=True, exclusive=True, group="audio")
    def refresh_data(self) -> None:
        data = {}
        for kind in ("sink", "source"):
            r = _sh("pactl", "-f", "json", "list", f"{kind}s")
            try:
                devs = json.loads(r.stdout) if r.returncode == 0 else []
            except json.JSONDecodeError:
                devs = []
            if kind == "source":
                devs = [d for d in devs if not d.get("name", "").endswith(".monitor")]
            default = _sh("pactl", f"get-default-{kind}").stdout.strip()
            cur = next((d for d in devs if d.get("name") == default), devs[0] if devs else None)
            vol = 0
            if cur:
                try:
                    vol = int(next(iter(cur["volume"].values()))["value_percent"].rstrip("%"))
                except (KeyError, StopIteration, ValueError, AttributeError):
                    vol = 0
            data[kind] = (devs, default, vol, bool(cur and cur.get("mute")))
        self.app.call_from_thread(self._show, data)

    def _show(self, data) -> None:
        for kind, (devs, default, vol, mute) in data.items():
            sel = self.query_one(f"#au_{kind}", Select)
            opts = [(d.get("description") or d["name"], d["name"]) for d in devs]
            with self.prevent(Select.Changed, Switch.Changed):
                sel.set_options(opts)
                if default in [v for _, v in opts]:
                    sel.value = default
                self.query_one(f"#au_{kind}_mute", Switch).value = mute
            self.query_one(f"#au_{kind}_bar", ProgressBar).update(progress=vol)
            self.query_one(f"#au_{kind}_val", Static).update(f"{vol} %")

    @on(Select.Changed)
    def device(self, ev: Select.Changed) -> None:
        ev.stop()
        kind = (ev.select.id or "")[3:]
        if isinstance(ev.value, str):
            _sh("pactl", f"set-default-{kind}", ev.value)
            self.refresh_data()

    @on(Switch.Changed)
    def mute(self, ev: Switch.Changed) -> None:
        ev.stop()
        kind = (ev.switch.id or "").split("_")[1]
        _sh("pactl", f"set-{kind}-mute", f"@DEFAULT_{kind.upper()}@", "1" if ev.value else "0")

    @on(Button.Pressed)
    def buttons(self, ev: Button.Pressed) -> None:
        ev.stop()
        bid = ev.button.id or ""
        if bid == "au_refresh":
            self.refresh_data()
        elif bid == "au_pavu":
            subprocess.Popen(["pavucontrol"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif bid.endswith(("_up", "_down")):
            kind = bid.split("_")[1]
            step = "+5%" if bid.endswith("_up") else "-5%"
            _sh("pactl", f"set-{kind}-volume", f"@DEFAULT_{kind.upper()}@", step)
            self.refresh_data()


# ── Bluetooth ────────────────────────────────────────────────────────
class BluetoothPanel(Panel):
    TITLE = "Bluetooth"
    NEEDS = ("bluetoothctl",)

    def body(self) -> ComposeResult:
        yield Horizontal(Label("Bluetooth on", classes="flabel flabelbox"), Switch(id="bt_power"), classes="frow")
        yield Static("Devices", classes="section")
        yield Static("", id="bt_status", classes="hint")
        yield ListView(id="bt_list")
        yield Horizontal(Button("Scan (10 s)", id="bt_scan", variant="primary"),
                         Button("Connect", id="bt_connect", variant="success"),
                         Button("Disconnect", id="bt_disconnect"),
                         Button("Pair", id="bt_pair"),
                         Button("Remove", id="bt_remove", variant="error"), classes="btnrow")
        yield Horizontal(Button("Refresh", id="bt_refresh"),
                         Button("Advanced (Blueman)", id="bt_blueman"), classes="btnrow")
        yield Static("New device: put it into pairing mode → Scan → select it → Pair.", classes="hint")

    @work(thread=True, exclusive=True, group="bt")
    def refresh_data(self) -> None:
        powered = "Powered: yes" in _sh("bluetoothctl", "show").stdout
        devs = []
        for line in _sh("bluetoothctl", "devices").stdout.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[0] == "Device":
                info = _sh("bluetoothctl", "info", parts[1], timeout=5).stdout
                devs.append((parts[1], parts[2], "Connected: yes" in info, "Paired: yes" in info))
        devs.sort(key=lambda d: (not d[2], not d[3], d[1].lower()))
        self.app.call_from_thread(self._show, powered, devs)

    def _show(self, powered: bool, devs) -> None:
        with self.prevent(Switch.Changed):
            self.query_one("#bt_power", Switch).value = powered
        lv = self.query_one("#bt_list", ListView)
        lv.clear()
        for mac, name, conn, paired in devs:
            state = "[green]● connected[/]" if conn else ("[dim]paired[/]" if paired else "[dim]new[/]")
            lv.append(ListItem(Label(f"{name:<34} {state}   [dim]{mac}[/]"), name=mac))
        self.query_one("#bt_status", Static).update(
            "No known devices – press Scan." if not devs else f"{len(devs)} device(s)")

    @on(Switch.Changed, "#bt_power")
    def power(self, ev: Switch.Changed) -> None:
        ev.stop()
        _sh("bluetoothctl", "power", "on" if ev.value else "off")
        self.refresh_data()

    def selected(self) -> str | None:
        item = self.query_one("#bt_list", ListView).highlighted_child
        return item.name if item else None

    @work(thread=True, group="bt-action")
    def action(self, verb: str, mac: str) -> None:
        self.app.call_from_thread(self.query_one("#bt_status", Static).update, f"{verb} {mac} …")
        if verb == "pair":
            r = _sh("bluetoothctl", "pair", mac, timeout=30)
            _sh("bluetoothctl", "trust", mac)
            if r.returncode == 0:
                r = _sh("bluetoothctl", "connect", mac, timeout=20)
        else:
            r = _sh("bluetoothctl", verb, mac, timeout=20)
        msg = (r.stdout + r.stderr).strip().splitlines()
        self.app.call_from_thread(self.app.notify, msg[-1] if msg else verb,
                                  severity="information" if r.returncode == 0 else "error")
        self.refresh_data()

    @work(thread=True, exclusive=True, group="bt-scan")
    def scan(self) -> None:
        self.app.call_from_thread(self.query_one("#bt_status", Static).update, "Scanning (10 s) …")
        _sh("bluetoothctl", "--timeout", "10", "scan", "on", timeout=15)
        self.refresh_data()

    @on(Button.Pressed)
    def buttons(self, ev: Button.Pressed) -> None:
        ev.stop()
        bid = ev.button.id or ""
        if bid == "bt_refresh":
            self.refresh_data()
        elif bid == "bt_scan":
            self.scan()
        elif bid == "bt_blueman":
            subprocess.Popen(["blueman-manager"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif bid in ("bt_connect", "bt_disconnect", "bt_pair", "bt_remove"):
            mac = self.selected()
            if not mac:
                self.app.notify("Select a device first", severity="warning")
                return
            self.action(bid[3:], mac)


# ── Network ─────────────────────────────────────────────────────────
_SPLIT = re.compile(r"(?<!\\):")


def _fields(line: str) -> list[str]:
    return [f.replace("\\:", ":") for f in _SPLIT.split(line)]


class NetworkPanel(Panel):
    TITLE = "Network"
    NEEDS = ("nmcli",)
    _del_armed = ""
    vpns: dict = {}

    def body(self) -> ComposeResult:
        yield Static("Connected", classes="section")
        yield Static("…", id="net_active")
        yield Static("Wi-Fi", classes="section")
        yield Horizontal(Label("Wi-Fi on", classes="flabel flabelbox"), Switch(id="net_wifi"), classes="frow")
        yield ListView(id="net_list")
        yield Horizontal(Input(placeholder="Password (only needed for new networks)", password=True, id="net_pw"),
                         Button("Connect", id="net_connect", variant="success"), classes="btnrow")
        yield Horizontal(Button("Rescan", id="net_scan", variant="primary"),
                         Button("Disconnect", id="net_disconnect"),
                         Button("nmtui", id="net_nmtui"),
                         Button("Connection editor", id="net_editor"), classes="btnrow")
        yield Static("Ethernet, static IP etc.: via nmtui or the connection editor.", classes="hint")
        yield Static("VPN", classes="section")
        yield Static("Import the file your VPN provider gave you (OpenVPN [b].ovpn[/b] or WireGuard [b].conf[/b]), "
                     "then connect with one click. Passwords are never stored by swayforge – if the VPN needs "
                     "one, a terminal asks for it.", classes="hint")
        yield ListView(id="vpn_list")
        yield Horizontal(Button("Connect", id="vpn_up", variant="success"),
                         Button("Disconnect", id="vpn_down"),
                         Button("Auto-connect on/off", id="vpn_auto"),
                         Button("Delete", id="vpn_del", variant="error"), classes="btnrow")
        yield Static("Add a VPN", classes="section")
        yield Horizontal(Select([], prompt="config files found in Downloads / home …", id="vpn_found",
                                allow_blank=True),
                         Button("↻", id="vpn_rescan", classes="small"), classes="btnrow")
        yield Horizontal(Input(placeholder="or path to a .ovpn / .conf file", id="vpn_path"),
                         Input(placeholder="username (OpenVPN, optional)", id="vpn_user"),
                         Button("Import", id="vpn_import", variant="primary"), classes="btnrow")
        yield Static("", id="vpn_tail", classes="hint")
        yield Horizontal(Button("Tailscale up", id="ts_up"), Button("Tailscale down", id="ts_down"),
                         Button("Tailscale status", id="ts_status"), id="ts_row", classes="btnrow")

    @work(thread=True, exclusive=True, group="net")
    def refresh_data(self, rescan: bool = False) -> None:
        active = []
        for line in _sh("nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active").stdout.splitlines():
            f = _fields(line)
            if len(f) >= 3 and f[1] not in ("loopback", "bridge"):
                active.append(f)
        ips = {}
        for line in _sh("ip", "-4", "-br", "addr").stdout.splitlines():
            p = line.split()
            if len(p) >= 3:
                ips[p[0]] = p[2]
        wifi_on = _sh("nmcli", "radio", "wifi").stdout.strip() == "enabled"
        nets = []
        if wifi_on:
            r = _sh("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                    "--rescan", "yes" if rescan else "auto", timeout=25)
            seen = set()
            for line in r.stdout.splitlines():
                f = _fields(line)
                if len(f) >= 4 and f[1] and f[1] not in seen:
                    seen.add(f[1])
                    nets.append((f[0] == "*", f[1], int(f[2] or 0), f[3]))
            nets.sort(key=lambda n: (not n[0], -n[2]))
        from .. import vpn
        vpns = vpn.list_vpns()
        found = vpn.find_configs(paths.HOME)
        self.app.call_from_thread(self._show, active, ips, wifi_on, nets)
        self.app.call_from_thread(self._show_vpn, vpns, found)

    def _show(self, active, ips, wifi_on, nets) -> None:
        lines = [f"[b]{name}[/b]  [dim]{typ.replace('802-11-wireless', 'Wi-Fi').replace('802-3-ethernet', 'Ethernet')}"
                 f" · {dev} · {ips.get(dev, '–')}[/]" for name, typ, dev in active]
        self.query_one("#net_active", Static).update("\n".join(lines) or "[red]Not connected[/]")
        with self.prevent(Switch.Changed):
            self.query_one("#net_wifi", Switch).value = wifi_on
        lv = self.query_one("#net_list", ListView)
        lv.clear()
        for inuse, ssid, sig, sec in nets:
            bars = "▂▄▆█"[: max(1, min(4, sig // 25 + 1))]
            lock = "🔒" if sec and sec != "--" else "  "
            mark = "[green]●[/] " if inuse else "  "
            lv.append(ListItem(Label(f"{mark}{ssid:<32} {bars:<4} {sig:>3}%  {lock}"), name=ssid))

    def _show_vpn(self, vpns, found) -> None:
        self.vpns = {v.uuid: v for v in vpns}
        lv = self.query_one("#vpn_list", ListView)
        keep = lv.highlighted_child.name if lv.highlighted_child else ""
        lv.clear()
        for v in vpns:
            mark = "[green]●[/] " if v.active else "  "
            auto = "  [dim]auto[/]" if v.autoconnect else ""
            lv.append(ListItem(Label(f"{mark}{escape(v.name):<30} [dim]{v.kind}[/]{auto}"), name=v.uuid))
        if not vpns:
            lv.append(ListItem(Label("[dim]no VPN yet – add one below[/]"), name=""))
        if keep:
            for i, v in enumerate(vpns):
                if v.uuid == keep:
                    lv.index = i
        sel = self.query_one("#vpn_found", Select)
        with self.prevent(Select.Changed):
            sel.set_options([(str(f).replace(str(paths.HOME), "~"), str(f)) for f in found])
        from .. import vpn
        ts = vpn.have_tailscale()
        self.query_one("#ts_row").display = ts
        self.query_one("#vpn_tail", Static).display = ts
        self.query_one("#vpn_tail", Static).update("Tailscale is installed:" if ts else "")

    @on(Select.Changed, "#vpn_found")
    def vpn_pick(self, ev: Select.Changed) -> None:
        ev.stop()
        if isinstance(ev.value, str):
            self.query_one("#vpn_path", Input).value = ev.value

    @work(thread=True, group="vpn-action")
    def vpn_task(self, what: str, uuid: str = "", path: str = "", user: str = "") -> None:
        from .. import vpn
        n = self.app.call_from_thread
        try:
            if what == "up":
                n(self.app.notify, "Connecting …")
                r = vpn.connect(uuid)
                msg, ok = vpn.message(r, "VPN connected")
                if not ok and vpn.needs_secret(msg):
                    n(self.app.spawn_term, f"nmcli --ask connection up uuid {uuid}")       # type: ignore[attr-defined]
                    msg, ok = "The VPN needs a password – a terminal asks for it", True
            elif what == "down":
                msg, ok = vpn.message(vpn.disconnect(uuid), "VPN disconnected")
            elif what == "del":
                msg, ok = vpn.message(vpn.delete(uuid), "VPN removed")
            elif what == "auto":
                cur = self.vpns.get(uuid)
                msg, ok = vpn.message(vpn.set_autoconnect(uuid, not (cur and cur.autoconnect)), "saved")
            else:
                msg, ok = vpn.import_file(Path(path).expanduser(), user)
        except ValueError as e:
            msg, ok = str(e), False
        n(self.app.notify, msg, severity="information" if ok else "error", timeout=10)
        self.refresh_data()

    def _vpn_uuid(self) -> str:
        item = self.query_one("#vpn_list", ListView).highlighted_child
        if not item or not item.name:
            self.app.notify("Select a VPN first", severity="warning")
            return ""
        return item.name

    @on(Switch.Changed, "#net_wifi")
    def wifi(self, ev: Switch.Changed) -> None:
        ev.stop()
        _sh("nmcli", "radio", "wifi", "on" if ev.value else "off")
        self.refresh_data()

    @work(thread=True, group="net-action")
    def connect(self, ssid: str, pw: str) -> None:
        self.app.call_from_thread(self.app.notify, f"Connecting to {ssid} …")
        cmd = ["nmcli", "device", "wifi", "connect", ssid] + (["password", pw] if pw else [])
        r = _sh(*cmd, timeout=45)
        out = (r.stdout + r.stderr).strip().splitlines()
        self.app.call_from_thread(self.app.notify, out[-1] if out else "done",
                                  severity="information" if r.returncode == 0 else "error", timeout=8)
        self.refresh_data()

    @on(Button.Pressed)
    def buttons(self, ev: Button.Pressed) -> None:
        ev.stop()
        bid = ev.button.id or ""
        if bid == "net_scan":
            self.refresh_data(rescan=True)
        elif bid == "net_connect":
            item = self.query_one("#net_list", ListView).highlighted_child
            if not item or not item.name:
                self.app.notify("Select a network first", severity="warning")
                return
            pw_in = self.query_one("#net_pw", Input)
            self.connect(item.name, pw_in.value)
            pw_in.value = ""
        elif bid == "net_disconnect":
            for line in _sh("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device").stdout.splitlines():
                f = _fields(line)
                if len(f) >= 3 and f[1] == "wifi" and f[2] == "connected":
                    _sh("nmcli", "device", "disconnect", f[0])
            self.refresh_data()
        elif bid in ("vpn_up", "vpn_down", "vpn_auto"):
            u = self._vpn_uuid()
            if u:
                self.vpn_task(bid[4:], u)
        elif bid == "vpn_del":
            u = self._vpn_uuid()
            if u:
                if self._del_armed == u:
                    self._del_armed = ""
                    ev.button.label = "Delete"
                    self.vpn_task("del", u)
                else:
                    self._del_armed = u
                    ev.button.label = "Really delete?"
                    self.set_timer(5, lambda b=ev.button: (setattr(self, "_del_armed", ""), setattr(b, "label", "Delete")))
        elif bid == "vpn_rescan":
            self.refresh_data()
        elif bid == "vpn_import":
            path = self.query_one("#vpn_path", Input).value.strip()
            if not path:
                self.app.notify("Pick a file above or type its path", severity="warning")
            else:
                self.vpn_task("import", path=path, user=self.query_one("#vpn_user", Input).value.strip())
        elif bid in ("ts_up", "ts_down", "ts_status"):
            self.app.spawn_term({"ts_up": "sudo tailscale up", "ts_down": "sudo tailscale down",   # type: ignore[attr-defined]
                                 "ts_status": "tailscale status"}[bid] + "; " + HOLD)
        elif bid == "net_nmtui":
            self.app.spawn_term("nmtui")             # type: ignore[attr-defined]
        elif bid == "net_editor":
            subprocess.Popen(["nm-connection-editor"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
