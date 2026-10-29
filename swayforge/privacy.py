"""Privacy guard: which app may reach what – and what is being used right now.

Two kinds of apps live on Fedora:
- Flatpak apps run in a sandbox. Their permissions are written down, so we can list them exactly
  (camera, microphone, screen, network, your files …) and take single ones away again.
- RPM apps (installed with dnf) have no sandbox. They can do everything you can: camera,
  microphone, network and every file in your home folder. That's normal on Linux – the list
  just makes it visible.
On top of that the "right now" view shows who is actually using the camera, the microphone,
screen sharing and the network at this moment (from /proc, PipeWire and `ss`, no root needed).
"""
from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
from pathlib import Path

from .system import have

# what each permission means, in plain words (shown in the apps)
PERMS = {
    "camera": "Camera",
    "microphone": "Microphone (and sound)",
    "screen": "Screen / other windows",
    "location": "Location",
    "network": "Network & internet",
    "home": "Your whole home folder",
    "system_files": "System files",
    "files": "Some folders",
    "devices": "All devices (USB, game pads, cameras …)",
    "bus": "Talk to other programs freely",
    "escape": "Can leave its sandbox",
    "background": "Runs in the background",
    "autostart": "Starts with your session",
    "notifications": "Notifications",
}
RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ── Flatpak ──────────────────────────────────────────────────────────
def parse_flatpak_permissions(text: str) -> dict[str, list[str]]:
    """`flatpak info --show-permissions` (key file) → {"shared": [...], "sockets": [...], ...}."""
    cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    cp.optionxform = str  # type: ignore[assignment]
    try:
        cp.read_string(text)
    except configparser.Error:
        return {}
    out: dict[str, list[str]] = {}
    if cp.has_section("Context"):
        for k, v in cp.items("Context"):
            out[k] = [x for x in v.split(";") if x]
    for sec in ("Session Bus Policy", "System Bus Policy"):
        if cp.has_section(sec):
            out[sec] = [f"{k}={v}" for k, v in cp.items(sec)]
    return out


def judge_flatpak(perm: dict[str, list[str]], portal: dict[str, str] | None = None) -> dict:
    """Permission sets → {"perms": {key: detail}, "risk": high|medium|low}."""
    portal = portal or {}
    shared, sockets = set(perm.get("shared", [])), set(perm.get("sockets", []))
    devices, fs = set(perm.get("devices", [])), perm.get("filesystems", [])
    bus = perm.get("Session Bus Policy", []) + perm.get("System Bus Policy", [])
    p: dict[str, str] = {}
    fs_clean = [f for f in fs if not f.startswith("!")]
    if "network" in shared:
        p["network"] = "full internet access"
    if "all" in devices:
        p["devices"] = "every device file"
        p["camera"] = "through device access"
    elif "camera" in devices or portal.get("camera") == "yes":
        p["camera"] = "allowed" + (" (you said yes once)" if portal.get("camera") == "yes" else "")
    if "pulseaudio" in sockets:
        p["microphone"] = "via the sound server (can record)"
    if "x11" in sockets and "fallback-x11" not in sockets:
        p["screen"] = "X11: can see and read other X11 windows"
    if portal.get("screenshot") == "yes":
        p["screen"] = (p.get("screen", "") + "; " if p.get("screen") else "") + "screenshots without asking"
    if portal.get("location") == "yes":
        p["location"] = "allowed"
    if portal.get("background") == "yes":
        p["background"] = "allowed"
    if portal.get("notifications") == "yes":
        p["notifications"] = "allowed"
    base = {f.split(":")[0] for f in fs_clean}
    if base & {"host", "host-os", "host-etc", "/"}:
        p["system_files"] = ", ".join(sorted(base & {"host", "host-os", "host-etc", "/"}))
    if base & {"home", "~", "host"}:
        p["home"] = "read" + ("" if all(f.endswith(":ro") for f in fs_clean if f.split(":")[0] in ("home", "~", "host"))
                              else " + write")
    rest = sorted(b for b in base if b not in ("host", "host-os", "host-etc", "/", "home", "~"))
    if rest:
        p["files"] = ", ".join(rest[:6]) + (" …" if len(rest) > 6 else "")
    if "session-bus" in sockets or "system-bus" in sockets:
        p["bus"] = "full " + " + ".join(s for s in ("session-bus", "system-bus") if s in sockets)
    if any(b.startswith(("org.freedesktop.Flatpak=", "org.freedesktop.Flatpak.Development=")) and
           b.endswith("talk") for b in bus):
        p["escape"] = "may start programs outside the sandbox"
    high = {"escape", "system_files", "bus", "devices"} & set(p) or ("home" in p and "write" in p["home"])
    medium = {"home", "screen", "camera", "microphone", "location"} & set(p)
    return {"perms": p, "risk": "high" if high else "medium" if medium else "low"}


def portal_permissions(text: str | None = None) -> dict[str, dict[str, str]]:
    """Answers you gave in portal dialogs: {app: {"camera": "yes", "location": "yes", ...}}."""
    txt = _run(["flatpak", "permission-show"]) if text is None else text
    keys = {("devices", "camera"): "camera", ("devices", "microphone"): "microphone",
            ("location", "location"): "location", ("background", "background"): "background",
            ("notifications", "notification"): "notifications", ("screenshot", "screenshot"): "screenshot"}
    out: dict[str, dict[str, str]] = {}
    for line in txt.splitlines():
        cols = line.split("\t") if "\t" in line else line.split()
        if len(cols) >= 4 and (cols[0], cols[1]) in keys and "." in cols[2]:
            out.setdefault(cols[2], {})[keys[(cols[0], cols[1])]] = "yes" if "yes" in cols[3].lower() else cols[3].lower()
    return out


def flatpak_apps() -> list[dict]:
    if not have("flatpak"):
        return []
    portal = portal_permissions()
    apps = []
    for line in _run(["flatpak", "list", "--app", "--columns=application,name"]).splitlines():
        cols = line.split("\t")
        if not cols or not cols[0].strip() or cols[0] == "Application ID":
            continue
        app = cols[0].strip()
        perm = parse_flatpak_permissions(_run(["flatpak", "info", "--show-permissions", app]))
        j = judge_flatpak(perm, portal.get(app, {}))
        overridden = bool(_run(["flatpak", "override", "--user", "--show", app]).strip())
        apps.append({"id": app, "name": (cols[1].strip() if len(cols) > 1 else "") or app, "kind": "flatpak",
                     "sandboxed": True, "overridden": overridden, **j})
    return apps


# ── RPM / native apps ────────────────────────────────────────────────
def native_apps(dirs: list[Path] | None = None) -> list[dict]:
    """Desktop apps outside Flatpak – they have no sandbox."""
    dirs = dirs or [Path("/usr/share/applications"), Path.home() / ".local/share/applications"]
    seen, out = set(), []
    for d in dirs:
        for f in sorted(d.glob("*.desktop")) if d.is_dir() else []:
            if f.name in seen:
                continue
            seen.add(f.name)
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
            except (configparser.Error, UnicodeDecodeError, OSError):
                continue
            if not cp.has_section("Desktop Entry"):
                continue
            e = cp["Desktop Entry"]
            if e.get("NoDisplay", "").lower() == "true" or e.get("Hidden", "").lower() == "true" \
                    or e.get("Type", "Application") != "Application" or "flatpak" in e.get("Exec", "") \
                    or "swayforge" in f.name:
                continue
            cats = e.get("Categories", "")
            if "Settings" in cats.split(";") and "Utility" not in cats:
                continue
            out.append({"id": f.stem, "name": e.get("Name", f.stem), "kind": "rpm", "sandboxed": False,
                        "exec": e.get("Exec", "").split()[0] if e.get("Exec") else "",
                        "perms": {k: "no sandbox" for k in ("camera", "microphone", "network", "home")},
                        "risk": "medium"})
    return sorted(out, key=lambda a: a["name"].lower())


def autostart(dirs: list[Path] | None = None) -> list[str]:
    dirs = dirs or [Path.home() / ".config/autostart", Path("/etc/xdg/autostart")]
    out = []
    for d in dirs:
        for f in sorted(d.glob("*.desktop")) if d.is_dir() else []:
            txt = f.read_text(errors="replace")
            if re.search(r"^Hidden\s*=\s*true", txt, re.M | re.I):
                continue
            m = re.search(r"^Name\s*=\s*(.+)$", txt, re.M)
            out.append(m.group(1).strip() if m else f.stem)
    return sorted(set(out))


# ── Right now ────────────────────────────────────────────────────────
def _comm(pid: str, proc: str = "/proc") -> str:
    try:
        return Path(proc, pid, "comm").read_text().strip()
    except OSError:
        return f"pid {pid}"


def camera_users(proc: str = "/proc") -> list[str]:
    """Programs that have a camera (/dev/video*) open right now."""
    users = set()
    for pdir in Path(proc).iterdir() if Path(proc).is_dir() else []:
        if not pdir.name.isdigit():
            continue
        try:
            for fd in (pdir / "fd").iterdir():
                if os.readlink(fd).startswith("/dev/video"):
                    users.add(_comm(pdir.name, proc))
                    break
        except OSError:
            continue
    return sorted(users)


def mic_users() -> list[str]:
    """Programs recording from a microphone right now (PipeWire/Pulse source outputs)."""
    out = _run(["pactl", "-f", "json", "list", "source-outputs"])
    try:
        data = json.loads(out) if out else []
    except ValueError:
        return []
    names = set()
    for so in data:
        pr = so.get("properties", {})
        if pr.get("stream.monitor") == "true" or "peak detect" in pr.get("media.name", "").lower():
            continue
        names.add(pr.get("application.name") or pr.get("application.process.binary") or "?")
    return sorted(names)


def screen_users() -> list[str]:
    """Screen sharing running right now (portal screencast streams in PipeWire)."""
    out = _run(["pw-dump"], timeout=10)
    try:
        nodes = json.loads(out) if out else []
    except ValueError:
        return []
    found = []
    for n in nodes:
        props = (n.get("info") or {}).get("props") or {}
        if props.get("media.class") == "Video/Source" and "xdpw" in (props.get("node.name", "") + props.get("media.name", "")):
            found.append("screen sharing is on")
    return found


def parse_ss(text: str) -> dict[str, dict]:
    """`ss -tunpH` → {program: {"connections": n, "peers": [...]}} (only your own programs show)."""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[1] not in ("ESTAB", "ESTABLISHED", "SYN-SENT", "UNCONN"):
            continue
        if parts[1] == "UNCONN":
            continue
        m = re.search(r'users:\(\("([^"]+)"', line)
        prog = m.group(1) if m else "(system / other user)"
        peer = parts[5]
        host = peer.rsplit(":", 1)[0].strip("[]")
        if host.startswith(("127.", "::1", "::ffff:127.")):
            continue
        e = out.setdefault(prog, {"connections": 0, "peers": []})
        e["connections"] += 1
        if host not in e["peers"] and len(e["peers"]) < 8:
            e["peers"].append(host)
    return out


def parse_listening(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[4]
        host, _, port = local.rpartition(":")
        if host.strip("[]").startswith(("127.", "::1")) or host.strip("[]") in ("localhost",):
            continue
        m = re.search(r'users:\(\("([^"]+)"', line)
        out.append({"proto": parts[0], "port": port, "where": host or "*", "program": m.group(1) if m else "(system)"})
    return out


def right_now() -> dict:
    net = parse_ss(_run(["ss", "-tunpH"])) if have("ss") else {}
    listen = parse_listening(_run(["ss", "-tulnpH"])) if have("ss") else []
    return {"camera": camera_users(), "microphone": mic_users() if have("pactl") else [],
            "screen": screen_users() if have("pw-dump") else [], "network": net, "listening": listen}


def scan() -> dict:
    fl = flatpak_apps()
    fl.sort(key=lambda a: (RISK_ORDER[a["risk"]], a["name"].lower()))
    return {"flatpak": fl, "native": native_apps(), "autostart": autostart(), "now": right_now()}


# ── Taking permissions away (Flatpak only – RPM apps have nothing to take) ──
REVOKE = {
    "network": (["--unshare=network"], "no internet"),
    "camera": (["--nodevice=all", "--nodevice=camera"], "no camera / devices"),
    "microphone": (["--nosocket=pulseaudio"], "no microphone – this also mutes the app"),
    "home": (["--nofilesystem=home", "--nofilesystem=host"], "no access to your files"),
    "screen": (["--nosocket=x11"], "no X11 (Wayland only)"),
    "bus": (["--nosocket=session-bus", "--nosocket=system-bus"], "no free bus access"),
}


def revoke_cmd(app: str, what: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", app) or what not in REVOKE and what != "reset":
        raise ValueError("bad app or permission")
    if what == "reset":
        return ["flatpak", "override", "--user", "--reset", app]
    return ["flatpak", "override", "--user", *REVOKE[what][0], app]


def revoke(app: str, what: str) -> bool:
    ok = subprocess.run(revoke_cmd(app, what), capture_output=True).returncode == 0
    if what == "reset":
        subprocess.run(["flatpak", "permission-reset", app], capture_output=True)
    return ok


# ── Terminal report ──────────────────────────────────────────────────
def report(data: dict | None = None) -> str:
    d = data or scan()
    now = d["now"]
    L = ["RIGHT NOW"]
    L.append(f"  Camera       : {', '.join(now['camera']) or 'nobody'}")
    L.append(f"  Microphone   : {', '.join(now['microphone']) or 'nobody'}")
    L.append(f"  Screen share : {'ON' if now['screen'] else 'off'}")
    if now["network"]:
        L.append("  Internet     : " + ", ".join(f"{p} ({v['connections']})" for p, v in
                                              sorted(now["network"].items(), key=lambda x: -x[1]["connections"])[:10]))
    if now["listening"]:
        L.append("  Open ports   : " + ", ".join(f"{x['program']} {x['proto']}/{x['port']}" for x in now["listening"][:10]))
    L.append("")
    L.append(f"FLATPAK APPS (sandboxed) – {len(d['flatpak'])}")
    for a in d["flatpak"]:
        mark = {"high": "!!", "medium": " !", "low": "  "}[a["risk"]]
        L.append(f" {mark} {a['name']}  [{a['id']}]{'  (changed by you)' if a['overridden'] else ''}")
        for k, v in a["perms"].items():
            L.append(f"      {PERMS[k]:<34} {v}")
    L.append("")
    L.append(f"RPM APPS (no sandbox – camera, microphone, network and all your files) – {len(d['native'])}")
    L.append("  " + ", ".join(a["name"] for a in d["native"]))
    if d["autostart"]:
        L.append("")
        L.append("STARTS WITH YOUR SESSION: " + ", ".join(d["autostart"]))
    L.append("")
    L.append("Take a permission away (Flatpak):  swayforge privacy revoke APP network|camera|microphone|home|screen|bus|reset")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    if argv[:1] == ["revoke"] and len(argv) == 3:
        try:
            ok = revoke(argv[1], argv[2])
        except ValueError as e:
            print(f"✗ {e}")
            return 2
        print("✓ done – restart the app" if ok else "✗ flatpak override failed")
        return 0 if ok else 1
    if argv[:1] == ["--json"]:
        print(json.dumps(scan(), indent=1))
        return 0
    print(report())
    return 0
