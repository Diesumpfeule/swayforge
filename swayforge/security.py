"""Security: malware scan (ClamAV), rootkit checks (rkhunter, chkrootkit), audit (Lynis), device overview.

All scanners are free software from the Fedora repos. Nothing is deleted automatically:
infected files go to a quarantine folder (or are only reported), every run leaves a report.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from . import paths
from .system import notify, run

REPORT_DIR = paths.STATE_DIR / "security"
QUARANTINE = paths.STATE_DIR / "quarantine"
CLAM_DB = Path("/var/lib/clamav")
UNIT_DIR = paths.XDG_CONFIG / "systemd/user"

TOOLS = {
    "clamscan": "ClamAV (malware scanner)",
    "freshclam": "ClamAV signature updates",
    "rkhunter": "rkhunter (rootkit hunter)",
    "chkrootkit": "chkrootkit (rootkit check)",
    "lynis": "Lynis (security audit)",
    "usbguard": "USBGuard (USB device control)",
    "lsusb": "lsusb (USB device list)",
}

# Big folders that only waste scan time (games, caches, our own quarantine)
HOME_EXCLUDES = [r"/\.cache/", r"/\.local/share/Steam/steamapps/", r"/\.steam/", r"/\.var/app/[^/]+/cache/",
                 r"/\.local/share/containers/", r"/\.local/share/swayforge/quarantine/", r"/node_modules/",
                 r"/\.git/objects/"]


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def installed() -> dict[str, bool]:
    return {t: have(t) for t in TOOLS}


def signature_age_days() -> float | None:
    """Days since the ClamAV signatures were updated (None = no database)."""
    files = [f for f in CLAM_DB.glob("*.c[lv]d")] if CLAM_DB.is_dir() else []
    if not files:
        return None
    return (time.time() - max(f.stat().st_mtime for f in files)) / 86400


def removable_drives() -> list[dict]:
    """Mounted USB sticks / SD cards / external disks."""
    r = run(["lsblk", "-J", "-o", "NAME,LABEL,SIZE,MOUNTPOINT,RM,HOTPLUG,TRAN,TYPE"])
    if r.returncode != 0:
        return []
    out = []

    def walk(devs, parent_usb=False):
        for d in devs:
            usb = parent_usb or d.get("tran") == "usb" or bool(d.get("rm")) or bool(d.get("hotplug"))
            mp = d.get("mountpoint")
            if usb and mp and mp not in ("/", "/boot", "/boot/efi", "[SWAP]") and not mp.startswith("/var"):
                out.append({"dev": "/dev/" + d["name"], "label": d.get("label") or d["name"],
                            "size": d.get("size", ""), "mount": mp})
            walk(d.get("children", []), usb)
    try:
        walk(json.loads(r.stdout).get("blockdevices", []))
    except ValueError:
        pass
    return out


def resolve_target(target: str) -> list[str]:
    t = target.strip()
    if t in ("", "downloads"):
        for name in ("Downloads", "Download", "Herunterladen"):
            p = paths.HOME / name
            if p.is_dir():
                return [str(p)]
        return [str(paths.HOME / "Downloads")]
    if t == "home":
        return [str(paths.HOME)]
    if t == "drives":
        return [d["mount"] for d in removable_drives()]
    return [os.path.expanduser(t)]


def report_path(kind: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}.log"


def clamscan_cmd(targets: list[str], quarantine: bool, report: Path, home: bool = False) -> list[str]:
    cmd = ["clamscan", "--recursive", "--infected", f"--log={report}",
           "--max-filesize=200M", "--max-scansize=400M"]
    if home:
        for pat in HOME_EXCLUDES:
            cmd.append(f"--exclude-dir={pat}")
    if quarantine:
        QUARANTINE.mkdir(parents=True, exist_ok=True)
        QUARANTINE.chmod(0o700)
        cmd.append(f"--move={QUARANTINE}")
    return cmd + targets


def scan(target: str = "downloads", quarantine: bool = True, quiet: bool = False) -> int:
    """Run a ClamAV scan in this terminal. Returns 0 clean, 1 found something, 2 error."""
    if not have("clamscan"):
        print("ClamAV isn't installed:  sudo dnf install clamav clamav-freshclam")
        return 2
    targets = [t for t in resolve_target(target) if Path(t).exists()]
    if not targets:
        print(f"Nothing to scan ({target}).")
        return 2
    age = signature_age_days()
    if age is None:
        print("No virus signatures yet – run:  sudo freshclam")
        return 2
    if age > 7 and not quiet:
        print(f"⚠ Signatures are {age:.0f} days old – update with:  sudo freshclam\n")
    rep = report_path("clamav")
    cmd = clamscan_cmd(targets, quarantine, rep, home=target == "home")
    if not quiet:
        print("Scanning:", ", ".join(targets))
        print("This can take a while for big folders. Ctrl+C stops.\n")
    rc = subprocess.call(cmd, stdout=subprocess.DEVNULL if quiet else None)
    s = summarize(rep)
    found = s.get("infected", 0)
    title = "Malware scan: " + ("nothing found" if rc == 0 else f"{found} infected file(s)!" if rc == 1
                                 else "error – see report")
    body = f"{', '.join(Path(t).name or t for t in targets)}" + \
           (" · moved to quarantine" if found and quarantine else "")
    notify(title, body)
    if not quiet:
        print(f"\n{title}\nReport: {rep}")
        if found:
            print(f"Quarantine: {QUARANTINE}" if quarantine else "Files were NOT moved (quarantine off).")
    return rc


def rootkit_cmd(report: Path) -> str:
    """rkhunter + chkrootkit (need root). Output goes to the screen and the report."""
    parts = []
    if have("rkhunter"):
        parts.append("echo '── rkhunter ──'; sudo rkhunter --check --sk --rwo --nocolors")
    if have("chkrootkit"):
        parts.append("echo; echo '── chkrootkit ──'; sudo chkrootkit -q")
    if not parts:
        return "echo 'rkhunter/chkrootkit not installed: sudo dnf install rkhunter chkrootkit'"
    return "{ " + "; ".join(parts) + "; } 2>&1 | tee " + shlex.quote(str(report))


def audit_cmd(report: Path) -> str:
    if not have("lynis"):
        return "echo 'Lynis not installed: sudo dnf install lynis'"
    return f"sudo lynis audit system --quick --no-colors 2>&1 | tee {shlex.quote(str(report))}"


def summarize(report: Path) -> dict:
    """Pull the interesting numbers out of a report."""
    try:
        txt = report.read_text(errors="replace")
    except OSError:
        return {}
    out: dict = {}
    m = re.search(r"Infected files:\s*(\d+)", txt)
    if m:
        out["infected"] = int(m.group(1))
    m = re.search(r"Scanned files:\s*(\d+)", txt)
    if m:
        out["scanned"] = int(m.group(1))
    if "rkhunter" in txt or "chkrootkit" in txt:
        out["warnings"] = len(re.findall(r"^Warning:", txt, re.M)) + len(re.findall(r"INFECTED", txt))
    m = re.search(r"Hardening index\s*:\s*(\d+)", txt)
    if m:
        out["hardening"] = int(m.group(1))
    return out


def reports(limit: int = 12) -> list[tuple[Path, dict]]:
    if not REPORT_DIR.is_dir():
        return []
    files = sorted(REPORT_DIR.glob("*.log"), reverse=True)[:limit]
    return [(f, summarize(f)) for f in files]


def describe(rep: Path, s: dict) -> str:
    stamp = rep.name[:15]
    when = f"{stamp[6:8]}.{stamp[4:6]}. {stamp[9:11]}:{stamp[11:13]}"
    kind = rep.stem.split("-", 2)[-1]
    if kind == "clamav":
        n = s.get("infected")
        res = "?" if n is None else ("clean" if n == 0 else f"⚠ {n} infected")
        return f"{when}  malware   {res}  ({s.get('scanned', '?')} files)"
    if kind == "rootkit":
        w = s.get("warnings")
        return f"{when}  rootkit   {'?' if w is None else ('no warnings' if w == 0 else f'{w} warning(s) – read it')}"
    if kind == "audit":
        return f"{when}  audit     hardening index {s.get('hardening', '?')}/100"
    return f"{when}  {kind}"


# ── Device & system overview (no root needed) ────────────────────────
def overview(kind: str) -> str:
    if kind == "usb":
        r = run(["lsusb"])
        return r.stdout.strip() or "lsusb not available (sudo dnf install usbutils)"
    if kind == "drives":
        r = run(["lsblk", "-o", "NAME,SIZE,TYPE,TRAN,RM,FSTYPE,LABEL,MOUNTPOINTS"])
        return r.stdout.strip()
    if kind == "ports":
        r = run(["ss", "-tulnH"])
        if r.returncode != 0:
            return "ss not available (sudo dnf install iproute)"
        lines = [l.split() for l in r.stdout.splitlines() if l.strip()]
        rows = [f"{l[0]:<5} {l[4]:<28}" for l in lines if len(l) >= 5]
        local = [x for x in rows if "127.0.0." not in x and "[::1]" not in x and "%lo" not in x]
        head = f"{len(rows)} listening sockets, {len(local)} reachable from the network:\n"
        return head + ("\n".join(local) if local else "  none – nothing on this PC listens to the network")
    if kind == "autostart":
        lines = ["Your autostart entries:"]
        for d in (paths.XDG_CONFIG / "autostart", Path("/etc/xdg/autostart")):
            if d.is_dir():
                for f in sorted(d.glob("*.desktop")):
                    hidden = "Hidden=true" in f.read_text(errors="replace")
                    lines.append(f"  {'(off) ' if hidden else ''}{f}")
        r = run(["systemctl", "--user", "list-unit-files", "--state=enabled", "--no-legend", "--type=service"])
        lines.append("\nEnabled user services:")
        lines += [f"  {l.split()[0]}" for l in r.stdout.splitlines() if l.strip()] or ["  none"]
        r = run(["crontab", "-l"])
        cron = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith("#")]
        lines.append("\nYour cron jobs:")
        lines += [f"  {l}" for l in cron] or ["  none"]
        return "\n".join(lines)
    return ""


# ── Weekly scan (systemd user timer) ─────────────────────────────────
def timer_files(launcher: str, target: str) -> dict[Path, str]:
    return {
        UNIT_DIR / "swayforge-scan.service": (
            "# swayforge generated – weekly malware scan\n[Unit]\nDescription=swayforge weekly malware scan\n\n"
            f"[Service]\nType=oneshot\nNice=15\nIOSchedulingClass=idle\n"
            f"ExecStart={launcher} scan {target} --quiet\n"),
        UNIT_DIR / "swayforge-scan.timer": (
            "# swayforge generated\n[Unit]\nDescription=swayforge weekly malware scan\n\n"
            "[Timer]\nOnCalendar=weekly\nPersistent=true\nRandomizedDelaySec=1h\n\n"
            "[Install]\nWantedBy=timers.target\n"),
    }


def set_weekly(enabled: bool, launcher: str, target: str = "downloads") -> None:
    files = timer_files(launcher, target)
    if enabled:
        UNIT_DIR.mkdir(parents=True, exist_ok=True)
        for p, txt in files.items():
            p.write_text(txt)
        run(["systemctl", "--user", "daemon-reload"])
        run(["systemctl", "--user", "enable", "--now", "swayforge-scan.timer"])
    else:
        run(["systemctl", "--user", "disable", "--now", "swayforge-scan.timer"])
        for p in files:
            if p.exists() and "swayforge generated" in p.read_text():
                p.unlink()
        run(["systemctl", "--user", "daemon-reload"])
