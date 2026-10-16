"""System cleanup and a careful wiper for USB sticks, SD cards and external SSDs.

Cleanup: every item says how much it frees and runs a plain, well-known command.
Wiping: only drives that are removable/hot-plugged AND hold nothing the running
system uses are ever offered. The wipe itself runs in a terminal, re-checks the drive
right before touching it and asks you to type the device name once more.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .apps import human


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def du(path: Path | str) -> int:
    """Bytes used below path (0 if missing or unreadable)."""
    p = Path(path)
    if not p.exists():
        return 0
    r = _run(["du", "-sb", str(p)], timeout=60)
    try:
        return int(r.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


# ── Cleanup ──────────────────────────────────────────────────────────
@dataclass
class Item:
    id: str
    label: str
    desc: str
    cmd: str                 # shell command (may use sudo – it runs in a terminal)
    size: int = -1           # -1 = unknown / can't be measured without root
    note: str = ""


def _journal_size() -> int:
    r = _run(["journalctl", "--disk-usage"])
    # "Archived and active journals take up 1.2G in the file system."
    for tok in r.stdout.replace("\n", " ").split():
        if tok[:-1].replace(".", "").isdigit() and tok[-1] in "BKMGT":
            mult = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}[tok[-1]]
            return int(float(tok[:-1]) * mult)
    return -1


def _unneeded() -> list[str]:
    r = _run(["dnf", "repoquery", "--unneeded", "--qf", "%{name}\n"], timeout=120)
    return [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def _unused_runtimes() -> int:
    """Rough count: Flatpak runtimes no installed app refers to."""
    if not _have("flatpak"):
        return 0
    apps = _run(["flatpak", "list", "--app", "--columns=runtime"]).stdout.split()
    rts = _run(["flatpak", "list", "--runtime", "--columns=application,branch"]).stdout.splitlines()
    used = {a.split("/")[0] for a in apps}
    return sum(1 for r in rts if r.split("\t")[0] not in used and ".Extension" not in r
               and ".GL." not in r and ".Locale" not in r and ".Debug" not in r)


def _have(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def items(measure: bool = True) -> list[Item]:
    home = paths.HOME
    trash = home / ".local/share/Trash"
    thumbs = home / ".cache/thumbnails"
    out = [
        Item("dnf_cache", "Package cache", "downloaded RPMs and repo metadata – dnf fetches them again when needed",
             "sudo dnf clean all", du("/var/cache/libdnf5") + du("/var/cache/dnf") if measure else -1),
        Item("autoremove", "Unneeded packages", "dependencies nothing needs any more",
             "sudo dnf autoremove"),
        Item("journal", "Old system logs", "keeps the last 2 weeks of the journal",
             "sudo journalctl --vacuum-time=2weeks", _journal_size() if measure else -1),
        Item("coredumps", "Crash dumps", "memory dumps of crashed programs",
             "sudo find /var/lib/systemd/coredump -type f -delete",
             du("/var/lib/systemd/coredump") if measure else -1),
        Item("trash", "Trash", "everything in the file manager's trash",
             f"rm -rf {shlex.quote(str(trash / 'files'))}/* {shlex.quote(str(trash / 'info'))}/* "
             f"{shlex.quote(str(trash / 'expunged'))}/* 2>/dev/null; true", du(trash) if measure else -1),
        Item("thumbs", "Thumbnail cache", "picture previews – rebuilt when you browse folders",
             f"rm -rf {shlex.quote(str(thumbs))}", du(thumbs) if measure else -1),
    ]
    if _have("flatpak"):
        out.append(Item("flatpak", "Unused Flatpak runtimes", "runtimes left behind by removed Flatpak apps",
                        "flatpak uninstall --unused"))
    if measure:
        un = _unneeded()
        out[1].note = f"{len(un)} package(s)" if un else "nothing to remove"
        if un:
            from .apps import rpm_db
            db = rpm_db()
            out[1].size = sum(db.get(p, (0, ""))[0] for p in un)
        else:
            out[1].size = 0
        if _have("flatpak"):
            n = _unused_runtimes()
            out[-1].note = f"about {n} runtime(s)" if n else "nothing to remove"
    return out


def describe(it: Item) -> str:
    size = "?" if it.size < 0 else human(it.size)
    return f"{size:>9}  {it.label}" + (f"  [dim]({it.note})[/]" if it.note else "")


# ── Drives that may be wiped ─────────────────────────────────────────
SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/efi", "/home", "/var", "/usr", "/nix", "/sysroot", "[SWAP]")


def _mounts(d: dict) -> list[str]:
    mps = list(d.get("mountpoints") or []) + ([d["mountpoint"]] if d.get("mountpoint") else [])
    out = [m for m in mps if m]
    for ch in d.get("children") or []:
        out += _mounts(ch)
    return out


def _holds_system(d: dict) -> bool:
    for m in _mounts(d):
        if m in SYSTEM_MOUNTS or m.startswith(("/var/", "/usr/", "/boot/")):
            return True
    for ch in d.get("children") or []:
        if ch.get("type") in ("crypt", "lvm", "raid1", "raid0", "md") and _holds_system(ch):
            return True
        if (ch.get("fstype") or "") in ("swap", "LVM2_member", "linux_raid_member"):
            return True
    return False


def wipeable_drives() -> list[dict]:
    """Whole disks that are USB/SD/hot-plugged and carry nothing the running system needs."""
    r = _run(["lsblk", "-J", "-b", "-o",
              "NAME,PATH,SIZE,MODEL,SERIAL,TRAN,RM,HOTPLUG,TYPE,FSTYPE,LABEL,MOUNTPOINTS,ROTA,DISC-GRAN"])
    if r.returncode != 0:
        return []
    try:
        devs = json.loads(r.stdout).get("blockdevices", [])
    except ValueError:
        return []
    out = []
    for d in devs:
        if d.get("type") != "disk" or d["name"].startswith(("loop", "zram", "sr", "ram")):
            continue
        external = d.get("tran") in ("usb", "mmc", "sdio", "ieee1394") or bool(d.get("rm")) or bool(d.get("hotplug"))
        if d["name"].startswith("mmcblk") and d.get("tran") not in ("mmc", "sdio") and not d.get("rm"):
            external = external and bool(d.get("hotplug"))      # soldered eMMC is not a card
        if not external or _holds_system(d) or int(d.get("size") or 0) == 0:
            continue
        kind = "SD card" if d["name"].startswith("mmcblk") else \
            "SSD" if not d.get("rota") else "hard disk" if int(d.get("size") or 0) > 600e9 else "USB stick"
        parts = [f"{c['name']} {c.get('fstype') or ''} {c.get('label') or ''}".strip()
                 for c in d.get("children") or []]
        out.append({"name": d["name"], "path": d.get("path") or f"/dev/{d['name']}",
                    "size": int(d.get("size") or 0), "model": (d.get("model") or "").strip() or kind,
                    "serial": (d.get("serial") or "").strip(), "kind": kind,
                    "discard": int(d.get("disc-gran") or 0) > 0, "parts": parts,
                    "mounted": _mounts(d)})
    return out


def drive_label(d: dict) -> str:
    return f"{d['name']} · {d['model']} · {human(d['size'])} · {d['kind']}"


MODES = {
    "quick": "Quick: erase partition table + signatures, new empty file system (seconds)",
    "zero": "Secure: overwrite every byte with zeros, then format (slow – about 1 min per GB on USB 2)",
    "discard": "Secure, SSD/SD: tell the flash to drop every block (TRIM/discard), then format (fast)",
}
MODE_SHORT = {"quick": "Quick (seconds)", "zero": "Secure: zero-fill (slow)", "discard": "Secure: discard / TRIM (SSD, SD)"}
FS_SHORT = {"exfat": "exFAT (everywhere, big files)", "vfat": "FAT32 (old devices, max 4 GB/file)",
            "ext4": "ext4 (Linux only)", "none": "leave empty"}
FILESYSTEMS = {
    "exfat": "exFAT – Windows, macOS, Linux, cameras; files over 4 GB",
    "vfat": "FAT32 – everything incl. old devices; max 4 GB per file",
    "ext4": "ext4 – Linux only",
    "none": "none – leave it empty",
}


def wipe_script(d: dict, mode: str, fs: str, label: str) -> list[str]:
    dev = shlex.quote(d["path"])
    lab = "".join(ch for ch in label if ch.isalnum() or ch in "-_")[:11] or "USB"
    parts = [shlex.quote("/dev/" + p.split()[0]) for p in d["parts"]]
    cmds = [f"sudo umount {p} 2>/dev/null || true" for p in parts]
    cmds += [f"sudo wipefs -a {p}" for p in parts]           # file-system signatures first
    cmds.append(f"sudo wipefs -a {dev}")                     # then the partition table
    if mode == "zero":
        cmds.append(f"sudo dd if=/dev/zero of={dev} bs=4M oflag=direct status=progress conv=fsync || true")
    elif mode == "discard":
        cmds.append(f"sudo blkdiscard -f {dev}")
    if fs != "none":
        part = d["path"] + ("p1" if d["name"][-1].isdigit() else "1")
        pq = shlex.quote(part)
        # ext4: GPT. exFAT/FAT32: MBR – cameras, TVs, car radios and consoles read that best
        table = "label: gpt\\n,,L\\n" if fs == "ext4" else f"label: dos\\n,,{'7' if fs == 'exfat' else 'c'}\\n"
        cmds.append(f"printf '{table}' | sudo sfdisk --wipe always {dev}")
        cmds.append("sudo udevadm settle")
        mk = {"exfat": f"sudo mkfs.exfat -L {shlex.quote(lab)} {pq}",
              "vfat": f"sudo mkfs.vfat -F 32 -n {shlex.quote(lab.upper())} {pq}",
              "ext4": f"sudo mkfs.ext4 -F -L {shlex.quote(lab)} {pq}"}[fs]
        cmds.append(mk)
        if fs == "ext4":
            cmds.append(f"sudo mkdir -p /tmp/sf-wipe && sudo mount {pq} /tmp/sf-wipe && "
                        f"sudo chown {os.getuid()}:{os.getgid()} /tmp/sf-wipe && sudo umount /tmp/sf-wipe")
    cmds.append("sync")
    return cmds


def wipe_main(name: str, mode: str, fs: str, label: str, size: int, confirm: str = "") -> int:
    """`swayforge wipe` – runs in a terminal. Re-checks everything before touching the drive."""
    drives = {d["name"]: d for d in wipeable_drives()}
    d = drives.get(name.removeprefix("/dev/"))
    if not d:
        print(f"✗ {name} is not a removable drive (or it holds part of the running system) – nothing done.")
        return 1
    if size and d["size"] != size:
        print(f"✗ {name} changed since you picked it (size differs) – was another drive plugged in? Nothing done.")
        return 1
    if mode not in MODES or fs not in FILESYSTEMS:
        print("✗ unknown mode or file system")
        return 2
    print(f"\n  Drive : {drive_label(d)}")
    print(f"  Parts : {', '.join(d['parts']) or 'none'}")
    print(f"  Mode  : {MODES[mode]}")
    print(f"  Format: {FILESYSTEMS[fs]}" + (f"  (label {label})" if fs != "none" else ""))
    if mode == "discard" and not d["discard"]:
        print("  ! This drive does not report discard support – switching to zero-fill.")
        mode = "zero"
    if mode == "zero":
        print("  Note: on flash memory (USB/SD/SSD) wear levelling can keep old copies of blocks that a\n"
              "  zero-fill can't reach. For truly secret data, use encryption from the start.")
    print("\n  EVERYTHING on this drive will be gone. There is no undo.\n")
    ans = confirm or input(f"  Type the device name ({d['name']}) to continue: ").strip()
    if ans != d["name"]:
        print("Cancelled – nothing was changed.")
        return 1
    for c in wipe_script(d, mode, fs, label):
        print(f"\n$ {c}")
        r = subprocess.run(["sh", "-c", c])
        if r.returncode != 0 and "|| true" not in c:
            print(f"\n✗ step failed (exit {r.returncode}) – stopped here.")
            return r.returncode
    print(f"\n✓ {d['name']} wiped" + (" and formatted." if fs != "none" else "."))
    return 0


if __name__ == "__main__":       # pragma: no cover
    sys.exit(wipe_main(*sys.argv[1:5], int(sys.argv[5]) if len(sys.argv) > 5 else 0))
