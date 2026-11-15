"""swayforge doctor – one look at everything that has to work, with the fix next to each problem.

Checks are quick and read-only (no root): the desktop's programs, services, your settings and
generated configs, fonts, disk space, background helpers. Problems come first, each with the
command or the place in Settings that fixes it; a few safe fixes can be run right away
(`swayforge doctor --fix`): re-apply the configs, restart helpers, restart the portals.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import paths, settings

OK, WARN, BAD = "ok", "warn", "bad"


@dataclass
class Check:
    group: str
    what: str
    state: str = OK              # ok | warn | bad
    detail: str = ""
    fix: str = ""                # command or place in Settings
    auto: str = ""               # id of a safe automatic fix (see FIXES)


def _run(cmd: list[str], timeout: int = 8) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _running(pattern: str, exact: bool = False) -> bool:
    return _run(["pgrep", "-x" if exact else "-f", pattern]).returncode == 0


# ── the single checks ────────────────────────────────────────────────
PROGRAMS = [   # (command, what it is for, package, needed?)
    ("sway", "the desktop itself", "sway", True),
    ("waybar", "the bar", "waybar", True),
    ("rofi", "app launcher and menus", "rofi-wayland", True),
    ("mako", "notifications", "mako", True),
    ("swaylock", "lock screen", "swaylock", True),
    ("swayidle", "auto lock / screen off", "swayidle", True),
    ("wl-copy", "clipboard", "wl-clipboard", True),
    ("grim", "screenshots, workspace pictures", "grim", False),
    ("slurp", "screenshot of an area", "slurp", False),
    ("rsvg-convert", "theme wallpapers", "librsvg2-tools", False),
    ("playerctl", "media keys, player widget", "playerctl", False),
    ("brightnessctl", "brightness keys (laptops)", "brightnessctl", False),
    ("pactl", "audio page, microphone level", "pulseaudio-utils", False),
    ("fastfetch", "terminal greeting", "fastfetch", False),
]


def check_programs() -> list[Check]:
    out = []
    missing_opt = []
    laptop = any(Path("/sys/class/power_supply").glob("BAT*")) if Path("/sys/class/power_supply").is_dir() else False
    for cmd, what, pkg, needed in PROGRAMS:
        if _have(cmd) or (cmd == "brightnessctl" and not laptop):
            continue
        if needed:
            out.append(Check("Programs", f"{cmd} is missing ({what})", BAD, fix=f"sudo dnf install {pkg}"))
        else:
            missing_opt.append((cmd, what, pkg))
    if missing_opt:
        out.append(Check("Programs", "optional helpers missing: " + ", ".join(f"{c} ({w})" for c, w, _ in missing_opt),
                         WARN, fix="sudo dnf install " + " ".join(p for _, _, p in missing_opt)))
    if not out:
        out.append(Check("Programs", f"all {len(PROGRAMS)} desktop programs are installed"))
    return out


def check_session() -> list[Check]:
    out = []
    in_sway = bool(os.environ.get("SWAYSOCK"))
    out.append(Check("Session", "running inside Sway" if in_sway else "not inside a Sway session", OK if in_sway else WARN,
                     fix="" if in_sway else "log in to Sway – the checks below about running helpers only count there"))
    if not in_sway:
        return out
    for name, pattern, exact, fix in (
            ("bar (waybar)", "waybar", True, "swaymsg reload"),
            ("notifications (mako)", "mako", True, "swaymsg reload"),
            ("auto lock (swayidle)", "swayidle", True, "swayforge session   (off on purpose while gaming mode is on)")):
        s = settings.load()
        if name.startswith(("bar", "notif")) and s["general"].get("shell") == "noctalia":
            continue
        if name.startswith("auto lock") and (paths.GEN_DIR / "gamemode").exists():
            out.append(Check("Session", "auto lock is paused – gaming mode is on", WARN, fix="Super+Shift+G switches it off"))
            continue
        run = _running(pattern, exact)
        out.append(Check("Session", f"{name} is running" if run else f"{name} is not running", OK if run else BAD,
                         fix="" if run else fix, auto="" if run else "reload"))
    env = _run(["systemctl", "--user", "show-environment"]).stdout
    good = "XDG_CURRENT_DESKTOP=sway" in env and "WAYLAND_DISPLAY=" in env
    out.append(Check("Session", "services know the Sway session (portals, screen sharing)" if good else
                     "services don't know the Sway session – screen sharing and portals fail", OK if good else BAD,
                     fix="" if good else "log out and in again (swayforge's Sway config exports it)"))
    return out


def check_services() -> list[Check]:
    out = []
    if not _have("systemctl"):
        return out
    for svc, what in (("pipewire", "sound"), ("wireplumber", "sound devices"), ("xdg-desktop-portal", "portals")):
        st = _run(["systemctl", "--user", "is-active", svc]).stdout.strip()
        if st == "active":
            out.append(Check("Services", f"{svc} is running ({what})"))
        elif svc == "xdg-desktop-portal":
            out.append(Check("Services", f"{svc} is {st or 'unknown'} – starts on demand", WARN, auto="portals",
                             fix="systemctl --user restart xdg-desktop-portal xdg-desktop-portal-wlr"))
        else:
            out.append(Check("Services", f"{svc} is {st or 'not running'} ({what})", BAD, fix=f"systemctl --user restart {svc}"))
    for scope in (["--user"], []):
        r = _run(["systemctl", *scope, "--failed", "--no-legend", "--plain"])
        units = [l.split()[0] for l in r.stdout.splitlines() if l.strip()]
        if units:
            who = "your" if scope else "system"
            out.append(Check("Services", f"{len(units)} failed {who} service(s): " + ", ".join(units[:5]), WARN,
                             fix=f"systemctl {' '.join(scope)} status {units[0]}".replace("  ", " ")))
    return out


def check_settings() -> list[Check]:
    out = []
    before = len(settings.LOAD_ERRORS)
    s = settings.load()
    if len(settings.LOAD_ERRORS) > before or settings.LOAD_ERRORS:
        out.append(Check("Settings", "settings.toml has an error – defaults are used", BAD,
                         detail=settings.LOAD_ERRORS[-1], fix=f"fix or delete {paths.SETTINGS_FILE}"))
    else:
        out.append(Check("Settings", "settings.toml is fine"))
    from . import layouts, themes
    if s["theme"]["name"] not in themes.all_themes() and s["theme"]["name"] not in themes.ALIASES:
        out.append(Check("Settings", f"theme “{s['theme']['name']}” no longer exists – the default is shown", WARN,
                         fix="Settings → Theme: pick one"))
    if not layouts.exists(s["bar"]["layout"]):
        out.append(Check("Settings", f"layout “{s['bar']['layout']}” no longer exists – Modern is shown", WARN,
                         fix="Settings → Layout: pick one"))
    return out


def check_configs() -> list[Check]:
    """Are the generated files what the settings say? (a dry run of Apply)"""
    out = []
    try:
        from . import render
        res = render.render_all(dry=True)
    except Exception as e:                       # noqa: BLE001
        return [Check("Configs", "the configs can't be generated", BAD, detail=f"{type(e).__name__}: {e}",
                      fix="swayforge apply   shows the full error")]
    if res.errors:
        out.append(Check("Configs", "generating the configs reports errors", BAD, detail="; ".join(res.errors[:3]),
                         fix="swayforge apply"))
    changed = [w for w in res.written if "/generated/" not in w]
    if changed:
        names = ", ".join(Path(w).name for w in changed[:4]) + (" …" if len(changed) > 4 else "")
        out.append(Check("Configs", f"{len(changed)} config file(s) are older than your settings ({names})", WARN,
                         fix="swayforge apply", auto="apply"))
    elif not res.errors:
        out.append(Check("Configs", "all generated configs match your settings"))
    if res.detached:
        out.append(Check("Configs", f"{len(res.detached)} file(s) are yours now (marker removed) – swayforge leaves them alone",
                         detail=", ".join(Path(d).name for d in res.detached[:5])))
    conf = paths.XDG_CONFIG / "sway/config"
    if conf.exists() and _have("sway"):
        r = _run(["sway", "-C", "-c", str(conf)], timeout=20)
        if r.returncode != 0:
            lines = [l for l in (r.stdout + r.stderr).splitlines() if "rror" in l][:3]
            out.append(Check("Configs", "Sway reports an error in its config", BAD, detail=" | ".join(lines),
                             fix=f"look at {paths.SWAY_CUSTOM} (your own lines) – or `swayforge undo`"))
        else:
            out.append(Check("Configs", "Sway accepts its config"))
    return out


def check_fonts() -> list[Check]:
    if not _have("fc-list"):
        return []
    s = settings.load()
    font = s["theme"]["font"]
    r = _run(["fc-list", ":", "family"])
    fams = {f.strip().lower() for l in r.stdout.splitlines() for f in l.split(",")}
    out = []
    if font.lower() in fams:
        out.append(Check("Fonts", f"font “{font}” is installed"))
    else:
        out.append(Check("Fonts", f"font “{font}” is not installed – a fallback is shown", WARN,
                         fix="Settings → Appearance → Font, or install it (installer → Desktop → fonts)"))
    if not any("nerd font" in f or "symbols nerd" in f for f in fams):
        out.append(Check("Fonts", "no Nerd Font found – icons in the bar show as boxes", WARN,
                         fix="swayforge install → Desktop → Sway base (brings the fonts)"))
    return out


def check_disk() -> list[Check]:
    out, seen = [], set()
    for label, mp in (("system drive", "/"), ("home", str(paths.HOME))):
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        if st.f_fsid in seen or not st.f_blocks:
            continue
        seen.add(st.f_fsid)
        free = st.f_bavail * st.f_frsize
        frac = st.f_bavail / st.f_blocks
        gb = free / 1e9
        if frac < 0.05 or gb < 3:
            out.append(Check("Disk", f"{label}: only {gb:.1f} GB free", BAD, fix="Settings → Cleanup & drives"))
        elif frac < 0.12:
            out.append(Check("Disk", f"{label}: {gb:.0f} GB free ({frac:.0%})", WARN, fix="Settings → Cleanup & drives"))
        else:
            out.append(Check("Disk", f"{label}: {gb:.0f} GB free"))
    return out


def check_helpers() -> list[Check]:
    """swayforge's own background helpers – running when they are switched on?"""
    out = []
    if not os.environ.get("SWAYSOCK"):
        return out
    s = settings.load()
    for on, name, pattern in (
            (s["clipboard"]["enabled"], "clipboard history", "m [s]wayforge clip watch"),
            (s["audio"]["keep_mic"] and _have("pactl"), "microphone level keeper", "m [s]wayforge mic keep"),
            (s["widgets"]["enabled"] and not (s.get("cyberdeck", {}).get("enabled") and s["cyberdeck"].get("low_power")),
             "desktop widgets", "m [s]wayforge widgets run")):
        if not on:
            continue
        run = _running(pattern)
        extra = ""
        if not run and name == "desktop widgets":
            from . import widgets
            bad = [w for ok, w, _f in widgets.check()[:4] if not ok]
            extra = ("missing: " + ", ".join(bad)) if bad else "; ".join(widgets.last_log(2))
        out.append(Check("Helpers", f"{name} is running" if run else f"{name} is switched on but not running",
                         OK if run else BAD, detail=extra, fix="" if run else "swaymsg reload", auto="" if run else "reload"))
    return out


def check_backup() -> list[Check]:
    from . import backup
    last = backup.last()
    s = settings.load()
    if last is None:
        return [Check("Backup", "no settings backup yet", WARN,
                      fix="Settings → System & files → Export, or turn on the automatic backup there")]
    import time
    days = (time.time() - last.stat().st_mtime) / 86400
    if days > 30 and not s["backup"]["auto"]:
        return [Check("Backup", f"last settings backup is {days:.0f} days old", WARN,
                      fix="Settings → System & files → automatic backup")]
    return [Check("Backup", f"last settings backup: {days:.0f} day(s) ago ({last.name})")]


def check_updates() -> list[Check]:
    from . import update
    out = []
    for name in update.APPS:
        info = update.local(name)
        if not info["installed"]:
            continue
        rem = update.remote(name)
        if rem and info["commit"] and not (rem.startswith(info["commit"]) or info["commit"].startswith(rem)):
            out.append(Check("Updates", f"{name}: “{update.codename(rem)}” is available (you have “{update.codename(info['commit'])}”)",
                             WARN, fix="swayforge update"))
        elif rem and info["commit"]:
            out.append(Check("Updates", f"{name} “{update.codename(info['commit'])}” is the newest version"))
    return out


CHECKS = [check_programs, check_session, check_services, check_settings, check_configs, check_fonts,
          check_disk, check_helpers, check_backup]


def run_all(online: bool = False) -> list[Check]:
    fns = CHECKS + ([check_updates] if online else [])

    def safe(fn):
        try:
            return fn()
        except Exception as e:                   # noqa: BLE001 – one broken check must not hide the others
            return [Check("Doctor", f"{fn.__name__} could not run", WARN, detail=f"{type(e).__name__}: {e}")]
    with ThreadPoolExecutor(max_workers=6) as pool:
        groups = list(pool.map(safe, fns))
    order = {BAD: 0, WARN: 1, OK: 2}
    return sorted((c for g in groups for c in g), key=lambda c: order[c.state])


# ── safe automatic fixes ─────────────────────────────────────────────
def fix(auto: str) -> str:
    if auto == "apply":
        from . import render
        res = render.apply()
        return "configs written again" if not res.errors else "apply failed: " + "; ".join(res.errors[:2])
    if auto == "reload":
        if os.environ.get("SWAYSOCK"):
            r = _run(["swaymsg", "reload"])
            return "Sway reloaded – bar, notifications and helpers start again" if r.returncode == 0 else r.stdout.strip()
        return "not inside Sway"
    if auto == "portals":
        _run(["systemctl", "--user", "restart", "xdg-desktop-portal-wlr", "xdg-desktop-portal"], timeout=20)
        return "portals restarted"
    return "unknown fix"


def fix_all(checks: list[Check]) -> list[str]:
    done = []
    for a in dict.fromkeys(c.auto for c in checks if c.auto and c.state != OK):
        done.append(f"{a}: {fix(a)}")
    return done


def summary(checks: list[Check]) -> str:
    bad = sum(c.state == BAD for c in checks)
    warn = sum(c.state == WARN for c in checks)
    if not bad and not warn:
        return "Everything looks good."
    return ", ".join(x for x in (f"{bad} problem(s)" if bad else "", f"{warn} hint(s)" if warn else "") if x)


def main(argv: list[str]) -> int:
    checks = run_all(online="--online" in argv)
    mark = {OK: "  ✓ ", WARN: "  ! ", BAD: "  ✗ "}
    group = None
    for c in checks if "--all" in argv or all(c.state == OK for c in checks) else [c for c in checks if c.state != OK]:
        if c.group != group:
            group = c.group
        print(f"{mark[c.state]}[{c.group}] {c.what}" + (f"\n      {c.detail}" if c.detail else "")
              + (f"\n      → {c.fix}" if c.fix and c.state != OK else ""))
    ok = sum(c.state == OK for c in checks)
    print(f"\n{summary(checks)}  ({ok} of {len(checks)} checks fine" + ("" if "--all" in argv else " – `--all` lists them") + ")")
    if "--fix" in argv:
        for line in fix_all(checks) or ["nothing to fix automatically"]:
            print("fix →", line)
    return 1 if any(c.state == BAD for c in checks) else 0
