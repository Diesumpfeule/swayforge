"""What is installed: the installer's catalogue + everything else you added yourself.

Read-only queries (rpm, dnf, flatpak). Uninstalling always happens in a terminal so
you see dnf/flatpak's own question and can still say no.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field

from .catalog import Catalog

OTHER = "other"


@dataclass
class Entry:
    id: str                       # catalogue id, or "rpm:<name>" / "flatpak:<app id>"
    label: str
    group: str                    # catalogue group id or "other"
    source: str                   # Fedora · RPM Fusion · COPR · Flatpak · vendor name
    size: int = 0                 # bytes (the app's own packages, not shared dependencies)
    rpms: list[str] = field(default_factory=list)
    flatpaks: list[str] = field(default_factory=list)
    locked: bool = False          # part of the swayforge base – removing it breaks the desktop

    def remove_cmd(self) -> str:
        parts = []
        if self.rpms:
            parts.append("sudo dnf remove " + " ".join(shlex.quote(p) for p in self.rpms))
        if self.flatpaks:
            parts.append("flatpak uninstall " + " ".join(shlex.quote(p) for p in self.flatpaks))
        return " && ".join(parts)


def _run(cmd: list[str], timeout: int = 60) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def source_name(vendor: str, release: str = "") -> str:
    v = vendor.lower()
    if "rpm fusion" in v:
        return "RPM Fusion"
    if "copr" in v:
        return "COPR"
    if "fedora" in v:
        return "Fedora"
    return vendor.strip() or "vendor repo"


def rpm_db() -> dict[str, tuple[int, str]]:
    """name → (installed size, source) for every installed RPM."""
    out = {}
    for line in _run(["rpm", "-qa", "--qf", r"%{NAME}\t%{SIZE}\t%{VENDOR}\n"]).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            name, size, vendor = parts
            out[name] = (int(size) if size.isdigit() else 0, source_name("" if vendor == "(none)" else vendor))
    return out


def flatpak_db() -> dict[str, tuple[str, int, str]]:
    """app id → (name, size, origin) for installed Flatpak apps."""
    out = {}
    raw = _run(["flatpak", "list", "--app", "--columns=application,name,size,origin"])
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            out[parts[0]] = (parts[1], parse_size(parts[2]), parts[3])
    return out


def user_installed() -> set[str]:
    """Packages you installed on purpose (dnf's own bookkeeping), not pulled-in dependencies."""
    raw = _run(["dnf", "repoquery", "--userinstalled", "--qf", "%{name}\n"], timeout=120)
    return {l.strip() for l in raw.splitlines() if l.strip()}


def parse_size(s: str) -> int:
    s = s.replace("\xa0", " ").strip()
    units = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
             "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4}
    try:
        num, unit = s.rsplit(" ", 1)
        return int(float(num.replace(",", ".")) * units.get(unit, 1))
    except ValueError:
        return 0


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1000
    return ""


# Fedora Sway spin / system packages that are never "your" apps, even if dnf says user-installed
_BASE_PREFIXES = ("kernel", "glibc", "systemd", "grub2", "shim", "dracut", "fedora-", "anaconda",
                  "dnf", "rpm", "sway", "sddm", "NetworkManager", "pipewire", "wireplumber", "linux-firmware",
                  "@", "gpg-pubkey", "langpacks", "glibc-", "xorg-x11-", "mesa-", "qt5-", "qt6-", "gtk",
                  "plymouth", "polkit", "selinux", "policycoreutils", "firewalld", "audit", "sudo", "bash",
                  "coreutils", "util-linux", "shadow-utils", "passwd", "openssh", "dbus", "iproute", "iputils",
                  "lvm2", "cryptsetup", "btrfs-progs", "e2fsprogs", "dosfstools", "xfsprogs", "efibootmgr",
                  "chrony", "rootfiles", "setup", "filesystem", "basesystem", "hostname", "less", "vim-minimal",
                  "nano-default-editor", "default-fonts", "google-noto", "abattis", "dejavu", "liberation")


def inventory(catalog: Catalog, with_other: bool = True) -> list[Entry]:
    rpms, flats = rpm_db(), flatpak_db()
    out: list[Entry] = []
    claimed_rpm: set[str] = set()
    claimed_fp: set[str] = set()
    for g in catalog.groups:
        for it in g.items:
            have_rpm = [p for p in it.dnf if p in rpms]
            have_fp = [p for p in it.flatpak if p in flats]
            claimed_rpm.update(it.dnf)
            claimed_fp.update(it.flatpak)
            if not have_rpm and not have_fp:
                continue
            srcs = []
            if have_rpm:
                srcs += sorted({"COPR" if it.copr else rpms[p][1] for p in have_rpm})
            if have_fp:
                srcs.append("Flatpak")
            size = sum(rpms[p][0] for p in have_rpm) + sum(flats[p][1] for p in have_fp)
            out.append(Entry(it.id, it.label, g.id, " + ".join(dict.fromkeys(srcs)), size,
                             have_rpm, have_fp, it.locked))
    if with_other:
        for name in sorted(user_installed()):
            if name in claimed_rpm or name not in rpms or name.startswith(_BASE_PREFIXES):
                continue
            size, src = rpms[name]
            out.append(Entry(f"rpm:{name}", name, OTHER, src, size, [name]))
        for app_id, (name, size, origin) in sorted(flats.items(), key=lambda kv: kv[1][0].lower()):
            if app_id not in claimed_fp:
                out.append(Entry(f"flatpak:{app_id}", name or app_id, OTHER, f"Flatpak ({origin})", size,
                                 flatpaks=[app_id]))
    return out
