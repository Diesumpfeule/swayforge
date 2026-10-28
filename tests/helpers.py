"""Shared test helpers: every test runs against a throw-away HOME, never your real one."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def fresh_home() -> Path:
    """New empty HOME + reloaded path modules (paths are computed at import time)."""
    home = Path(tempfile.mkdtemp(prefix="swayforge-test-"))
    os.environ["HOME"] = str(home)
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "SWAYSOCK", "WAYLAND_DISPLAY"):
        os.environ.pop(k, None)
    import swayforge.paths as p
    importlib.reload(p)
    for name in ("settings", "themes", "render", "screensaver", "livewall", "update", "security", "tools",
                 "widgets", "gamecfg"):
        mod = sys.modules.get(f"swayforge.{name}")
        if mod:
            importlib.reload(mod)
    return home


def sysinfo(**kw):
    from swayforge import system
    base = dict(distro="Fedora", fedora=43, user="tester", amd_gpu=True, laptop=True, bluetooth=True,
                swayfx=True, hwmon_cpu="/x", gpu_busy="/y")
    base.update(kw)
    return system.SysInfo(**base)
