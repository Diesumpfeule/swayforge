"""Install plan: your profile (selection) becomes executable steps."""
from __future__ import annotations

import asyncio
import shlex
import time
import tomllib
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from . import catalog as cat
from . import paths, render, settings, tomlw
from .system import SysInfo, detect, have, installed_rpms

NERD_FONTS = {
    "JetBrainsMonoNerd": "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz",
    "TerminessNerd": "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Terminus.tar.xz",
}
SPACESHIP_URL = "https://github.com/spaceship-prompt/spaceship-prompt.git"


@dataclass
class Profile:
    selected: set[str] = field(default_factory=set)
    remove: set[str] = field(default_factory=set)
    update_first: bool = True

    @classmethod
    def load(cls, path=None) -> "Profile | None":
        p = path or paths.PROFILE_FILE
        if not p.exists():
            return None
        d = tomllib.loads(p.read_text())
        return cls(set(d.get("selected", [])), set(d.get("remove", [])),
                   bool(d.get("update_first", True)))

    def save(self, path=None) -> None:
        paths.ensure_dirs()
        (path or paths.PROFILE_FILE).write_text(
            "# swayforge profile – your app selection. With this file + settings.toml\n"
            "# you rebuild your system after a reset in one go:\n"
            "#   ./install.sh --yes\n\n"
            + tomlw.dumps({"update_first": self.update_first,
                           "selected": sorted(self.selected),
                           "remove": sorted(self.remove)}))


@dataclass
class Step:
    title: str
    cmds: list[str] = field(default_factory=list)
    func: Callable[[], list[str]] | None = None   # Python step, returns log lines
    critical: bool = False                         # abort on failure?


def build(profile: Profile, s: dict, si: SysInfo | None = None,
          c: cat.Catalog | None = None) -> list[Step]:
    si = si or detect()
    c = c or cat.load()
    items = [i for i in c.resolve(profile.selected) if i.applicable(si) or i.id in profile.selected]
    fmt = {"{user}": si.user, "{fedora}": str(si.fedora or "$(rpm -E %fedora)"),
           "{app}": shlex.quote(str(paths.PKG.parent))}

    def f(cmd: str) -> str:
        for k, v in fmt.items():
            cmd = cmd.replace(k, v)
        return cmd

    steps: list[Step] = [Step("Check admin rights", [
        "sudo -n true 2>/dev/null || { echo 'No cached sudo rights. "
        "Start swayforge via ./install.sh or run sudo -v first.'; exit 1; }"],
        critical=True)]

    pre = [f(x) for i in items for x in i.pre]
    if pre:
        steps.append(Step("Set up package sources", pre))
    coprs = sorted({i.copr for i in items if i.copr})
    if coprs:
        steps.append(Step("Enable COPR repos", [f"sudo dnf copr enable -y {x}" for x in coprs]))
    if profile.update_first:
        steps.append(Step("Update the system", ["sudo dnf upgrade -y --refresh"]))
    remove = installed_rpms(sorted(profile.remove)) if have("rpm") else set(profile.remove)
    if remove:
        steps.append(Step("Remove what you don't need", [
            # Swap Fedora's spin profile for the minimal one first: otherwise removing a
            # spin dependency (e.g. dunst) would take Sway itself with it.
            "if rpm -q sway-config-fedora >/dev/null 2>&1; then "
            "sudo dnf swap -y sway-config-fedora sway-config-minimal; fi",
            "sudo dnf remove -y " + " ".join(sorted(remove)),
        ]))

    pkgs: list[str] = []
    for i in items:
        pkgs += [p for p in i.dnf if p not in pkgs]
    term = s["general"]["terminal"]
    if term not in pkgs:
        pkgs.append(term)
    steps.append(Step(f"Install packages ({len(pkgs)})",
                      ["sudo dnf install -y --skip-unavailable " + " ".join(pkgs)]))

    post = [f(x) for i in items for x in i.post]
    if post:
        steps.append(Step("Set up services and drivers", post))

    flat = [x for i in items for x in i.flatpak]
    if flat:
        steps.append(Step(f"Install Flatpaks ({len(flat)})",
                          ["sudo flatpak install -y --noninteractive flathub " + " ".join(flat)]))

    font_cmds = []
    for name, url in NERD_FONTS.items():
        d = shlex.quote(str(paths.XDG_DATA / "fonts" / name))
        font_cmds += [f"mkdir -p {d}",
                      f"test -n \"$(ls {d} 2>/dev/null)\" || curl -fsSL {url} | tar -xJ -C {d}"]
    steps.append(Step("Install Nerd Fonts (JetBrains Mono + Terminus for retro)",
                      font_cmds + ["fc-cache -f >/dev/null"]))
    if s["shell"]["zsh"] and s["shell"]["spaceship"]:
        sp = shlex.quote(str(paths.SPACESHIP_DIR))
        steps.append(Step("Install the Spaceship prompt", [
            f"if [ -d {sp}/.git ]; then git -C {sp} pull -q --ff-only; "
            f"else git clone -q --depth=1 {SPACESHIP_URL} {sp}; fi"]))
    if s["shell"]["zsh"]:
        steps.append(Step("Make zsh the default shell", [
            f"[ \"$(getent passwd {si.user} | cut -d: -f7)\" = /usr/bin/zsh ] || sudo usermod -s /usr/bin/zsh {si.user}"]))

    def write_configs() -> list[str]:
        detect.cache_clear()          # re-detect SwayFX, sensors … after installing
        settings.save(s)
        profile.save()
        res = render.render_all(s)
        out = [f"{len(res.written)} files written"]
        if res.backup_dir:
            out.append(f"Old configs backed up to {res.backup_dir}")
        out += res.notes + res.errors
        if res.errors:
            raise RuntimeError("\n".join(res.errors))
        return out

    steps.append(Step("Write theme & configs", func=write_configs, critical=True))
    ids = {i.id for i in items}
    if "bootscreen" in ids:
        steps.append(Step("Install the boot screen (rebuilds initramfs)",
                          [f"bash {shlex.quote(str(paths.GEN_DIR / 'boot/apply-boot.sh'))}"]))
    if "tuigreet" in ids:
        steps.append(Step("Install the tuigreet login screen",
                          [f"bash {shlex.quote(str(paths.GEN_DIR / 'boot/apply-login.sh'))}"]))
        s["login"]["greeter"] = "tuigreet"
    return steps


# ── Run ────────────────────────────────────────────────────────
@dataclass
class Event:
    kind: str          # step | line | ok | fail | done
    text: str = ""
    index: int = 0


async def execute(steps: list[Step], dry: bool = False) -> AsyncIterator[Event]:
    paths.ensure_dirs()
    log = open(paths.LOG_FILE, "a")
    log.write(f"\n===== swayforge {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    failed = []
    keepalive = None
    if not dry:
        keepalive = asyncio.create_task(_sudo_keepalive())
    try:
        for n, st in enumerate(steps):
            yield Event("step", st.title, n)
            log.write(f"\n## {st.title}\n")
            ok = True
            if st.func:
                if dry:
                    yield Event("line", "(Python step)")
                else:
                    try:
                        for line in await asyncio.to_thread(st.func):
                            log.write(line + "\n")
                            yield Event("line", line)
                    except Exception as e:  # noqa: BLE001
                        ok = False
                        yield Event("line", f"Error: {e}")
            for cmd in st.cmds:
                yield Event("line", f"$ {cmd}")
                log.write(f"$ {cmd}\n")
                if dry:
                    continue
                proc = await asyncio.create_subprocess_exec(
                    "bash", "-o", "pipefail", "-c", cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    stdin=asyncio.subprocess.DEVNULL)
                assert proc.stdout
                async for raw in proc.stdout:
                    line = raw.decode(errors="replace").rstrip()
                    log.write(line + "\n")
                    if line.strip():
                        yield Event("line", line)
                if await proc.wait() != 0:
                    ok = False
                    yield Event("line", f"⚠ command failed (code {proc.returncode})")
            log.flush()
            if ok:
                yield Event("ok", st.title, n)
            else:
                failed.append(st.title)
                yield Event("fail", st.title, n)
                if st.critical:
                    yield Event("done", "aborted")
                    return
        yield Event("done", "Problems with: " + ", ".join(failed) if failed else "")
    finally:
        if keepalive:
            keepalive.cancel()
        log.close()


async def _sudo_keepalive() -> None:
    while True:
        await asyncio.sleep(60)
        p = await asyncio.create_subprocess_exec("sudo", "-n", "-v",
                                                 stdout=asyncio.subprocess.DEVNULL,
                                                 stderr=asyncio.subprocess.DEVNULL)
        await p.wait()


def run_cli(steps: list[Step], dry: bool = False) -> int:
    """Run without the TUI (for --yes)."""
    async def main() -> int:
        rc = 0
        async for ev in execute(steps, dry):
            if ev.kind == "step":
                print(f"\n\033[1;35m==> [{ev.index + 1}/{len(steps)}] {ev.text}\033[0m", flush=True)
            elif ev.kind == "line":
                print("   " + ev.text, flush=True)
            elif ev.kind == "fail":
                print(f"\033[1;31m✗ {ev.text}\033[0m")
                rc = 1
            elif ev.kind == "done":
                print("\n\033[1;32mDone.\033[0m " + ev.text)
        return rc
    return asyncio.run(main())
