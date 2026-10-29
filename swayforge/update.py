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


# Every version gets a name instead of a number: two English words picked from its commit
# (same commit → same name everywhere: Settings, the app, the update check).
_ADJ = ("amber", "arctic", "ashen", "autumn", "azure", "bold", "brisk", "bronze", "calm", "cedar", "cobalt",
        "copper", "coral", "crimson", "crystal", "dawn", "dusky", "ember", "emerald", "feral", "frosty",
        "gentle", "gilded", "golden", "granite", "hidden", "hollow", "humble", "indigo", "iron", "ivory",
        "jade", "keen", "lunar", "maple", "marble", "midnight", "misty", "mossy", "nimble", "noble", "ochre",
        "onyx", "pale", "polar", "quiet", "rapid", "rustic", "sable", "scarlet", "silent", "silver", "solar",
        "stormy", "sunny", "swift", "tidal", "velvet", "violet", "wandering", "wild", "winter", "woven", "zesty")
_NOUN = ("badger", "beacon", "birch", "bison", "breeze", "brook", "canyon", "cinder", "comet", "condor",
         "cove", "crane", "creek", "dune", "falcon", "fern", "fjord", "forge", "fox", "glacier", "grove",
         "harbor", "hawk", "heron", "hollow", "ibis", "island", "jaguar", "kestrel", "lagoon", "lantern",
         "lark", "lynx", "marten", "meadow", "mesa", "moth", "nebula", "otter", "owl", "panther", "pine",
         "prairie", "quartz", "raven", "reef", "ridge", "river", "salmon", "sparrow", "spruce", "summit",
         "thistle", "thunder", "tundra", "valley", "viper", "walrus", "willow", "wolf", "wren", "yak",
         "zephyr", "orca")


def codename(commit: str) -> str:
    """'b248872…' → 'Silver Otter'. '' when the commit is unknown."""
    c = (commit or "").strip().lower()
    try:
        n = int(c[:8], 16)
    except ValueError:
        return ""
    return f"{_ADJ[n % len(_ADJ)].title()} {_NOUN[(n // len(_ADJ)) % len(_NOUN)].title()}"


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
    v = f"{name} “{codename(info['commit'])}”" if info["commit"] else f"{name} {info['version'] or '?'}"
    if info["commit"]:
        v += f" · {info['commit'][:7]}" + (f" ({info['date']})" if info["date"] else "")
    return v + {"current": "  [green]✓ up to date[/]",
                "update": f"  [yellow]⬆ update available: “{codename(rem)}”[/]",
                "unknown": "  [dim]– can't check (offline, or installed without git)[/]"}[verdict]


DONE_MARK = paths.STATE_DIR / "update-done"


def pull_cmd(name: str, q: str) -> str:
    """Bring the source copy to the newest version, whatever happened to it locally.
    Own edits are never lost: they go into `git stash` (git -C SRC stash list / stash pop),
    a copy that drifted apart gets a backup branch before it is reset to GitHub's version."""
    stamp = "$st"
    return (
        f"st=$(date +%Y%m%d-%H%M); git -C {q} pull --ff-only -q || {{ "
        f"echo '! {name}: your copy has own changes – saving them with git stash, then updating'; "
        f"git -C {q} stash push --include-untracked -m \"before update {stamp}\" >/dev/null 2>&1; "
        f"git -C {q} pull --ff-only -q || {{ "
        f"echo \"! {name}: your copy went its own way – keeping it as branch local-backup-{stamp}\"; "
        f"git -C {q} branch \"local-backup-{stamp}\" >/dev/null 2>&1; "
        f"git -C {q} fetch -q origin && git -C {q} reset -q --hard \"origin/$(git -C {q} rev-parse --abbrev-ref HEAD)\"; }}; "
        f"git -C {q} stash list | grep -q 'before update' && "
        f"echo '  your changes: git -C {q.strip(chr(39))} stash list   (get them back: stash pop)'; }}"
    )


def script(names: list[str] | None = None) -> str:
    """Shell commands: pull (or clone) each repo, then run its installer without questions.
    Ends with exit status 0 only if every step worked."""
    parts = ["fail=0"]
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
            f"if [ -d {q}/.git ]; then {pull_cmd(name, q)}; "
            f"else mkdir -p {shlex.quote(str(Path(src).parent))} && git clone -q {url(name)}.git {q}; fi; "
            f"if bash {q}/install.sh {flag} </dev/null; then echo '✓ {name} updated'; "
            f"else echo '✗ {name}: install step failed'; fail=1; fi")
    parts.append("(exit $fail)")
    return "; ".join(parts)


def terminal_command(hold: str) -> str:
    """What the update terminal runs: on success it says so, leaves a marker (the settings app
    sees it and restarts itself with the new code) and closes; on failure it stays open."""
    mark = shlex.quote(str(DONE_MARK))
    return (f"{script()}; rc=$?; echo; "
            f"if [ $rc -eq 0 ]; then mkdir -p {shlex.quote(str(DONE_MARK.parent))}; touch {mark}; "
            f"echo '✓ All updated – the settings app restarts, this window closes.'; sleep 3; "
            f"else echo '✗ The update didn’t finish – the messages above say why.'; {hold}; fi")
