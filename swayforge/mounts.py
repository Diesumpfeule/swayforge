"""Mount drives permanently: /mnt/NAME + a line in /etc/fstab, done safely.

Every change: /etc/fstab is backed up first, the new file is checked with
`findmnt --verify`, and if that fails the backup goes straight back. Entries get
`nofail` + a short device timeout, so a missing drive never blocks booting.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from . import paths
from .apps import human

FSTAB = Path("/etc/fstab")
TAG = "# swayforge mount:"
SUPPORTED = {"ext4", "btrfs", "xfs", "f2fs", "ntfs", "exfat", "vfat"}
SKIP_PARTTYPES = {
    "c12a7328-f81f-11d2-ba4b-00a0c93ec93b",   # EFI system
    "de94bba4-06d1-4d40-a16a-bfd50179d6ac",   # Windows recovery
    "e3c9e316-0b5c-4db8-817d-f92df00215ae",   # Microsoft reserved
    "21686148-6449-6e6f-744e-656564454649",   # BIOS boot
}
SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/efi", "/home", "/var", "/usr", "/sysroot", "[SWAP]")


def _run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def fstab_text() -> str:
    try:
        return FSTAB.read_text()
    except OSError:
        return ""


def _fstab_ids(text: str) -> set[str]:
    ids = set()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(line.split()[0])
    return ids


def entries() -> list[dict]:
    """Mounts swayforge added (they carry a tag comment)."""
    out, lines = [], fstab_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith(TAG) and i + 1 < len(lines):
            spec = lines[i + 1].split()
            if len(spec) >= 3:
                out.append({"label": line[len(TAG):].strip(), "spec": spec[0], "target": spec[1],
                            "fstype": spec[2], "mounted": os.path.ismount(spec[1])})
    return out


def candidates() -> list[dict]:
    """Partitions (internal or external) with a file system that aren't in fstab yet."""
    r = _run(["lsblk", "-J", "-b", "-o",
              "NAME,PATH,SIZE,FSTYPE,LABEL,UUID,PARTTYPE,PARTLABEL,MOUNTPOINTS,TYPE,TRAN,RM,HOTPLUG,MODEL"])
    try:
        devs = json.loads(r.stdout).get("blockdevices", []) if r.returncode == 0 else []
    except ValueError:
        devs = []
    known = _fstab_ids(fstab_text())
    out = []

    def walk(d: dict, model: str, external: bool) -> None:
        model = (d.get("model") or "").strip() or model
        external = external or d.get("tran") in ("usb", "mmc") or bool(d.get("rm")) or bool(d.get("hotplug"))
        fs, uuid = d.get("fstype") or "", d.get("uuid") or ""
        mps = [m for m in (d.get("mountpoints") or []) if m]
        if (fs in SUPPORTED and uuid and d.get("type") in ("part", "disk")
                and (d.get("parttype") or "").lower() not in SKIP_PARTTYPES
                and not (fs == "vfat" and re.search(r"efi|esp|boot", (d.get("partlabel") or d.get("label") or ""), re.I))
                and not any(m in SYSTEM_MOUNTS or m.startswith(("/boot", "/var/", "/usr/")) for m in mps)
                and f"UUID={uuid}" not in known and d["path"] not in known
                and not d["name"].startswith(("loop", "zram", "sr"))):
            out.append({"name": d["name"], "path": d["path"], "uuid": uuid, "fstype": fs,
                        "label": d.get("label") or "", "size": int(d.get("size") or 0),
                        "model": model, "external": external, "mounted": mps})
        for ch in d.get("children") or []:
            walk(ch, model, external)

    for d in devs:
        walk(d, "", False)
    return out


def describe(c: dict) -> str:
    where = f" · now at {c['mounted'][0]}" if c["mounted"] else ""
    return (f"{c['name']} · {c['label'] or 'no label'} · {human(c['size'])} · {c['fstype']}"
            f" · {c['model'] or 'disk'}{' (external)' if c['external'] else ''}{where}")


def default_name(c: dict) -> str:
    return clean_name(c["label"]) or f"drive-{c['name']}"


def clean_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s.strip()).strip("-")[:32].lower()


def options(fstype: str, uid: int, gid: int) -> tuple[str, str, int]:
    """(fstab type, options, fsck pass) – owner = you for Windows/flash file systems."""
    safe = "nofail,x-systemd.device-timeout=5s"
    if fstype == "ntfs":
        return "ntfs3", f"uid={uid},gid={gid},umask=022,windows_names,{safe}", 0
    if fstype in ("exfat", "vfat"):
        return fstype, f"uid={uid},gid={gid},umask=022,{safe}", 0
    if fstype == "btrfs":
        return "btrfs", f"defaults,compress=zstd:1,{safe}", 0
    return fstype, f"defaults,{safe}", 2 if fstype in ("ext4", "xfs") else 0


def fstab_line(c: dict, name: str, uid: int, gid: int) -> str:
    typ, opts, passno = options(c["fstype"], uid, gid)
    return f"UUID={c['uuid']}  /mnt/{name}  {typ}  {opts}  0 {passno}"


def _sh(cmd: str) -> int:
    print(f"\n$ {cmd}")
    return subprocess.run(["sh", "-c", cmd]).returncode


def _backup() -> str:
    b = f"{FSTAB}.swayforge-{time.strftime('%Y%m%d-%H%M%S')}"
    _sh(f"sudo cp -a {FSTAB} {b}")
    return b


def _errors(tab: str) -> list[str]:
    r = subprocess.run(["sh", "-c", f"sudo findmnt --verify --tab-file {shlex.quote(tab)} 2>&1"],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "[E]" in l]


def _verify_or_restore(backup: str) -> bool:
    """Only errors that weren't there before count – old problems in your fstab aren't ours."""
    before = set(_errors(backup))
    bad = [l for l in _errors(str(FSTAB)) if l not in before]
    if bad:
        print("\n".join(bad))
        print(f"\n✗ fstab check failed – putting the old file back ({backup}). Nothing changed.")
        _sh(f"sudo cp -a {backup} {FSTAB} && sudo systemctl daemon-reload")
        return False
    return True


def bookmark(name: str, add: bool) -> None:
    """Thunar/GTK sidebar entry for /mnt/NAME."""
    bm = paths.XDG_CONFIG / "gtk-3.0/bookmarks"
    line = f"file:///mnt/{name} {name}"
    lines = bm.read_text().splitlines() if bm.exists() else []
    lines = [l for l in lines if l.split(" ")[0] != f"file:///mnt/{name}"]
    if add:
        lines.append(line)
    bm.parent.mkdir(parents=True, exist_ok=True)
    bm.write_text("\n".join(lines) + ("\n" if lines else ""))


def add_main(dev: str, name: str) -> int:
    """`swayforge mount add DEV NAME` – runs in a terminal (asks for sudo)."""
    name = clean_name(name)
    c = next((x for x in candidates() if x["name"] == dev.removeprefix("/dev/")), None)
    if not c:
        print(f"✗ {dev} isn't a mountable partition, or it's already in /etc/fstab.")
        return 1
    if not name:
        print("✗ name missing")
        return 1
    target = f"/mnt/{name}"
    if os.path.ismount(target) or (os.path.isdir(target) and os.listdir(target)):
        print(f"✗ {target} is already in use – pick another name.")
        return 1
    line = fstab_line(c, name, os.getuid(), os.getgid())
    print(f"\n  {describe(c)}\n  → {target}  (permanent, survives reboots; a missing drive never blocks boot)")
    print(f"\n  fstab line:\n  {line}\n")
    backup = _backup()
    for m in c["mounted"]:                      # e.g. auto-mounted at /run/media/… → move it
        _sh(f"sudo umount {shlex.quote(m)} || true")
    if _sh(f"sudo mkdir -p {shlex.quote(target)}"):
        return 1
    entry = f"\n{TAG} {c['label'] or c['name']} ({c['model'] or 'disk'})\n{line}\n"
    if _sh(f"printf %s {shlex.quote(entry)} | sudo tee -a {FSTAB} >/dev/null"):
        return 1
    if not _verify_or_restore(backup):
        return 1
    _sh("sudo systemctl daemon-reload")
    if _sh(f"sudo mount {shlex.quote(target)}"):
        print(f"\n✗ mounting failed – the fstab entry stays (nofail, boot is safe). Backup: {backup}")
        if c["fstype"] == "ntfs":
            print("  Windows drive? Turn off “Fast Startup” in Windows (or shut Windows down fully),\n"
                  "  it leaves the drive locked. Then: sudo mount " + target)
        return 1
    if c["fstype"] in ("ext4", "btrfs", "xfs", "f2fs"):
        # a fresh Linux file system belongs to root – hand its top folder to you
        _sh(f"[ \"$(stat -c %u {shlex.quote(target)})\" = 0 ] && "
            f"[ -z \"$(ls -A {shlex.quote(target)} | grep -v '^lost+found$')\" ] && "
            f"sudo chown {os.getuid()}:{os.getgid()} {shlex.quote(target)} || true")
    bookmark(name, True)
    print(f"\n✓ {c['name']} is mounted at {target} – now and after every reboot. "
          f"It's in Thunar's sidebar too.\n  fstab backup: {backup}")
    return 0


def remove_main(target: str) -> int:
    """`swayforge mount remove /mnt/NAME` – unmount and drop swayforge's fstab entry (data stays)."""
    target = target if target.startswith("/") else f"/mnt/{target}"
    e = next((x for x in entries() if x["target"] == target), None)
    if not e:
        print(f"✗ no swayforge mount at {target}")
        return 1
    backup = _backup()
    _sh(f"sudo umount {shlex.quote(target)} 2>/dev/null || true")
    lines = fstab_text().splitlines()
    keep, skip = [], False
    for i, line in enumerate(lines):
        if skip:
            skip = False
            continue
        if line.startswith(TAG) and i + 1 < len(lines):
            nxt = lines[i + 1].split()
            if len(nxt) >= 2 and nxt[1] == target:
                skip = True
                if keep and not keep[-1].strip():
                    keep.pop()
                continue
        keep.append(line)
    new = "\n".join(keep).rstrip("\n") + "\n"
    _sh(f"printf %s {shlex.quote(new)} | sudo tee {FSTAB} >/dev/null")
    if not _verify_or_restore(backup):
        return 1
    _sh("sudo systemctl daemon-reload")
    _sh(f"sudo rmdir {shlex.quote(target)} 2>/dev/null || true")
    bookmark(Path(target).name, False)
    print(f"\n✓ {target} removed from fstab (the data on the drive is untouched). Backup: {backup}")
    return 0
