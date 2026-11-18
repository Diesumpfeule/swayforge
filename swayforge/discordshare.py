"""Discord screen sharing on Sway: the parts that have to line up, set up and checked one by one.

Discord is Electron. Started under XWayland it can only capture other XWayland windows – the
screen picker stays empty or shows black. Real screen sharing needs Discord running natively on
Wayland with Chromium's PipeWire capturer, plus PipeWire, xdg-desktop-portal and its wlr backend.

xwaylandvideobridge is deliberately not used: it is built for KDE, is reported not to work on
Sway, and is no longer maintained.

`swayforge discordshare fix`   – steps 1-5 below (asks for the sudo password only if packages are missing)
`swayforge discordshare check` – pass/fail per item, changes nothing

Everything happens in your home folder (except installing packages); files that are replaced are
backed up to ~/.local/share/swayforge/backups/ first.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .fsutil import atomic_write
from .system import have, run

MARK = "swayforge generated"          # same marker as render.MARK (not imported: render imports us)
PACKAGES = ["pipewire", "wireplumber", "xdg-desktop-portal", "xdg-desktop-portal-wlr", "xdg-desktop-portal-gtk"]
FLAGS = ["--enable-features=UseOzonePlatform,WebRTCPipeWireCapturer", "--ozone-platform=wayland"]
FEATURES = ["UseOzonePlatform", "WebRTCPipeWireCapturer"]
PORTALS_CONF = (f"# {MARK} – don't edit\n[preferred]\ndefault=gtk\n"
                "org.freedesktop.impl.portal.ScreenCast=wlr\norg.freedesktop.impl.portal.Screenshot=wlr\n")
ENV_LINE = ("dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY SWAYSOCK "
            "XDG_CURRENT_DESKTOP=sway XDG_SESSION_TYPE=wayland")
# services: (unit, enable it?) – the portals are started over D-Bus and can't be enabled, only restarted
SERVICES = [("pipewire", True), ("pipewire-pulse", True), ("wireplumber", True),
            ("xdg-desktop-portal", False), ("xdg-desktop-portal-wlr", False)]
FLATPAK_DIRS = (Path("/var/lib/flatpak"),)


def portals_conf() -> Path:
    return paths.XDG_CONFIG / "xdg-desktop-portal/sway-portals.conf"


def apps_dir() -> Path:
    return paths.XDG_DATA / "applications"


# ── backups ───────────────────────────────────────────────────────────
_STAMP = time.strftime("%Y%m%d-%H%M%S")


def backup(path: Path) -> Path:
    """Copy a file into swayforge's backup folder before it's changed. Returns where it went."""
    rel = path.relative_to(paths.HOME) if path.is_relative_to(paths.HOME) else Path(path.name)
    dest = paths.BACKUP_DIR / _STAMP / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def _home(p: Path | str) -> str:
    return str(p).replace(str(paths.HOME), "~", 1)


# ── step 1: packages ──────────────────────────────────────────────────
def missing_packages() -> list[str]:
    if not have("rpm"):
        return list(PACKAGES)
    return [p for p in PACKAGES if run(["rpm", "-q", p]).returncode != 0]


def install_packages() -> list[str]:
    missing = missing_packages()
    if not missing:
        return ["packages: all installed (" + ", ".join(PACKAGES) + ")"]
    if not have("dnf"):
        return ["packages: dnf not found – install by hand: " + " ".join(missing)]
    print("Installing " + " ".join(missing) + " (sudo asks for your password) …", flush=True)
    r = _run_visible(["sudo", "dnf", "install", "-y", *missing])
    still = missing_packages()
    if r != 0 or still:
        return ["packages: NOT installed: " + " ".join(still or missing) + f" (dnf exit {r})"]
    return ["packages: installed " + " ".join(missing)]


def _run_visible(cmd: list[str]) -> int:
    """Run with the terminal attached (sudo needs to ask for the password)."""
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        return 127


# ── step 2: portal routing ────────────────────────────────────────────
def routes_to_wlr(text: str) -> bool:
    keys = {}
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif "=" in line and not line.startswith("#") and section == "[preferred]":
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    return all(keys.get(f"org.freedesktop.impl.portal.{x}", "").split(";")[0] == "wlr"
               for x in ("ScreenCast", "Screenshot"))


def write_portals_conf() -> list[str]:
    f = portals_conf()
    if not f.exists():
        atomic_write(f, PORTALS_CONF)
        return [f"portals: created {_home(f)}"]
    old = f.read_text(errors="replace")
    if old == PORTALS_CONF:
        return [f"portals: {_home(f)} already routes screen sharing to wlr"]
    if MARK not in old and routes_to_wlr(old):
        return [f"portals: your own {_home(f)} already routes screen sharing to wlr – left as it is"]
    saved = backup(f)
    atomic_write(f, PORTALS_CONF)
    return [f"portals: replaced {_home(f)} (old version: {_home(saved)})"]


# ── step 3: session environment ───────────────────────────────────────
def sway_config_ok(text: str) -> bool:
    return any(l.strip().startswith("exec") and "dbus-update-activation-environment" in l
               and "XDG_CURRENT_DESKTOP=sway" in l and "XDG_SESSION_TYPE=wayland" in l
               for l in text.splitlines())


def fix_session_env() -> list[str]:
    out = []
    cfg = paths.XDG_CONFIG / "sway/config"
    text = cfg.read_text(errors="replace") if cfg.exists() else ""
    if sway_config_ok(text):
        out.append("session: the Sway config already exports XDG_CURRENT_DESKTOP / XDG_SESSION_TYPE")
    elif cfg.exists() and MARK not in text:
        out.append(f"session: {_home(cfg)} isn't swayforge's (you took it over) – not touched. Add this line yourself:\n"
                   f"      exec {ENV_LINE}")
    else:
        from . import render                     # regenerates the Sway config (and backs up what it replaces)
        res = render.render_all()
        if res.errors:
            out.append("session: could not regenerate the Sway config: " + res.errors[0].splitlines()[0])
        else:
            out.append(f"session: Sway config regenerated – it exports the variables at every login"
                       + (f" (backups: {_home(res.backup_dir)})" if res.backup_dir else ""))
    if os.environ.get("WAYLAND_DISPLAY") and have("dbus-update-activation-environment"):
        env = dict(os.environ, XDG_CURRENT_DESKTOP="sway", XDG_SESSION_TYPE="wayland")
        names = [n for n in ("DISPLAY", "WAYLAND_DISPLAY", "SWAYSOCK") if env.get(n)]
        r = run(["dbus-update-activation-environment", "--systemd", *names,
                 "XDG_CURRENT_DESKTOP=sway", "XDG_SESSION_TYPE=wayland"], timeout=15, env=env)
        out.append("session: variables handed to the running session" if r.returncode == 0 else
                   "session: could not update the running session – log out and in again")
    else:
        out.append("session: not inside Sway right now – takes effect at the next Sway login")
    return out


# ── step 4: Discord / Vesktop launchers ───────────────────────────────
@dataclass
class Client:
    name: str          # "Discord" / "Vesktop"
    kind: str          # "Flatpak" / "RPM" / "binary"
    desktop: str       # file name in ~/.local/share/applications
    program: str       # program to start (binary installs and generated entries)
    app_id: str = ""   # Flatpak only


def _flatpak_installed(app: str) -> bool:
    return any((d / "app" / app).is_dir() for d in (*FLATPAK_DIRS, paths.XDG_DATA / "flatpak"))


def _rpm(pkg: str) -> bool:
    return have("rpm") and run(["rpm", "-q", pkg]).returncode == 0


def _binary_discord() -> str:
    for p in (paths.XDG_DATA / "Discord/Discord", paths.XDG_DATA / "discord/Discord", paths.HOME / "Discord/Discord",
              Path("/opt/discord/Discord"), Path("/opt/Discord/Discord")):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return shutil.which("Discord") or shutil.which("discord") or ""


def find_clients() -> list[Client]:
    out = []
    if _flatpak_installed("com.discordapp.Discord"):
        out.append(Client("Discord", "Flatpak", "com.discordapp.Discord.desktop", "flatpak", "com.discordapp.Discord"))
    if _rpm("discord"):
        out.append(Client("Discord", "RPM", "discord.desktop", "/usr/bin/discord"))
    elif _binary_discord():
        out.append(Client("Discord", "binary", "discord.desktop", _binary_discord()))
    if _flatpak_installed("dev.vencord.Vesktop"):
        out.append(Client("Vesktop", "Flatpak", "dev.vencord.Vesktop.desktop", "flatpak", "dev.vencord.Vesktop"))
    if _rpm("vesktop"):
        out.append(Client("Vesktop", "RPM", "vesktop.desktop", "/usr/bin/vesktop"))
    elif shutil.which("vesktop") and not str(shutil.which("vesktop")).startswith("/var/lib/flatpak"):
        out.append(Client("Vesktop", "binary", "vesktop.desktop", shutil.which("vesktop") or "vesktop"))
    return out


def system_desktop(c: Client) -> Path | None:
    """The desktop entry the system installed for this client (what we start from)."""
    dirs = [Path("/usr/share/applications"), Path("/usr/local/share/applications")]
    if c.kind == "Flatpak":
        dirs = [paths.XDG_DATA / "flatpak/exports/share/applications", Path("/var/lib/flatpak/exports/share/applications")]
    for d in dirs:
        if (d / c.desktop).is_file():
            return d / c.desktop
    return None


def _dq(tok: str) -> str:
    """Quote one Exec argument the way desktop files want it (double quotes, not shell quotes)."""
    if tok and not re.search(r'[\s"\'\\><~|&;$*?#()`]', tok):
        return tok
    return '"' + re.sub(r'(["`$\\])', r"\\\1", tok) + '"'


def with_flags(exec_value: str, app_id: str = "") -> str:
    """An Exec= value with the Wayland/PipeWire flags added (once). Flatpak: after the app id;
    otherwise right after the program. Other --enable-features are kept and merged."""
    try:
        toks = shlex.split(exec_value)
    except ValueError:
        toks = exec_value.split()
    feats: list[str] = []
    kept = []
    for t in toks:
        if t.startswith("--enable-features="):
            feats += [f for f in t.split("=", 1)[1].split(",") if f]
        elif t.startswith("--ozone-platform="):
            continue
        else:
            kept.append(t)
    feats += [f for f in FEATURES if f not in feats]
    flags = ["--enable-features=" + ",".join(feats), "--ozone-platform=wayland"]
    if app_id and app_id in kept:
        at = kept.index(app_id) + 1
    else:
        at = 0
        if kept and kept[0] == "env":                # "env VAR=x … program": the flags go after the program
            at = 1
            while at < len(kept) and "=" in kept[at]:
                at += 1
        at = min(at + 1, len(kept))
    kept[at:at] = flags
    return " ".join(_dq(t) for t in kept)


def desktop_text(c: Client, source: str | None) -> str:
    """Our override: the source entry with flags on every Exec= line, or a minimal one."""
    if not source:
        source = (f"[Desktop Entry]\nType=Application\nName={c.name}\nComment={c.name} on Wayland (screen sharing)\n"
                  f"Exec={_dq(c.program)} %U\nIcon={c.name.lower()}\nCategories=Network;InstantMessaging;\n"
                  "StartupWMClass=" + c.name.lower() + "\n")
    out = [f"# {MARK} – Wayland + PipeWire flags for screen sharing (swayforge discordshare). Delete this file to undo."]
    for line in source.splitlines():
        if line.startswith("#") and MARK in line:
            continue                                   # our own old header
        if line.startswith("Exec="):
            line = "Exec=" + with_flags(line[5:], c.app_id)
        out.append(line)
    return "\n".join(out).rstrip("\n") + "\n"


def flatpak_override(app_id: str) -> bool:
    """Flatpak: may talk to Wayland and PipeWire, and Electron prefers Wayland."""
    if not have("flatpak"):
        return False
    return run(["flatpak", "override", "--user", "--socket=wayland", "--filesystem=xdg-run/pipewire-0",
                "--env=ELECTRON_OZONE_PLATFORM_HINT=wayland", app_id], timeout=20).returncode == 0


def write_launchers() -> list[str]:
    clients = find_clients()
    if not clients:
        return ["launchers: no Discord or Vesktop found (RPM, Flatpak or binary) – install one, then run this again"]
    out = []
    for c in clients:
        target = apps_dir() / c.desktop
        current = target.read_text(errors="replace") if target.exists() else None
        if current is not None:
            src_text = current                        # yours or ours from last time: keep it, just (re)add the flags
        else:
            src = system_desktop(c)
            src_text = src.read_text(errors="replace") if src else None
        new = desktop_text(c, src_text)
        label = f"{c.name} ({c.kind})"
        if current == new:
            out.append(f"launchers: {label} – {_home(target)} already has the flags")
        else:
            note = ""
            if current is not None:
                note = f" (old version: {_home(backup(target))})"
            atomic_write(target, new)
            out.append(f"launchers: {label} – wrote {_home(target)}{note}")
        if c.kind == "Flatpak":
            out.append(f"launchers: {label} – flatpak override "
                       + ("set (Wayland, PipeWire)" if flatpak_override(c.app_id) else "FAILED"))
    if have("update-desktop-database"):
        run(["update-desktop-database", str(apps_dir())], timeout=20)
    return out


# ── step 5: services ──────────────────────────────────────────────────
def unit_state(unit: str) -> str:
    """enabled / disabled / static / masked / … or "" when there is no such user unit."""
    r = run(["systemctl", "--user", "list-unit-files", f"{unit}.service", "--no-legend"])
    parts = r.stdout.split()
    return parts[1] if r.returncode == 0 and len(parts) > 1 else ""


def restart_services() -> list[str]:
    if not have("systemctl"):
        return ["services: systemctl not found – nothing restarted"]
    out, restart = [], []
    for unit, enable in SERVICES:
        state = unit_state(unit)
        if not state:
            if unit != "pipewire-pulse":
                out.append(f"services: {unit} not found (is the package installed?)")
            continue
        if state == "masked":
            out.append(f"services: {unit} is masked – left alone (systemctl --user unmask {unit} if you want it)")
            continue
        if enable and state == "disabled":
            r = run(["systemctl", "--user", "enable", f"{unit}.service"], timeout=20)
            out.append(f"services: {unit} enabled" if r.returncode == 0 else f"services: could not enable {unit}")
        restart.append(unit)
    for unit in restart:
        r = run(["systemctl", "--user", "restart", f"{unit}.service"], timeout=30)
        out.append(f"services: {unit} restarted" if r.returncode == 0 else
                   f"services: {unit} did not restart – journalctl --user -u {unit} -n 30")
    return out


# ── the two actions ───────────────────────────────────────────────────
def fix() -> list[str]:
    out = []
    for name, step in (("1/5 packages", install_packages), ("2/5 portal config", write_portals_conf),
                       ("3/5 session environment", fix_session_env), ("4/5 Discord launchers", write_launchers),
                       ("5/5 services", restart_services)):
        print(f"── {name}", flush=True)
        try:
            lines = step()
        except Exception as e:                     # noqa: BLE001 – one step failing must not stop the rest
            lines = [f"{name}: failed: {type(e).__name__}: {e}"]
        for l in lines:
            print("  " + l, flush=True)
        out += lines
    return out


@dataclass
class Item:
    ok: bool
    what: str
    hint: str = ""


def _running_clients() -> list[tuple[str, bool]]:
    """(program, started with the Wayland flag) for every running Discord/Vesktop main process."""
    found = []
    for d in Path("/proc").glob("[0-9]*"):
        try:
            argv = (d / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in argv if a]
        if not args or any(a.startswith("--type=") for a in args):
            continue                                  # Electron helper processes
        prog = os.path.basename(args[0])
        if prog.lower() in ("discord", "vesktop", "electron") and any("discord" in a.lower() or "vesktop" in a.lower()
                                                                      for a in args[:3]):
            found.append((prog, "--ozone-platform=wayland" in args))
    return found


def check() -> list[Item]:
    items: list[Item] = []
    rpm = have("rpm")
    for p in PACKAGES:
        items.append(Item(rpm and run(["rpm", "-q", p]).returncode == 0, f"package {p} installed", f"sudo dnf install {p}"))
    sysd = have("systemctl")
    for unit in ("pipewire", "wireplumber", "xdg-desktop-portal", "xdg-desktop-portal-wlr"):
        state = run(["systemctl", "--user", "is-active", unit]).stdout.strip() if sysd else "no systemctl"
        items.append(Item(state == "active", f"service {unit} running ({state or 'unknown'})",
                          f"systemctl --user restart {unit}   ·   journalctl --user -u {unit} -n 30"))
    f = portals_conf()
    items.append(Item(f.exists() and routes_to_wlr(f.read_text(errors="replace")),
                      f"{_home(f)} routes ScreenCast + Screenshot to wlr", "swayforge discordshare fix"))
    env = run(["systemctl", "--user", "show-environment"]).stdout if sysd else ""
    for want in ("XDG_CURRENT_DESKTOP=sway", "XDG_SESSION_TYPE=wayland"):
        items.append(Item(want in env.split("\n"), f"session environment has {want}",
                          "swayforge discordshare fix, then log out and in again"))
    items.append(Item("WAYLAND_DISPLAY=" in env, "session environment has WAYLAND_DISPLAY", "only set inside a Sway session"))
    cfg = paths.XDG_CONFIG / "sway/config"
    items.append(Item(cfg.exists() and sway_config_ok(cfg.read_text(errors="replace")),
                      "Sway config exports both at login (dbus-update-activation-environment)", "swayforge discordshare fix"))
    clients = find_clients()
    if not clients:
        items.append(Item(False, "Discord or Vesktop installed", "none found (RPM, Flatpak or binary)"))
    for c in clients:
        label = f"{c.name} ({c.kind})"
        target = apps_dir() / c.desktop
        text = target.read_text(errors="replace") if target.exists() else ""
        execs = [l for l in text.splitlines() if l.startswith("Exec=")]
        ok = bool(execs) and all(all(f in l for f in FEATURES) and "--ozone-platform=wayland" in l for l in execs)
        items.append(Item(ok, f"{label} launcher has the Wayland + PipeWire flags ({_home(target)})",
                          "swayforge discordshare fix"))
        if c.kind == "Flatpak":
            o = run(["flatpak", "override", "--user", "--show", c.app_id]).stdout if have("flatpak") else ""
            items.append(Item("wayland" in o and "pipewire-0" in o, f"{label} Flatpak may use Wayland and PipeWire",
                              "swayforge discordshare fix"))
    for prog, flagged in _running_clients():
        items.append(Item(flagged, f"running {prog} was started with --ozone-platform=wayland",
                          "quit it completely (also from the tray) and start it from the app menu"))
    return items


def print_check(items: list[Item]) -> int:
    print("Discord screen sharing on Sway:\n")
    for i in items:
        print(("  PASS  " if i.ok else "  FAIL  ") + i.what + ("" if i.ok or not i.hint else f"\n          → {i.hint}"))
    bad = sum(not i.ok for i in items)
    print(f"\n{len(items) - bad} passed, {bad} failed.")
    if not bad:
        print("Quit Discord completely (also from the tray) and start it from the app menu, then share a screen.")
    return 0 if not bad else 1


def main(argv: list[str]) -> int:
    act = argv[0] if argv else "check"
    if act == "fix":
        fix()
        print()
        return print_check(check())
    if act == "check":
        return print_check(check())
    print("usage: swayforge discordshare [fix|check]")
    return 2
