"""Version info and one-click updates for swayforge and wolfforge from GitHub."""
from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

from . import __version__, paths

OWNER = "Diesumpfeule"
APPS = {
    # name: (app dir, default source clone, install.sh flag that installs without questions)
    "swayforge": (paths.XDG_DATA / "swayforge/app", paths.XDG_DATA / "swayforge/src", "--update"),
    "wolfforge": (paths.XDG_DATA / "wolfforge/app", paths.XDG_DATA / "wolfforge/src", "--apply"),
}


def url(name: str) -> str:
    return f"https://github.com/{OWNER}/{name}"


def local(name: str) -> dict:
    """What's installed: version, commit, date, source folder (from build.json written by install.sh)."""
    app, src, _flag = APPS[name]
    info = {"installed": app.is_dir(), "version": "", "commit": "", "date": "", "source": ""}
    try:
        info.update(json.loads((app / "build.json").read_text()))
    except (OSError, ValueError):
        pass
    if name == "swayforge" and not info["version"]:
        info["version"] = __version__
    if not info["version"]:
        init = app / name / "__init__.py"
        try:
            for line in init.read_text().splitlines():
                if line.startswith("__version__"):
                    info["version"] = line.split("=", 1)[1].strip().strip('"\'')
        except OSError:
            pass
    return info


def remote(name: str) -> str:
    """Newest commit on GitHub ('' when offline)."""
    try:
        r = subprocess.run(["git", "ls-remote", url(name), "HEAD"], capture_output=True, text=True, timeout=12)
        return r.stdout.split()[0] if r.returncode == 0 and r.stdout.strip() else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def status(name: str) -> tuple[dict, str, str]:
    """(local info, remote commit, verdict) – verdict: current | update | unknown | missing."""
    info = local(name)
    if not info["installed"]:
        return info, "", "missing"
    rem = remote(name)
    if not rem or not info["commit"]:
        return info, rem, "unknown"
    return info, rem, "current" if rem.startswith(info["commit"]) or info["commit"].startswith(rem) else "update"


def describe(name: str, info: dict, rem: str, verdict: str) -> str:
    if verdict == "missing":
        return f"{name}: not installed"
    v = f"{name} {info['version'] or '?'}"
    if info["commit"]:
        v += f" · {info['commit'][:7]}" + (f" ({info['date']})" if info["date"] else "")
    return v + {"current": "  [green]✓ up to date[/]",
                "update": f"  [yellow]⬆ update available ({rem[:7]})[/]",
                "unknown": "  [dim]– can't check (offline, or installed without git)[/]"}[verdict]


def script(names: list[str] | None = None) -> str:
    """Shell commands: pull (or clone) each repo, then run its installer without questions."""
    parts = []
    for name in names or list(APPS):
        app, default_src, flag = APPS[name]
        if not app.is_dir():
            continue
        src = local(name).get("source") or ""
        if not src or not (Path(src) / ".git").is_dir():
            src = str(default_src)
        q = shlex.quote(src)
        parts.append(
            f"echo; echo '── {name} ──'; "
            f"if [ -d {q}/.git ]; then git -C {q} pull --ff-only "
            f"|| {{ echo '! {name}: your copy in {src} has own changes – pull skipped'; }}; "
            f"else mkdir -p {shlex.quote(str(Path(src).parent))} && git clone -q {url(name)}.git {q}; fi "
            f"&& bash {q}/install.sh {flag}")
    return "; ".join(parts) if parts else "echo 'nothing installed'"
