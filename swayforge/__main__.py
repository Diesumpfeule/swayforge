"""swayforge – command line.

  swayforge                    settings app (TUI)
  swayforge gui                swayforge app – graphical settings with live previews
  swayforge screenshare        check and repair screen sharing (Discord/Vesktop, browsers)
  swayforge widgets [restart|stop]  desktop widgets (clock, player, system monitor, Clippy)
  swayforge install            installer (TUI)
  swayforge install --yes      install the saved profile without questions
  swayforge apply              regenerate configs from settings.toml + reload
  swayforge theme NAME         switch theme (--list, --next, --from-wallpaper IMAGE)
  swayforge layout NAME        switch bar/UI layout (--list, --next)
  swayforge boot               install the boot screen (Plymouth)
  swayforge login              install the tuigreet login screen
  swayforge import-sway FILE   take over an existing Sway config into custom.conf
  swayforge mount [add|remove]  mount drives permanently at /mnt/NAME (fstab)
  swayforge steam [...]        Steam shader-cache helper (add-on steamtune: limits, move cache, update window)
  swayforge wipe DEVICE        wipe + format a USB stick / SD card / external SSD (asks first)
  swayforge version / update    installed version · get the newest from GitHub
  swayforge export FILE        back up settings + your tweaks
  swayforge restore FILE       … and bring them back after a reset
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(epilog="Proof of concept, written by Claude (Anthropic). No warranty – use at your own risk.", prog="swayforge", description="Set up and theme Fedora Sway")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("install", help="install apps & desktop")
    p.add_argument("--yes", "-y", action="store_true", help="install the saved profile without questions")
    p.add_argument("--profile", type=Path, help="use another profile file")
    p.add_argument("--dry-run", action="store_true", help="only show what would happen")

    p = sub.add_parser("apply", help="regenerate configs and reload")
    p.add_argument("--no-reload", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("theme", help="switch colour theme")
    p.add_argument("name", nargs="?")
    p.add_argument("--from-wallpaper", metavar="IMAGE", help="make a theme from an image, set it as wallpaper")
    p.add_argument("--mode", choices=["auto", "dark", "light"], default="auto", help="with --from-wallpaper")
    p.add_argument("--save", metavar="NAME", help="with --from-wallpaper: keep it as your own theme NAME")
    p.add_argument("--list", action="store_true")
    p.add_argument("--next", action="store_true")

    p = sub.add_parser("layout", help="switch bar/UI layout")
    p.add_argument("name", nargs="?")
    p.add_argument("--list", action="store_true")
    p.add_argument("--next", action="store_true")

    sub.add_parser("boot", help="install the boot screen (needs sudo, rebuilds initramfs)")
    sub.add_parser("login", help="install the tuigreet login screen (needs sudo)")

    p = sub.add_parser("import-sway", help="take over an existing Sway config")
    p.add_argument("file", type=Path)
    p = sub.add_parser("export", help="back up your settings")
    p.add_argument("file", nargs="?", default="~/swayforge-backup.tar.gz")
    p = sub.add_parser("restore", help="restore a backup")
    p.add_argument("file")

    p = sub.add_parser("widgets", help="desktop widgets: run | restart | stop | overview (all workspaces big)")
    p.add_argument("action", nargs="?", default="run", choices=["run", "restart", "stop", "overview"])
    p = sub.add_parser("screenshare", help="check and repair screen sharing (Discord/Vesktop, browsers)")
    p.add_argument("--report", action="store_true", help="write everything needed to find the cause into one file")
    p = sub.add_parser("gui", help="swayforge app – graphical settings with live previews")
    p.add_argument("--browser", action="store_true", help="open in a browser instead of a native window")
    p.add_argument("--serve", action="store_true", help="only serve and print the address")
    p = sub.add_parser("settings", help="settings app (default)")
    p.add_argument("--page", default="", help="open a page directly (audio, network, layout, boot …)")
    p = sub.add_parser("sound", help="system sounds: test | play EVENT | build")
    p.add_argument("action", choices=["test", "play", "build"])
    p.add_argument("event", nargs="?", default="bell")
    sub.add_parser("power", help="power menu (Rofi)")
    p = sub.add_parser("livewall", help="animated wallpaper: make aurora|tide | guard | stop")
    p.add_argument("action", choices=["make", "guard", "stop"])
    p.add_argument("name", nargs="?", default="aurora")
    p = sub.add_parser("screensaver", help="animated screensaver instead of a plain lock: list | preview NAME | start | wake")
    p.add_argument("action", choices=["list", "preview", "run", "start", "wake"])
    p.add_argument("name", nargs="?", default="")
    sub.add_parser("start", help="start menu (Rofi)")
    sub.add_parser("keys", help="shortcut overview (Rofi)")
    sub.add_parser("version", help="installed versions + whether GitHub has newer ones")
    sub.add_parser("update", help="get the newest swayforge + wolfforge from GitHub and apply them")
    p = sub.add_parser("hello", help="animated ASCII greeting, then fastfetch (terminal start)")
    p.add_argument("--anim", choices=["intro", "spin", "donut", "cube", "fire", "video", "off"],
                   help="try another animation (default: the one from Settings)")
    p.add_argument("--seconds", type=float, help="how long it plays (0 = until a key)")
    p.add_argument("--video", help="GIF or video file for --anim video")
    sub.add_parser("undo", help="back to the version before the last apply")
    p = sub.add_parser("history", help="earlier versions: list | restore NUMBER")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p = sub.add_parser("privacy", help="privacy guard: which app may use camera, mic, network, files …")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="[--json] | revoke APP PERMISSION")
    p = sub.add_parser("clip", help="clipboard history: (pick) | list [TEXT] | clear [--all] | pause | resume")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    sub.add_parser("session", help="at Sway start: GTK settings, swayidle")
    p = sub.add_parser("osd", help="volume/brightness with on-screen display")
    p.add_argument("kind", choices=["volume", "mic", "brightness"])
    p.add_argument("arg", nargs="?", default="mute")
    p = sub.add_parser("gamemode", help="toggle gaming mode")
    p.add_argument("action", nargs="?", default="toggle", choices=["toggle", "status"])
    p.add_argument("--text", action="store_true", help="text label instead of icon")
    p = sub.add_parser("scan", help="malware scan with ClamAV (downloads | home | drives | PATH)")
    p.add_argument("target", nargs="?", default="downloads")
    p.add_argument("--no-quarantine", action="store_true", help="only report, don't move files")
    p.add_argument("--quiet", action="store_true", help="no output, just a notification (for the timer)")
    p = sub.add_parser("audit", help="rootkit check (rkhunter, chkrootkit) or system audit (Lynis)")
    p.add_argument("what", choices=["rootkit", "system"], nargs="?", default="rootkit")
    p = sub.add_parser("mount", help="mount a drive permanently at /mnt/NAME (fstab)")
    p.add_argument("action", nargs="?", default="list", choices=["list", "add", "remove"])
    p.add_argument("device", nargs="?", help="add: partition, e.g. nvme1n1p1 · remove: NAME or /mnt/NAME")
    p.add_argument("name", nargs="?", help="add: folder name under /mnt")
    p = sub.add_parser("steam", help="Steam shader-cache helper (optional add-on: steamtune)")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="passed on to steamtune")
    p = sub.add_parser("wipe", help="wipe + format a removable drive (USB, SD, external SSD)")
    p.add_argument("device", nargs="?", help="e.g. sdb or mmcblk0 – without it: list the drives")
    p.add_argument("--mode", default="quick", choices=["quick", "zero", "discard"])
    p.add_argument("--fs", default="exfat", choices=["exfat", "vfat", "ext4", "none"])
    p.add_argument("--label", default="USB")
    p.add_argument("--size", type=int, default=0, help=argparse.SUPPRESS)
    p.add_argument("--serial", default=None, help=argparse.SUPPRESS)
    p.add_argument("--confirm", default="", help=argparse.SUPPRESS)
    p = sub.add_parser("find", help="find an app and show the install command (Fedora → COPR → RPM Fusion → Flathub)")
    p.add_argument("term", nargs="+", help="e.g. fastfetch, steam, discord")
    p = sub.add_parser("wallpapers", help="wallpaper collections: list | install PACK[/FOLDER] …")
    p.add_argument("action", choices=["list", "install"], nargs="?", default="list")
    p.add_argument("what", nargs="*", help="dharmx/nord  dharmx/anime  aesthetic (= whole pack)")
    p = sub.add_parser("shot", help="screenshot")
    p.add_argument("mode", choices=["area", "output", "edit"], nargs="?", default="area")

    a = ap.parse_args(argv)

    if a.cmd == "widgets":
        from . import widgets
        return widgets.main(a.action)

    if a.cmd in ("undo", "history"):
        from . import history
        return history.main(["undo"] if a.cmd == "undo" else a.rest)

    if a.cmd == "privacy":
        from . import privacy
        return privacy.main(a.rest)

    if a.cmd == "screenshare":
        from . import render
        return render.screenshare_report() if a.report else render.screenshare_check(fix=True)

    if a.cmd == "gui":
        from .gui import main as gui_main
        return gui_main((["--browser"] if a.browser else []) + (["--serve"] if a.serve else []))

    if a.cmd in (None, "settings"):
        from .tui.settings_app import main as run
        run(getattr(a, "page", ""))
        return 0

    if a.cmd == "install":
        from . import plan, settings
        if not a.dry_run and os.geteuid() != 0 and subprocess.run(
                ["sudo", "-n", "true"], capture_output=True).returncode != 0:
            print("swayforge needs admin rights to install packages – enter your password once:")
            if subprocess.run(["sudo", "-v"]).returncode != 0:
                print("No admin rights – nothing was installed.")
                return 1
        if a.yes or a.dry_run:
            prof = plan.Profile.load(a.profile)
            if not prof:
                print("No profile found. Run the installer once without --yes first.")
                return 1
            steps = plan.build(prof, settings.load())
            return plan.run_cli(steps, dry=a.dry_run)
        from .tui.installer import main as run
        run()
        return 0

    if a.cmd == "apply":
        from . import render
        if a.dry_run:
            res = render.render_all(dry=True)
        elif a.no_reload:
            res = render.render_all()
        else:
            res = render.apply()
        for f in res.written:
            print("written:", f)
        if res.backup_dir:
            print("backup:", res.backup_dir)
        for n in res.notes:
            print(n)
        for e in res.errors:
            print("ERROR:", e, file=sys.stderr)
        return 1 if res.errors else 0

    if a.cmd in ("boot", "login"):
        from . import boot, render
        render.render_all()
        script = boot.BOOT_DIR / ("apply-boot.sh" if a.cmd == "boot" else "apply-login.sh")
        return subprocess.call(["bash", str(script)])

    if a.cmd == "theme":
        from . import tools
        if a.from_wallpaper:
            return tools.theme_from_wallpaper(a.from_wallpaper, a.mode, a.save or "")
        return tools.theme_cmd(a.name, a.next, a.list)
    if a.cmd == "layout":
        from . import tools
        return tools.layout_cmd(a.name, a.next, a.list)

    if a.cmd == "import-sway":
        from . import render
        from .importer import import_sway_config
        try:
            print(import_sway_config(a.file.expanduser()))
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        render.apply()
        return 0

    if a.cmd == "scan":
        from . import security, settings
        q = settings.load()["security"]["quarantine"] and not a.no_quarantine
        return security.scan(a.target, quarantine=q, quiet=a.quiet)
    if a.cmd == "mount":
        from . import mounts
        if a.action == "add":
            if not a.device:
                print("usage: swayforge mount add DEVICE [NAME]")
                return 2
            c = next((x for x in mounts.candidates() if x["name"] == a.device.removeprefix("/dev/")), None)
            return mounts.add_main(a.device, a.name or (mounts.default_name(c) if c else ""))
        if a.action == "remove":
            return mounts.remove_main(a.device or "")
        print("Mounted by swayforge:")
        for e in mounts.entries():
            print(f"  {e['target']:<22} {e['label']}  {'(mounted)' if e['mounted'] else '(not mounted)'}")
        print("Can be added:")
        for c in mounts.candidates():
            print("  " + mounts.describe(c))
        return 0

    if a.cmd in ("version", "update"):
        from . import update
        if a.cmd == "update":
            return subprocess.call(["bash", "-c", update.script()])
        for n in update.APPS:
            print(update.describe(n, *update.status(n)).replace("[green]", "").replace("[yellow]", "")
                  .replace("[dim]", "").replace("[/]", ""))
        return 0

    if a.cmd == "find":
        from . import apps, finder
        res = finder.search_all(" ".join(a.term))
        finder.mark_installed(res.hits, set(apps.rpm_db()), set(apps.flatpak_db()))
        print(finder.describe(res))
        return 0 if res.hits else 1

    if a.cmd == "wallpapers":
        from . import wallpacks
        if a.action == "list":
            for p in wallpacks.load():
                print(f"{p.name}  [{p.id}]  {p.total_files} files, {p.total_mb} MB  –  {p.license}")
                print(f"  {p.blurb}")
                print("  " + ", ".join(f"{c.id}({c.mb}MB{'*' if wallpacks.is_installed(p, c) else ''})"
                                      for c in p.categories))
            return 0
        keys = []
        for w in a.what:
            pid, _, cid = w.partition("/")
            pk = wallpacks.get(pid)
            if not pk:
                print(f"unknown collection: {pid}", file=sys.stderr)
                return 2
            keys += [wallpacks.key(pid, cid)] if cid else [wallpacks.key(pid, c.id) for c in pk.categories]
        if not wallpacks.resolve(keys):
            print("nothing to install – see: swayforge wallpapers list", file=sys.stderr)
            return 2
        print(f"about {wallpacks.total_mb(keys)} MB")
        return subprocess.call(["bash", "-o", "pipefail", "-c", wallpacks.script(keys)])

    if a.cmd == "livewall":
        from . import livewall as lw
        if a.action == "guard":
            return lw.guard()
        if a.action == "stop":
            lw.stop()
            return 0
        if a.name not in lw.STYLES:
            print("styles:", ", ".join(lw.STYLES))
            return 2
        print("Rendering a seamless loop in your theme colours (about half a minute) …")
        try:
            out = lw.generate(a.name)
        except RuntimeError as e:
            print(f"✗ {e}")
            return 1
        print(f"✓ {out}\n  Pick it on the Wallpapers page (press ↻ first).")
        return 0

    if a.cmd == "screensaver":
        from . import screensaver as sv
        if a.action == "list":
            for k, v in sv.SAVERS.items():
                print(f"{k:10} {v}")
            return 0
        if a.action == "preview":
            return sv.preview(a.name or "matrix")
        if a.action == "run":
            return sv.run_scene(a.name or "matrix", False)
        return sv.start() if a.action == "start" else sv.wake()

    if a.cmd == "hello":
        from . import anim
        return anim.hello(a.anim, a.seconds, a.video)

    if a.cmd == "steam":
        exe = Path.home() / ".local/bin/steamtune"
        if not exe.exists():
            print("steamtune is an optional add-on – select it in the installer (swayforge install → Own tools).")
            return 1
        return subprocess.call([str(exe), *a.rest])
    if a.cmd == "wipe":
        from . import cleanup
        if not a.device:
            drives = cleanup.wipeable_drives()
            print("\n".join(cleanup.drive_label(d) for d in drives) or "No removable drive found.")
            return 0
        rc = cleanup.wipe_main(a.device, a.mode, a.fs, a.label, a.size, a.confirm, a.serial)
        return rc

    if a.cmd == "audit":
        from . import security
        rep = security.report_path("rootkit" if a.what == "rootkit" else "audit")
        cmd = security.rootkit_cmd(rep) if a.what == "rootkit" else security.audit_cmd(rep)
        rc = subprocess.call(["bash", "-c", cmd])
        print(f"\nReport: {rep}  ·  {security.describe(rep, security.summarize(rep))}")
        return rc

    if a.cmd == "export":
        from . import tools
        return tools.export(a.file)
    if a.cmd == "restore":
        from . import tools
        return tools.import_(a.file)

    from . import render, tools
    if a.cmd == "sound":
        tools.sound(a.action, a.event)
    elif a.cmd == "power":
        tools.power()
    elif a.cmd == "start":
        tools.start()
    elif a.cmd == "keys":
        tools.keys()
    elif a.cmd == "clip":
        from . import clipboard
        return clipboard.main(a.rest)
    elif a.cmd == "shot":
        tools.shot(a.mode)
    elif a.cmd == "osd":
        tools.osd(a.kind, a.arg)
    elif a.cmd == "gamemode":
        tools.gamemode(a.action, a.text)
    elif a.cmd == "session":
        render.session()
    return 0


if __name__ == "__main__":
    from .crash import guard
    sys.exit(guard("swayforge", main))
