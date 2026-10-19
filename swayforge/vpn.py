"""VPN helpers on top of NetworkManager (nmcli): list, connect, import, remove.

Handles OpenVPN (.ovpn) and WireGuard (.conf) files. Everything goes through nmcli with the connection's
UUID (never its name) so odd names can't confuse a command. Pure functions + a thin runner so it can be
tested with a fake nmcli."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VPN_TYPES = ("vpn", "wireguard")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
CONF_DIRS = ("Downloads", "", "vpn", "VPN", "Documents")


@dataclass
class Vpn:
    name: str
    uuid: str
    kind: str            # "OpenVPN" | "WireGuard" | other plugin name
    active: bool = False
    autoconnect: bool = False


def _run(*cmd: str, timeout: float = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def split_terse(line: str) -> list[str]:
    """Split an `nmcli -t` line at unescaped colons."""
    out, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ":":
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return out


def kind_of(vpn_type_service: str, nm_type: str) -> str:
    if nm_type == "wireguard":
        return "WireGuard"
    s = vpn_type_service.rsplit(".", 1)[-1].lower()
    return {"openvpn": "OpenVPN", "wireguard": "WireGuard", "openconnect": "OpenConnect",
            "l2tp": "L2TP", "pptp": "PPTP", "strongswan": "IPsec", "vpnc": "Cisco"}.get(s, s or "VPN")


def list_vpns() -> list[Vpn]:
    r = _run("nmcli", "-t", "-f", "NAME,UUID,TYPE,ACTIVE,AUTOCONNECT", "connection", "show")
    out = []
    for line in r.stdout.splitlines():
        f = split_terse(line)
        if len(f) >= 5 and f[2] in VPN_TYPES and UUID_RE.match(f[1]):
            out.append(Vpn(f[0], f[1], kind_of("", f[2]) if f[2] == "wireguard" else "VPN",
                           f[3] == "yes", f[4] == "yes"))
    # OpenVPN & friends: ask the plugin name per connection
    for v in out:
        if v.kind == "VPN":
            q = _run("nmcli", "-g", "vpn.service-type", "connection", "show", "uuid", v.uuid)
            v.kind = kind_of(q.stdout.strip(), "vpn")
    return sorted(out, key=lambda v: (not v.active, v.name.lower()))


def message(r: subprocess.CompletedProcess, ok: str = "done") -> tuple[str, bool]:
    lines = (r.stdout + "\n" + r.stderr).strip().splitlines()
    return (ok if r.returncode == 0 and not lines else (lines[-1] if lines else ok)), r.returncode == 0


def connect(uuid: str):
    if not UUID_RE.match(uuid):
        raise ValueError("bad id")
    return _run("nmcli", "connection", "up", "uuid", uuid, timeout=60)


def disconnect(uuid: str):
    if not UUID_RE.match(uuid):
        raise ValueError("bad id")
    return _run("nmcli", "connection", "down", "uuid", uuid)


def delete(uuid: str):
    if not UUID_RE.match(uuid):
        raise ValueError("bad id")
    return _run("nmcli", "connection", "delete", "uuid", uuid)


def set_autoconnect(uuid: str, on: bool):
    if not UUID_RE.match(uuid):
        raise ValueError("bad id")
    return _run("nmcli", "connection", "modify", "uuid", uuid, "connection.autoconnect", "yes" if on else "no")


def detect_type(path: Path) -> str | None:
    """'openvpn' | 'wireguard' | None, from the file's content (extension as a hint only)."""
    try:
        text = path.read_text(errors="replace")[:20000]
    except OSError:
        return None
    if re.search(r"^\s*\[Interface\]", text, re.M) and re.search(r"^\s*PrivateKey\s*=", text, re.M):
        return "wireguard"
    if re.search(r"^\s*(client|remote|dev)\b", text, re.M) and (path.suffix.lower() in (".ovpn", ".conf")
                                                                or "<ca>" in text):
        return "openvpn"
    return None


def find_configs(home: Path, limit: int = 40) -> list[Path]:
    seen: list[Path] = []
    for d in CONF_DIRS:
        base = home / d if d else home
        if not base.is_dir():
            continue
        try:
            files = sorted(base.iterdir())
        except OSError:
            continue
        for f in files:
            if f.is_file() and f.suffix.lower() in (".ovpn", ".conf") and f not in seen and detect_type(f):
                seen.append(f)
    return seen[:limit]


def plugin_missing(kind: str) -> str | None:
    """Package to install when NetworkManager can't handle this kind yet (OpenVPN needs a plugin)."""
    if kind == "openvpn" and not Path("/usr/lib64/NetworkManager/libnm-vpn-plugin-openvpn.so").exists() \
            and not list(Path("/usr/lib64/NetworkManager").glob("*openvpn*")) \
            and not list(Path("/usr/lib/NetworkManager").glob("*openvpn*")):
        return "NetworkManager-openvpn"
    return None


def import_file(path: Path, user: str = "") -> tuple[str, bool]:
    """Import a config file as a NetworkManager connection (passwords are never stored by us: nmcli asks in a terminal). Returns (message, ok)."""
    kind = detect_type(path)
    if not kind:
        return "That doesn't look like an OpenVPN (.ovpn) or WireGuard (.conf) file", False
    pkg = plugin_missing(kind)
    if pkg:
        return f"OpenVPN needs a NetworkManager plugin: sudo dnf install {pkg}", False
    before = {v.uuid for v in list_vpns()}
    r = _run("nmcli", "connection", "import", "type", kind, "file", str(path))
    msg, ok = message(r, "imported")
    if not ok:
        return msg, False
    new = [v for v in list_vpns() if v.uuid not in before]
    if new and kind == "openvpn" and user:
        _run("nmcli", "connection", "modify", "uuid", new[0].uuid, "+vpn.data", f"username={user}")
    return (f"Imported “{new[0].name}”" if new else msg), True


def needs_secret(msg: str) -> bool:
    m = msg.lower()
    return "secret" in m or "password" in m or "no valid secrets" in m


def have_tailscale() -> bool:
    return shutil.which("tailscale") is not None
