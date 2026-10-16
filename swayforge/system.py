"""Hardware/system detection and small helpers."""
from __future__ import annotations

import functools
import getpass
import glob
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str] | str, check: bool = False, **kw) -> subprocess.CompletedProcess:
    """Run a command; a missing program yields code 127 instead of an exception."""
    shell = isinstance(cmd, str)
    try:
        return subprocess.run(cmd, shell=shell, check=check, text=True,
                              capture_output=True, **kw)
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def os_release() -> dict:
    data = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v.strip().strip('"')
    except OSError:
        pass
    return data


@dataclass
class SysInfo:
    distro: str = "?"
    fedora: int = 0
    variant: str = ""
    user: str = ""
    amd_gpu: bool = False
    nvidia_gpu: bool = False
    laptop: bool = False
    bluetooth: bool = False
    in_sway: bool = False
    swayfx: bool = False
    hwmon_cpu: str = ""        # directory for Waybar hwmon-path-abs
    gpu_busy: str = ""         # /sys/.../gpu_busy_percent
    outputs: list[dict] = field(default_factory=list)

    @property
    def is_fedora(self) -> bool:
        return self.fedora > 0


def _hwmon_dir(names: tuple[str, ...]) -> str:
    for d in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            if Path(d, "name").read_text().strip() in names:
                return str(Path(d, "device").resolve() / "hwmon")
        except OSError:
            continue
    return ""


def _gpu_busy() -> str:
    for f in sorted(glob.glob("/sys/class/drm/card*/device/gpu_busy_percent")):
        return f
    return ""


def is_swayfx() -> bool:
    if not have("sway"):
        return False
    r = run(["sway", "--version"])
    return "swayfx" in (r.stdout + r.stderr).lower()


def sway_outputs() -> list[dict]:
    if not (os.environ.get("SWAYSOCK") and have("swaymsg")):
        return []
    r = run(["swaymsg", "-r", "-t", "get_outputs"])
    try:
        return json.loads(r.stdout) if r.returncode == 0 else []
    except json.JSONDecodeError:
        return []


@functools.cache
def detect() -> SysInfo:
    rel = os_release()
    info = SysInfo()
    info.distro = rel.get("PRETTY_NAME", "?")
    if rel.get("ID") == "fedora":
        try:
            info.fedora = int(rel.get("VERSION_ID", "0"))
        except ValueError:
            info.fedora = 0
    info.variant = rel.get("VARIANT_ID", "")
    info.user = os.environ.get("USER") or getpass.getuser()

    vendors = set()
    for f in glob.glob("/sys/class/drm/card*/device/vendor"):
        try:
            vendors.add(Path(f).read_text().strip())
        except OSError:
            pass
    info.amd_gpu = "0x1002" in vendors
    info.nvidia_gpu = "0x10de" in vendors

    info.laptop = bool(glob.glob("/sys/class/power_supply/BAT*"))
    if not info.laptop:
        try:
            chassis = Path("/sys/class/dmi/id/chassis_type").read_text().strip()
            info.laptop = chassis in {"8", "9", "10", "14", "31", "32"}
        except OSError:
            pass
    info.bluetooth = bool(glob.glob("/sys/class/bluetooth/hci*"))
    info.in_sway = bool(os.environ.get("SWAYSOCK"))
    info.swayfx = is_swayfx()
    info.hwmon_cpu = _hwmon_dir(("k10temp", "coretemp", "zenpower"))
    info.gpu_busy = _gpu_busy()
    info.outputs = sway_outputs()
    return info


def installed_rpms(names: list[str]) -> set[str]:
    """Which of these package names are installed?"""
    if not names or not have("rpm"):
        return set()
    r = run(["rpm", "-q", "--qf", "%{NAME}\n", *names])
    return {l.strip() for l in r.stdout.splitlines() if l.strip() and "not installed" not in l}


def notify(title: str, body: str = "") -> None:
    if have("notify-send"):
        subprocess.Popen(["notify-send", "-a", "swayforge", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
