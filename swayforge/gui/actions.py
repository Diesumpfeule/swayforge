"""What the Studio pages show (page data) and what their buttons do (actions).

Everything here reuses the modules the terminal app uses. Slow or root-needing work runs in a
terminal window exactly like in the terminal app, so you always see the real command.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from .. import paths, settings
from ..system import have, run

HOLD = "stty sane 2>/dev/null; echo; read -t 180 -rp 'Done – press Enter to close (closes itself after 3 min) '"
_SPLIT = re.compile(r"(?<!\\):")


class Fail(Exception):
    """An action that can't be done – the message goes to the user as is."""


def _sh(*cmd: str, timeout: float = 15) -> subprocess.CompletedProcess:
    try:
        return run(list(cmd), timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def _nm_fields(line: str) -> list[str]:
    return [f.replace("\\:", ":") for f in _SPLIT.split(line)]


def _spawn(*cmd: str) -> None:
    subprocess.Popen(list(cmd), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _last(r: subprocess.CompletedProcess, ok: str = "Done") -> str:
    out = (r.stdout + r.stderr).strip().splitlines()
    return out[-1] if out else ok


def L() -> str:
    from .. import render
    return shlex.quote(render.LAUNCHER)


# ── Displays ─────────────────────────────────────────────────────────
def output_key(o: dict) -> str:
    ident = " ".join(x for x in (o.get("make"), o.get("model"), o.get("serial")) if x and x != "Unknown")
    return ident or o["name"]


def page_display(s: dict) -> dict:
    outs = []
    if os.environ.get("SWAYSOCK"):
        try:
            outs = json.loads(_sh("swaymsg", "-t", "get_outputs", "-r").stdout or "[]")
        except ValueError:
            outs = []
    res = []
    for o in outs:
        key = output_key(o)
        cfg = s["display"]["outputs"].get(key, {})
        modes = []
        for m in o.get("modes", []):
            ms = f"{m['width']}x{m['height']}@{m['refresh'] / 1000:.3f}Hz"
            if ms not in [v for _, v in modes]:
                modes.append((f"{m['width']}×{m['height']} @ {m['refresh'] / 1000:.0f} Hz", ms))
        modes.sort(key=lambda x: (-int(x[1].split("x")[0]), -float(x[1].split("@")[1][:-2])))
        cur = o.get("current_mode") or {}
        cur_s = f"{cur.get('width')}x{cur.get('height')}@{cur.get('refresh', 0) / 1000:.3f}Hz" if cur else ""
        mode = cfg.get("mode") or cur_s or (modes[0][1] if modes else "")
        if mode and mode not in [v for _, v in modes]:
            modes.insert(0, (mode, mode))
        rect = o.get("rect", {})
        res.append({"key": key, "name": o["name"], "make": o.get("make", ""), "model": o.get("model", ""),
                    "enabled": cfg.get("enabled", True), "mode": mode, "modes": modes,
                    "scale": cfg.get("scale", o.get("scale", 1.0)),
                    "pos": cfg.get("pos", f"{rect.get('x', 0)} {rect.get('y', 0)}"),
                    "rect": rect, "adaptive_sync": cfg.get("adaptive_sync", o.get("adaptive_sync_status") == "enabled")})
    return {"outputs": res, "primary": s["display"].get("primary") or (res[0]["key"] if res else ""),
            "allow_tearing": s["display"].get("allow_tearing", False), "in_sway": bool(os.environ.get("SWAYSOCK"))}


def set_outputs(s: dict, outputs: list, primary: str) -> None:
    clean = {}
    for o in outputs:
        try:
            scale = max(0.5, min(4.0, float(o.get("scale") or 1)))
        except (TypeError, ValueError):
            scale = 1.0
        pos = str(o.get("pos", "")).strip()
        if pos and not re.fullmatch(r"-?\d+ -?\d+", pos):
            raise Fail(f"Position “{pos}” must be two numbers like 2560 0")
        mode = str(o.get("mode", ""))
        if mode and not re.fullmatch(r"\d+x\d+@[\d.]+Hz", mode):
            raise Fail("Unknown resolution")
        clean[str(o["key"])] = {"enabled": bool(o.get("enabled", True)), "mode": mode, "scale": scale,
                                "pos": pos, "adaptive_sync": bool(o.get("adaptive_sync"))}
    s["display"]["outputs"] = clean
    s["display"]["primary"] = str(primary or "")


# ── Audio ────────────────────────────────────────────────────────────
def page_audio(s: dict) -> dict:
    data = {"have": have("pactl")}
    for kind in ("sink", "source"):
        r = _sh("pactl", "-f", "json", "list", f"{kind}s")
        try:
            devs = json.loads(r.stdout) if r.returncode == 0 else []
        except ValueError:
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
        data[kind] = {"devices": [{"name": d["name"], "label": d.get("description") or d["name"]} for d in devs],
                      "default": default, "volume": vol, "mute": bool(cur and cur.get("mute"))}
    return data


def audio(kind: str, what: str, value=None) -> str:
    if kind not in ("sink", "source"):
        raise Fail("unknown device kind")
    dev = f"@DEFAULT_{kind.upper()}@"
    if what == "default":
        _sh("pactl", f"set-default-{kind}", str(value))
    elif what == "volume":
        _sh("pactl", f"set-{kind}-volume", dev, f"{max(0, min(150, int(value)))}%")
    elif what == "mute":
        _sh("pactl", f"set-{kind}-mute", dev, "1" if value else "0")
    elif what == "pavucontrol":
        _spawn("pavucontrol")
    return ""


# ── Bluetooth ────────────────────────────────────────────────────────
MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$", re.I)


def page_bluetooth(s: dict) -> dict:
    if not have("bluetoothctl"):
        return {"have": False, "powered": False, "devices": []}
    powered = "Powered: yes" in _sh("bluetoothctl", "show").stdout
    devs = []
    for line in _sh("bluetoothctl", "devices").stdout.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device":
            info = _sh("bluetoothctl", "info", parts[1], timeout=5).stdout
            icon = re.search(r"Icon: (\S+)", info)
            devs.append({"mac": parts[1], "name": parts[2], "connected": "Connected: yes" in info,
                         "paired": "Paired: yes" in info, "icon": icon.group(1) if icon else ""})
    devs.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"].lower()))
    return {"have": True, "powered": powered, "devices": devs}


def bluetooth(verb: str, mac: str = "", on: bool = True) -> str:
    if verb == "power":
        return _last(_sh("bluetoothctl", "power", "on" if on else "off"))
    if verb == "scan":
        _sh("bluetoothctl", "--timeout", "10", "scan", "on", timeout=15)
        return "Scan finished"
    if verb == "blueman":
        _spawn("blueman-manager")
        return ""
    if verb not in ("connect", "disconnect", "pair", "remove") or not MAC.match(mac):
        raise Fail("Pick a device first")
    if verb == "pair":
        r = _sh("bluetoothctl", "pair", mac, timeout=30)
        _sh("bluetoothctl", "trust", mac)
        if r.returncode == 0:
            r = _sh("bluetoothctl", "connect", mac, timeout=20)
    else:
        r = _sh("bluetoothctl", verb, mac, timeout=20)
    if r.returncode != 0:
        raise Fail(_last(r, f"{verb} failed"))
    return _last(r)


# ── Network & VPN ────────────────────────────────────────────────────
def page_network(s: dict, rescan: bool = False) -> dict:
    from .. import vpn
    if not have("nmcli"):
        return {"have": False}
    active = []
    for line in _sh("nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active").stdout.splitlines():
        f = _nm_fields(line)
        if len(f) >= 3 and f[1] not in ("loopback", "bridge"):
            active.append({"name": f[0], "type": f[1].replace("802-11-wireless", "Wi-Fi").replace("802-3-ethernet", "Ethernet"),
                           "device": f[2]})
    for line in _sh("ip", "-4", "-br", "addr").stdout.splitlines():
        p = line.split()
        for a in active:
            if len(p) >= 3 and p[0] == a["device"]:
                a["ip"] = p[2]
    wifi_on = _sh("nmcli", "radio", "wifi").stdout.strip() == "enabled"
    nets = []
    if wifi_on:
        r = _sh("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                "--rescan", "yes" if rescan else "auto", timeout=25)
        seen = set()
        for line in r.stdout.splitlines():
            f = _nm_fields(line)
            if len(f) >= 4 and f[1] and f[1] not in seen:
                seen.add(f[1])
                nets.append({"inuse": f[0] == "*", "ssid": f[1], "signal": int(f[2] or 0),
                             "secure": bool(f[3] and f[3] != "--")})
        nets.sort(key=lambda n: (not n["inuse"], -n["signal"]))
    vpns = [{"uuid": v.uuid, "name": v.name, "kind": v.kind, "active": v.active, "auto": v.autoconnect}
            for v in vpn.list_vpns()]
    found = [str(f) for f in vpn.find_configs(paths.HOME)]
    return {"have": True, "active": active, "wifi": wifi_on, "networks": nets, "vpns": vpns, "found": found,
            "tailscale": vpn.have_tailscale()}


def network(state, verb: str, d: dict) -> str:
    from .. import vpn
    if verb == "wifi":
        _sh("nmcli", "radio", "wifi", "on" if d.get("on") else "off")
        return ""
    if verb == "connect":
        ssid = str(d.get("ssid", ""))
        if not ssid:
            raise Fail("Pick a network first")
        pw = str(d.get("password", ""))
        r = _sh("nmcli", "device", "wifi", "connect", ssid, *(["password", pw] if pw else []), timeout=45)
        if r.returncode != 0:
            raise Fail(_last(r, "Could not connect"))
        return _last(r, f"Connected to {ssid}")
    if verb == "disconnect":
        for line in _sh("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device").stdout.splitlines():
            f = _nm_fields(line)
            if len(f) >= 3 and f[1] == "wifi" and f[2] == "connected":
                _sh("nmcli", "device", "disconnect", f[0])
        return "Wi-Fi disconnected"
    if verb in ("nmtui",):
        term(state, "nmtui")
        return ""
    if verb == "editor":
        _spawn("nm-connection-editor")
        return ""
    uuid = str(d.get("uuid", ""))
    if verb in ("vpn_up", "vpn_down", "vpn_auto", "vpn_del") and not vpn.UUID_RE.match(uuid):
        raise Fail("Pick a VPN first")
    if verb == "vpn_up":
        msg, ok = vpn.message(vpn.connect(uuid), "VPN connected")
        if not ok and vpn.needs_secret(msg):
            term(state, f"nmcli --ask connection up uuid {shlex.quote(uuid)}")
            return "The VPN needs a password – a terminal asks for it"
    elif verb == "vpn_down":
        msg, ok = vpn.message(vpn.disconnect(uuid), "VPN disconnected")
    elif verb == "vpn_del":
        msg, ok = vpn.message(vpn.delete(uuid), "VPN removed")
    elif verb == "vpn_auto":
        cur = next((v for v in vpn.list_vpns() if v.uuid == uuid), None)
        msg, ok = vpn.message(vpn.set_autoconnect(uuid, not (cur and cur.autoconnect)), "Saved")
    elif verb == "vpn_import":
        try:
            msg, ok = vpn.import_file(Path(str(d.get("path", ""))).expanduser(), str(d.get("user", "")))
        except ValueError as e:
            msg, ok = str(e), False
    elif verb in ("ts_up", "ts_down", "ts_status"):
        term(state, {"ts_up": "sudo tailscale up", "ts_down": "sudo tailscale down",
                     "ts_status": "tailscale status"}[verb] + "; " + HOLD)
        return ""
    else:
        raise Fail("unknown action")
    if not ok:
        raise Fail(msg)
    return msg


# ── Power ────────────────────────────────────────────────────────────
def page_power(s: dict) -> dict:
    out = {"profiles": [], "profile": ""}
    if have("powerprofilesctl"):
        out["profile"] = _sh("powerprofilesctl", "get").stdout.strip()
        names = {"performance": "Performance", "balanced": "Balanced", "power-saver": "Power saver"}
        out["profiles"] = [[names.get(a, a), a] for a in
                           (l.strip().rstrip(":").lstrip("* ").strip()
                            for l in _sh("powerprofilesctl", "list").stdout.splitlines() if l.strip().endswith(":"))]
    return out


def power_profile(p: str) -> str:
    if not re.fullmatch(r"[a-z-]+", p):
        raise Fail("unknown profile")
    r = _sh("powerprofilesctl", "set", p)
    if r.returncode != 0:
        raise Fail(_last(r))
    return f"Power profile: {p}"


# ── Boot & login ─────────────────────────────────────────────────────
def page_boot(s: dict) -> dict:
    from .. import boot, render
    ctx = render.make_ctx(s)
    greeter = _sh("systemctl", "is-enabled", "greetd").stdout.strip() if have("systemctl") else ""
    return {"styles": [["auto", "Theme's style", ""]] + [[k, label, desc] for k, (label, desc) in boot.STYLES.items()],
            "current": boot.style_for(ctx), "previews": boot.PREVIEWS, "greeter": greeter == "enabled",
            "banner": boot.banner_text(ctx)}


# ── Security ─────────────────────────────────────────────────────────
def page_security(s: dict) -> dict:
    from .. import security
    inst = security.installed()
    return {"tools": [{"id": t, "label": label, "ok": inst[t]} for t, label in security.TOOLS.items()],
            "signature_age": security.signature_age_days(), "clam": inst["clamscan"],
            "drives": security.removable_drives(),
            "reports": [{"path": str(r), "text": security.describe(r, x)} for r, x in security.reports()]}


def security_action(state, verb: str, d: dict) -> str:
    from .. import security
    nq = "" if state.s["security"]["quarantine"] else " --no-quarantine"
    if verb in ("dl", "home"):
        term(state, f"{L()} scan {'downloads' if verb == 'dl' else 'home'}{nq}; {HOLD}")
    elif verb == "drive":
        mounts_ok = {x["mount"] for x in security.removable_drives()}
        if d.get("mount") not in mounts_ok:
            raise Fail("Pick a USB drive first")
        term(state, f"{L()} scan {shlex.quote(d['mount'])}{nq}; {HOLD}")
    elif verb == "path":
        p = os.path.expanduser(str(d.get("path", "")).strip())
        if not p or not Path(p).exists():
            raise Fail("That path doesn't exist")
        term(state, f"{L()} scan {shlex.quote(p)}{nq}; {HOLD}")
    elif verb == "fresh":
        term(state, f"sudo freshclam; {HOLD}")
    elif verb == "install":
        term(state, "sudo dnf install -y clamav clamav-freshclam rkhunter chkrootkit lynis usbutils && "
                    "sudo freshclam && sudo systemctl enable --now clamav-freshclam.service; "
                    f"sudo rkhunter --propupd; {HOLD}")
    elif verb == "rootkit":
        term(state, f"{L()} audit rootkit; {HOLD}")
    elif verb == "audit":
        term(state, f"{L()} audit system; {HOLD}")
    elif verb == "quarantine":
        security.QUARANTINE.mkdir(parents=True, exist_ok=True)
        _spawn("xdg-open", str(security.QUARANTINE))
    elif verb == "overview":
        kind = str(d.get("kind", ""))
        if kind not in ("usb", "drives", "ports", "autostart"):
            raise Fail("unknown overview")
        return security.overview(kind)
    elif verb == "report":
        p = Path(str(d.get("path", "")))
        if p.parent != security.REPORT_DIR or not p.is_file():
            raise Fail("Report not found")
        return p.read_text(errors="replace")[-20000:]
    else:
        raise Fail("unknown action")
    return ""


# ── Apps ─────────────────────────────────────────────────────────────
def page_apps(s: dict) -> dict:
    from .. import apps, catalog
    cat = catalog.load()
    labels = {g.id: g.label for g in cat.groups} | {apps.OTHER: "Other (yours)"}
    entries = apps.inventory(cat)
    groups = []
    for gid, glabel in labels.items():
        rows = [e for e in entries if e.group == gid]
        if rows:
            groups.append({"id": gid, "label": glabel, "size": sum(e.size for e in rows), "apps": [
                {"id": e.id, "label": e.label, "source": e.source, "size": e.size, "human": apps.human(e.size),
                 "locked": e.locked, "packages": e.rpms + e.flatpaks}
                for e in sorted(rows, key=lambda e: (-e.size if gid == apps.OTHER else 0, e.label.lower()))]})
    return {"groups": groups, "total": apps.human(sum(e.size for e in entries)), "count": len(entries)}


def apps_remove(state, app_id: str) -> str:
    from .. import apps, catalog
    e = next((x for x in apps.inventory(catalog.load()) if x.id == app_id), None)
    if not e:
        raise Fail("App not found – refresh the list")
    if e.locked:
        raise Fail(f"{e.label} is part of the swayforge desktop and can't be removed here")
    term(state, f"{e.remove_cmd()}; {HOLD}")
    return f"Uninstalling {e.label} in a terminal"


def apps_search(state, term_: str) -> dict:
    from .. import apps, finder
    if len(term_.strip()) < 2:
        raise Fail("Type at least two letters")
    res = finder.search_all(term_.strip())
    finder.mark_installed(res.hits, set(apps.rpm_db()), set(apps.flatpak_db()))
    state.hits = list(res.hits)                 # installing refers to these by number
    return {"hits": [{"n": i, "name": h.name, "source": h.source, "summary": h.summary, "cmd": h.cmd,
                      "installed": h.installed, "note": h.note} for i, h in enumerate(res.hits)],
            "errors": res.errors}


def apps_install(state, n: int) -> str:
    """Only a command the finder produced in this session may run – the page sends its number."""
    hits = getattr(state, "hits", [])
    if not isinstance(n, int) or not 0 <= n < len(hits):
        raise Fail("Search again – that result is gone")
    h = hits[n]
    term(state, f"{h.cmd}; {HOLD}")
    return f"Installing {h.name} in a terminal"


# ── Cleanup & drives ─────────────────────────────────────────────────
def page_cleanup(s: dict) -> dict:
    from .. import apps, cleanup
    items = cleanup.items(measure=True)
    return {"items": [{"id": i.id, "label": i.label, "desc": i.desc, "cmd": i.cmd, "size": i.size,
                       "human": apps.human(i.size) if i.size >= 0 else "?", "note": i.note,
                       "default": i.id != "coredumps" and i.size != 0} for i in items],
            "total": apps.human(sum(i.size for i in items if i.size > 0)),
            "drives": [dict(d, label=cleanup.drive_label(d), human=apps.human(d["size"])) for d in cleanup.wipeable_drives()],
            "modes": cleanup.MODE_SHORT, "fs": cleanup.FS_SHORT,
            "have": {"ncdu": have("ncdu"), "bleachbit": have("bleachbit"), "nwipe": have("nwipe")}}


def cleanup_run(state, ids: list[str]) -> str:
    from .. import cleanup
    chosen = [i for i in cleanup.items(measure=False) if i.id in set(ids)]
    if not chosen:
        raise Fail("Nothing ticked")
    script = "; ".join(f"echo; echo '── {it.label}: {it.cmd.replace(chr(39), '')}'; {it.cmd}" for it in chosen)
    term(state, f"{script}; {HOLD}")
    return "Cleaning in a terminal – measure again afterwards"


def wipe(state, d: dict) -> str:
    from .. import cleanup
    drive = next((x for x in cleanup.wipeable_drives() if x["name"] == d.get("name")), None)
    if not drive:
        raise Fail("That drive is gone – look again")
    if str(d.get("confirm", "")).strip() != drive["name"]:
        raise Fail(f"Type {drive['name']} to confirm")
    mode, fs = str(d.get("mode", "quick")), str(d.get("fs", "exfat"))
    if mode not in cleanup.MODE_SHORT or fs not in cleanup.FS_SHORT:
        raise Fail("unknown option")
    label = re.sub(r"[^A-Za-z0-9 _-]", "", str(d.get("label", "USB")))[:11] or "USB"
    term(state, f"{L()} wipe {shlex.quote(drive['name'])} --mode {mode} --fs {fs} --label {shlex.quote(label)} "
                f"--size {drive['size']} --confirm {shlex.quote(drive['name'])}; {HOLD}")
    return f"Wiping {drive['name']} in a terminal"


# ── Mounts ───────────────────────────────────────────────────────────
def page_mounts(s: dict) -> dict:
    from .. import mounts
    cands = mounts.candidates()
    return {"candidates": [dict(c, label=mounts.describe(c), suggest=mounts.default_name(c),
                                line=mounts.fstab_line(c, mounts.default_name(c), os.getuid(), os.getgid()))
                           for c in cands],
            "entries": mounts.entries()}


def mounts_action(state, verb: str, d: dict) -> str:
    from .. import mounts
    if verb == "add":
        c = next((x for x in mounts.candidates() if x["name"] == d.get("name")), None)
        n = mounts.clean_name(str(d.get("as", "")))
        if not c or not n:
            raise Fail("Pick a drive and give it a name")
        term(state, f"{L()} mount add {shlex.quote(c['name'])} {shlex.quote(n)}; {HOLD}")
        return f"Mounting at /mnt/{n} in a terminal"
    target = str(d.get("target", ""))
    if target not in {e["target"] for e in mounts.entries()}:
        raise Fail("Unknown mount")
    if verb == "remove":
        term(state, f"{L()} mount remove {shlex.quote(target)}; {HOLD}")
        return "Removing in a terminal – the data on the drive stays"
    if verb == "open":
        _spawn("xdg-open", target)
        return ""
    raise Fail("unknown action")


# ── System & files ───────────────────────────────────────────────────
def page_system(s: dict) -> dict:
    from .. import render
    backups = sorted((d for d in paths.BACKUP_DIR.iterdir() if d.is_dir()), reverse=True) \
        if paths.BACKUP_DIR.is_dir() else []
    return {"files": [{"key": k, "label": label, "path": str(p).replace(str(paths.HOME), "~"), "exists": p.exists()}
                      for k, (label, p) in render.CONFIG_FILES.items()],
            "backups": [d.name for d in backups[:40]],
            "export": str(paths.HOME / "swayforge-backup.tar.gz")}


def open_file(state, key: str) -> str:
    from .. import render
    if key not in render.CONFIG_FILES:
        raise Fail("unknown file")
    p = render.CONFIG_FILES[key][1]
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    editor = state.s["general"]["editor"]
    if editor.split()[0] in ("code", "codium"):
        subprocess.Popen(shlex.split(editor.replace(" --wait", "")) + [str(p)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        term(state, f"{editor} {shlex.quote(str(p))}")
    return f"Opened {str(p).replace(str(paths.HOME), '~')} – apply again after saving there"


def system_action(state, verb: str, d: dict) -> str:
    if verb == "update":
        term(state, f"sudo dnf upgrade --refresh; flatpak update 2>/dev/null; {HOLD}")
        return "System update runs in a terminal"
    if verb == "screenshare":
        term(state, f"{L()} screenshare; {HOLD}")
        return "Checking screen sharing in a terminal"
    if verb == "firmware":
        term(state, f"fwupdmgr refresh; fwupdmgr get-updates; {HOLD}")
        return ""
    if verb == "installer":
        term(state, f"{L()} install")
        return "The installer opens in a terminal"
    if verb == "import":
        from ..importer import import_sway_config
        try:
            return import_sway_config(Path(os.path.expanduser(str(d.get("path", "")))))
        except (OSError, ValueError) as e:
            raise Fail(str(e)) from None
    if verb == "export":
        from .. import tools
        dest = os.path.expanduser(str(d.get("path", "")).strip()) or str(paths.HOME / "swayforge-backup.tar.gz")
        settings.save(state.s)
        if tools.export(dest) != 0:
            raise Fail("Export failed")
        return f"Backup written to {dest.replace(str(paths.HOME), '~')}"
    name = str(d.get("name", ""))
    b = paths.BACKUP_DIR / name
    if verb in ("restore", "open_backup"):
        if not re.fullmatch(r"[\w.-]+", name) or not b.is_dir():
            raise Fail("Pick a backup first")
        if verb == "open_backup":
            _spawn("xdg-open", str(b))
            return ""
        n = 0
        for f in b.rglob("*"):
            if f.is_file():
                target = paths.HOME / f.relative_to(b)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
                n += 1
        if os.environ.get("SWAYSOCK"):
            run(["swaymsg", "reload"])
        return f"{n} files restored. Applying in swayforge writes the generated files again."
    raise Fail("unknown action")


# ── About & updates ──────────────────────────────────────────────────
def page_about(s: dict) -> dict:
    from .. import crash, update
    apps_ = []
    for n in update.APPS:
        info, rem, verdict = update.status(n)
        apps_.append({"name": n, "version": info.get("version", ""), "commit": info.get("commit", "")[:7],
                      "date": info.get("date", ""), "verdict": verdict, "remote": rem[:7], "url": update.url(n)})
    crashes = []
    for r in crash.recent():
        last = (r.read_text(errors="replace").strip().splitlines() or ["?"])[-1][:120]
        crashes.append({"name": r.name, "last": last})
    return {"apps": apps_, "crashes": crashes}


def about_action(state, verb: str) -> str:
    from .. import crash, update
    if verb == "update":
        update.DONE_MARK.unlink(missing_ok=True)
        term(state, update.terminal_command(HOLD))
        return "Updating in a terminal – restart the app when it says it's done"
    if verb in ("gh_swayforge", "gh_wolfforge"):
        _spawn("xdg-open", update.url(verb[3:]))
        return ""
    if verb == "crash_dir":
        crash.CRASH_DIR.mkdir(parents=True, exist_ok=True)
        _spawn("xdg-open", str(crash.CRASH_DIR))
        return ""
    raise Fail("unknown action")


# ── Games ────────────────────────────────────────────────────────────
def page_games(s: dict) -> dict:
    from .. import gamecfg
    out = {"cs2": {"installed": gamecfg.CS2_DIR.is_dir(), "values": gamecfg.cs2_values(),
                   "fields": {k: list(v) for k, v in gamecfg.CS2_FIELDS.items()}},
           "steam": {"installed": gamecfg.STEAMTUNE.is_file(), "libraries": []}}
    if gamecfg.STEAMTUNE.is_file():
        try:
            st = gamecfg.steamtune_module()
            root = st.root()
            lims = st.load_cfg().get("limits", {})
            for i, lib in enumerate(st.libraries(root) if root else []):
                try:
                    size = sum(b for _, b, _ in st.apps_in(lib, root))
                    free = st.shutil.disk_usage(lib).free
                    out["steam"]["libraries"].append({"n": i, "path": str(lib), "cache": st.human(size),
                                                      "free": st.human(free), "limit": lims.get(str(i), "")})
                except OSError:
                    out["steam"]["libraries"].append({"n": i, "path": str(lib), "cache": "–", "free": "not mounted"})
            out["steam"]["window"] = st.window(root) if root else ""
        except Exception as e:                  # noqa: BLE001 – steamtune is optional
            out["steam"]["error"] = str(e)
    return out


def games_action(state, verb: str, d: dict) -> str:
    from .. import gamecfg
    if verb == "cs2_save":
        vals = {k: str(d.get("values", {}).get(k, "")).strip() for k in gamecfg.CS2_FIELDS}
        for k, v in vals.items():
            if v and not re.fullmatch(r"[\w.,-]{1,12}", v):
                raise Fail(f"“{v}” is not a valid value for {gamecfg.CS2_FIELDS[k][0]}")
        gamecfg.cs2_save(vals, bool(d.get("no_original")))
        return "Saved – takes effect the next time CS2 starts"
    if verb == "cs2_test":
        term(state, f"{shlex.quote(str(gamecfg.CS2_BIN))} --terminal --debug; {HOLD}")
        return ""
    if verb == "cs2_move":
        term(state, f"{shlex.quote(str(gamecfg.CS2_BIN))} --move; {HOLD}")
        return "Drag the overlay over the chat, Esc saves"
    if verb == "steamtune":
        term(state, f"{shlex.quote(str(gamecfg.STEAMTUNE_BIN))}; {HOLD}")
        return ""
    if verb == "steam_limit":
        n, v = int(d.get("n", -1)), str(d.get("limit", "")).strip() or "off"
        if n < 0 or not re.fullmatch(r"off|\d+(\.\d+)?[GMgm]?", v):
            raise Fail("Limit like 20G, or empty for none")
        r = _sh(str(gamecfg.STEAMTUNE_BIN), "limit", str(n), v)
        if r.returncode != 0:
            raise Fail(_last(r))
        return _last(r, "Saved")
    if verb == "steam_window":
        v = str(d.get("window", "")).strip() or "off"
        if not re.fullmatch(r"off|\d{1,2}(:\d\d)?-\d{1,2}(:\d\d)?", v):
            raise Fail("Window like 2-6 (hours), or empty for none")
        r = _sh(str(gamecfg.STEAMTUNE_BIN), "window", v)
        if r.returncode != 0:
            raise Fail(_last(r))
        return _last(r, "Saved")
    raise Fail("unknown action")


# ── Sounds ───────────────────────────────────────────────────────────
def sound_test(event: str = "") -> str:
    _spawn(*shlex.split(L()), "sound", *(["play", event] if event else ["test"]))
    return ""


# ── Theme editor & theme from wallpaper ──────────────────────────────
def theme_save(state, label: str, colors: dict, dark: bool | None = None) -> dict:
    from .. import themes
    cols = {}
    for k in themes.COLOR_KEYS:
        v = str(colors.get(k, "")).strip().lower()
        if not themes.HEX.match(v):
            raise Fail(f"{themes.COLOR_LABELS.get(k, k)}: “{v}” is not a colour like #1e1e2e")
        cols[k] = v
    base = themes.get(state.s["theme"]["name"])
    name = label.strip() or f"{base.label.split(' (')[0]} custom"
    t = themes.save_custom(name, base, cols)
    state.s["theme"]["name"] = t.id
    state.s["theme"]["accent"] = ""
    return {"id": t.id, "label": t.label}


def theme_from_wallpaper(state, mode: str) -> dict:
    from .. import livewall, themes, wallpalette
    img = state.s["theme"]["wallpaper"]
    if not img or not Path(img).is_file():
        raise Fail("Pick a picture on the Wallpapers page first")
    if mode not in ("auto", "dark", "light"):
        raise Fail("unknown mode")
    try:
        t = wallpalette.make_theme(livewall.thumb(img) if livewall.is_video(img) else img, mode)
    except ImportError:
        raise Fail("Needs Pillow: sudo dnf install python3-pillow") from None
    except OSError as e:
        raise Fail(f"Can't read that image: {e}") from None
    old = themes.all_themes().get(state.s["theme"]["name"])
    themes.apply_style(state.s, t, old)
    state.s["theme"]["name"] = t.id
    state.s["theme"]["accent"] = ""
    return {"id": t.id, "label": t.label, "dark": t.dark}


def live_wallpaper(state, style: str) -> str:
    from .. import livewall
    if style not in livewall.STYLES:
        raise Fail("unknown style")
    p = livewall.generate(style, state.s)
    state.s["theme"]["wallpaper"] = str(p)
    state.walls = None
    return f"Made {p.name} – apply to use it"


def wallpacks_page() -> dict:
    from .. import wallpacks
    return {"packs": [{"id": p.id, "name": p.name, "blurb": p.blurb, "license": p.license, "categories": [
        {"key": wallpacks.key(p.id, c.id), "id": c.id, "files": c.files, "mb": c.mb,
         "installed": wallpacks.is_installed(p, c)} for c in p.categories]} for p in wallpacks.load()]}


def wallpacks_download(state, keys: list[str]) -> str:
    from .. import wallpacks
    ok = {wallpacks.key(p.id, c.id) for p in wallpacks.load() for c in p.categories}
    keys = [k for k in keys if k in ok]
    if not keys:
        raise Fail("Tick at least one collection")
    term(state, wallpacks.script(keys) + f"; {HOLD}")
    state.walls = None
    return f"Downloading {len(keys)} collection(s) – about {wallpacks.total_mb(keys)} MB – in a terminal"


# ── Desktop shell (Noctalia) ─────────────────────────────────────────
def shell_toggle(state) -> str:
    s = state.s
    if not (have("noctalia") or have("noctalia-shell")) and s["general"].get("shell") != "noctalia":
        raise Fail("Noctalia is not installed. Run: sudo dnf install noctalia")
    s["general"]["shell"] = "swayforge" if s["general"].get("shell") == "noctalia" else "noctalia"
    if s["general"]["shell"] == "swayforge":
        for pat in (["-x", "noctalia"], ["-x", "noctalia-shell"], ["-f", "^quickshell.*noctalia"]):
            run(["pkill", *pat])
    return s["general"]["shell"]


# ── terminal helper ──────────────────────────────────────────────────
def term(state, cmd: str) -> None:
    from .. import render
    full = render.terminal_cmd(state.s, "swayforge-task", f"sh -c {shlex.quote(cmd)}")
    subprocess.Popen(shlex.split(full), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
