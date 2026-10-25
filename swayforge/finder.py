"""Find an app by name and show the exact install command – following the repo hierarchy:

    1. Fedora            (your enabled repos: `dnf`)
    2. COPR              (community builds, searched online)
    3. RPM Fusion        (free + nonfree, searched online even if not enabled yet)
    4. Flathub           (Flatpak, searched online – only when nothing above has it)

Only structured sources are queried (dnf, the COPR API, the Flathub API) – never a random web
page – and every name that comes back is checked against a strict pattern before it can end up
in a shell command. Nothing is installed here: the command is run in a terminal by the settings
app, where dnf/flatpak ask once more.
"""
from __future__ import annotations

import json
import platform
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .system import have

SOURCES = ["Fedora", "COPR", "RPM Fusion", "Flathub"]
TIER = {name: i for i, name in enumerate(SOURCES)}
UA = {"User-Agent": "swayforge-finder", "Accept": "application/json"}

PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")                 # rpm package name
COPR_RE = re.compile(r"^(@?[A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)$")  # owner/project, @group/project
FLATPAK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+){1,}$")  # com.example.App


@dataclass
class Hit:
    name: str                     # what to show
    source: str                   # Fedora | COPR | RPM Fusion | Flathub | "<repo> (extra repo)"
    summary: str
    cmd: str                      # the exact shell command that installs it
    ident: str = ""               # package name / owner/project / Flatpak app id
    tier: int = 0
    rank: int = 3                 # 0 exact name · 1 starts with · 2 contains · 3 only in the description
    note: str = ""
    installed: bool = False

    @property
    def key(self) -> tuple:
        return (self.tier, self.rank, self.name.lower())


@dataclass
class Result:
    hits: list[Hit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)   # source → why it gave nothing


# ── helpers ──────────────────────────────────────────────────────────
def _try(cmd: list[str], timeout: int = 60) -> str | None:
    """Output of the command, or None if it failed (≠ empty output = nothing found)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _run(cmd: list[str], timeout: int = 60) -> str:
    return _try(cmd, timeout) or ""


def _http_json(url: str, body: dict | None = None, timeout: int = 12) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(UA)
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def rank_of(term: str, name: str) -> int:
    t, n = term.lower().strip(), name.lower()
    if n == t or n.replace("-", " ") == t:
        return 0
    if n.startswith(t):
        return 1
    return 2 if t in n else 3


def one_line(text: str, width: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[:width - 1] + "…"


def fedora_release() -> int:
    from .system import os_release
    try:
        return int(os_release().get("VERSION_ID", "0"))
    except ValueError:
        return 0


def arch() -> str:
    return platform.machine() or "x86_64"


def classify_repo(repoid: str) -> tuple[str, int]:
    """Repo id → (label, tier). dnf says which repo a package comes from."""
    r = repoid.lower()
    if r.startswith("copr:") or r.startswith("copr_"):
        return "COPR", TIER["COPR"]
    if r.startswith("rpmfusion"):
        return "RPM Fusion", TIER["RPM Fusion"]
    if r.startswith(("fedora", "updates")) or r == "@system":
        return "Fedora", TIER["Fedora"]
    return f"{repoid} (extra repo)", TIER["RPM Fusion"]      # a vendor's own RPM repo ranks with RPM Fusion


# ── install commands ─────────────────────────────────────────────────
def dnf_cmd(pkg: str) -> str:
    return f"sudo dnf install {shlex.quote(pkg)}"


def copr_cmd(full_name: str, project: str) -> str:
    """Enable the COPR, list what it contains and let you pick (project names ≠ package names)."""
    owner = full_name.split("/")[0]
    repo = f"copr:copr.fedorainfracloud.org:{'group_' + owner[1:] if owner.startswith('@') else owner}:{project}"
    default = shlex.quote(project)
    return (f"sudo dnf copr enable -y {shlex.quote(full_name)} && "
            f"{{ echo; echo 'Packages in this COPR:'; "
            f"dnf repoquery -q --available --repo {shlex.quote(repo)} --qf '  %{{name}}  –  %{{summary}}' | sort -u; "
            f"echo; read -rp 'Package to install [{project}]: ' p; "
            f"sudo dnf install \"${{p:-{default}}}\"; }}")


def rpmfusion_setup(release: int, free: bool = True, nonfree: bool = True) -> str:
    rel = str(release) if release else "$(rpm -E %fedora)"
    urls = [f"https://mirrors.rpmfusion.org/{k}/fedora/rpmfusion-{k}-release-{rel}.noarch.rpm"
            for k, on in (("free", free), ("nonfree", nonfree)) if on]
    return "sudo dnf install " + " ".join(urls) if urls else ""


def rpmfusion_cmd(pkg: str, release: int, free: bool, nonfree: bool) -> str:
    setup = rpmfusion_setup(release, free, nonfree)
    return (f"{setup} && " if setup else "") + dnf_cmd(pkg)


def flathub_cmd(app_id: str) -> str:
    pre = []
    if not have("flatpak"):
        pre.append("sudo dnf install -y flatpak")
    if not have("flatpak") or "flathub" not in _run(["flatpak", "remotes"]):
        pre.append("sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo")
    return " && ".join(pre + [f"sudo flatpak install flathub {shlex.quote(app_id)}"])


# ── 1. Fedora and everything already enabled ─────────────────────────
_SEARCH_LINE = re.compile(r"^\s*([A-Za-z0-9][\w.+-]*?)\.(?:x86_64|noarch|aarch64|i686|ppc64le|s390x)\b\s*:?\s*(.*)$")


def candidate_names(term: str, limit: int = 40) -> list[str]:
    """Package names that match: by name (repoquery) and by description (dnf search)."""
    names: list[str] = []
    glob = "*" + "*".join(term.split()) + "*"
    for line in _run(["dnf", "repoquery", "-q", "--available", "--qf", "%{name}\n", glob], 90).splitlines():
        n = line.strip()
        if PKG_RE.match(n) and n not in names:
            names.append(n)
    for line in _run(["dnf", "search", "-q", term], 90).splitlines():
        m = _SEARCH_LINE.match(line)
        if m and PKG_RE.match(m.group(1)) and m.group(1) not in names:
            names.append(m.group(1))
    names.sort(key=lambda n: rank_of(term, n))
    return names[:limit]


def search_enabled(term: str, limit: int = 20) -> list[Hit]:
    if not have("dnf"):
        raise RuntimeError("dnf not found")
    names = candidate_names(term, limit * 2)
    if not names:
        return []
    raw = _run(["dnf", "repoquery", "-q", "--available", "--qf", "%{name}\t%{repoid}\t%{summary}\n", *names], 90)
    best: dict[str, Hit] = {}
    for line in raw.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3 or not PKG_RE.match(parts[0]):
            continue
        name, repoid, summary = parts
        label, tier = classify_repo(repoid)
        h = Hit(name, label, one_line(summary), dnf_cmd(name), name, tier, rank_of(term, name))
        if name not in best or h.tier < best[name].tier:
            best[name] = h
    return sorted(best.values(), key=lambda h: h.key)[:limit]


# ── 2. COPR ──────────────────────────────────────────────────────────
def parse_copr(data: dict, term: str, release: int, arch_: str, limit: int = 12) -> list[Hit]:
    out: list[Hit] = []
    for it in data.get("items") or []:
        full = str(it.get("full_name") or "")
        m = COPR_RE.match(full)
        if not m:
            continue
        chroots = list((it.get("chroot_repos") or {}).keys()) or list(it.get("chroots") or [])
        if chroots and not any(c.startswith((f"fedora-{release}-{arch_}", "fedora-rawhide-")) for c in chroots):
            continue                                  # no build for your Fedora version
        proj = m.group(2)
        out.append(Hit(proj, "COPR", one_line(it.get("description") or it.get("instructions") or ""),
                       copr_cmd(full, proj), full, TIER["COPR"], rank_of(term, proj),
                       note="community build – not reviewed by Fedora"))
    out.sort(key=lambda h: h.key)
    return out[:limit]


def search_copr(term: str, limit: int = 12) -> list[Hit]:
    from urllib.parse import quote
    data = _http_json(f"https://copr.fedorainfracloud.org/api_3/project/search?query={quote(term)}&limit=60")
    return parse_copr(data, term, fedora_release(), arch(), limit)


# ── 3. RPM Fusion (also when it isn't enabled yet) ───────────────────
def rpmfusion_enabled() -> tuple[bool, bool]:
    d = Path("/etc/yum.repos.d")
    return (any(d.glob("rpmfusion-free.repo")) or any(d.glob("rpmfusion-free-*.repo")),
            any(d.glob("rpmfusion-nonfree.repo")) or any(d.glob("rpmfusion-nonfree-*.repo")))


def search_rpmfusion(term: str, limit: int = 12) -> list[Hit]:
    """Packages of the RPM Fusion repos that are NOT enabled yet (enabled ones show up under Fedora)."""
    have_free, have_nonfree = rpmfusion_enabled()
    if have_free and have_nonfree:
        return []
    if not have("dnf"):
        raise RuntimeError("dnf not found")
    rel = fedora_release()
    if not rel:
        raise RuntimeError("not Fedora")
    glob = "*" + "*".join(term.split()) + "*"
    out: dict[str, Hit] = {}
    failed = asked = 0
    for kind, enabled in (("free", have_free), ("nonfree", have_nonfree)):
        if enabled:
            continue
        asked += 1
        rid = f"swayforge-rpmfusion-{kind}"
        base = f"https://download1.rpmfusion.org/{kind}/fedora/releases/{rel}/Everything/{arch()}/os/"
        raw = _try(["dnf", "repoquery", "-q", "--available", f"--repofrompath={rid},{base}", "--repo", rid,
                    "--nogpgcheck", "--qf", "%{name}\t%{summary}\n", glob], 120)
        if raw is None:
            failed += 1
            continue
        for line in raw.splitlines():
            name, _, summary = line.partition("\t")
            if PKG_RE.match(name) and name not in out:
                out[name] = Hit(name, "RPM Fusion", one_line(summary),
                                rpmfusion_cmd(name, rel, not have_free, not have_nonfree), name,
                                TIER["RPM Fusion"], rank_of(term, name),
                                note=f"{kind}: enables the RPM Fusion repos first")
    if asked and failed == asked:
        raise RuntimeError("RPM Fusion didn't answer (offline?)")
    return sorted(out.values(), key=lambda h: h.key)[:limit]


# ── 4. Flathub ───────────────────────────────────────────────────────
def parse_flathub(data: dict, term: str, limit: int = 12) -> list[Hit]:
    out: list[Hit] = []
    for h in data.get("hits") or []:
        app_id = str(h.get("app_id") or h.get("id") or "")
        if app_id.startswith("flathub:"):
            app_id = app_id.split(":", 1)[1]
        if not FLATPAK_RE.match(app_id):
            continue
        name = str(h.get("name") or app_id)
        out.append(Hit(name, "Flathub", one_line(h.get("summary") or h.get("description") or ""),
                       flathub_cmd(app_id), app_id, TIER["Flathub"], rank_of(term, name),
                       note=app_id))
    return out[:limit]


def search_flathub(term: str, limit: int = 12) -> list[Hit]:
    try:
        return parse_flathub(_http_json("https://flathub.org/api/v2/search", {"query": term}), term, limit)
    except (urllib.error.URLError, OSError, ValueError):
        if not have("flatpak"):
            raise
    # offline fallback: whatever your configured Flatpak remotes know
    out: list[Hit] = []
    for line in _run(["flatpak", "search", "--columns=application,name,description", term], 40).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and FLATPAK_RE.match(parts[0].strip()):
            out.append(Hit(parts[1].strip() or parts[0], "Flathub", one_line(parts[2] if len(parts) > 2 else ""),
                           flathub_cmd(parts[0].strip()), parts[0].strip(), TIER["Flathub"],
                           rank_of(term, parts[1]), note=parts[0].strip()))
    return out[:limit]


# ── all together ─────────────────────────────────────────────────────
STEPS: list[tuple[str, str, Callable[[str], list[Hit]]]] = [
    ("Fedora", "Fedora & enabled repos", search_enabled),
    ("COPR", "COPR", search_copr),
    ("RPM Fusion", "RPM Fusion", search_rpmfusion),
    ("Flathub", "Flathub", search_flathub),
]


def mark_installed(hits: list[Hit], rpms: set[str], flatpaks: set[str]) -> None:
    for h in hits:
        h.installed = h.ident in (flatpaks if h.source == "Flathub" else rpms)


def search_all(term: str, on_done: Callable[[str, list[Hit], str], None] | None = None) -> Result:
    """Ask all four sources in parallel. on_done(source, hits, error) fires as each one answers."""
    term = " ".join(term.split())
    res = Result()
    if len(term) < 2:
        return res

    def one(step):
        key, _label, fn = step
        try:
            hits, err = fn(term), ""
        except Exception as e:
            hits, err = [], f"{e.__class__.__name__}: {e}"[:160]
        if on_done:
            on_done(key, hits, err)
        return key, hits, err

    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, hits, err in pool.map(one, STEPS):
            res.hits += hits
            if err:
                res.errors[key] = err
    # the same package from several repos: keep the one from the highest tier
    seen: dict[tuple[str, str], Hit] = {}
    for h in sorted(res.hits, key=lambda h: h.key):
        seen.setdefault((h.source, h.ident), h)
    res.hits = sorted(seen.values(), key=lambda h: h.key)
    return res


def describe(res: Result) -> str:
    """Plain-text listing for the command line."""
    lines: list[str] = []
    last = None
    for h in res.hits:
        if h.source != last:
            lines.append(f"\n── {h.source} " + "─" * max(0, 60 - len(h.source)))
            last = h.source
        lines.append(f"  {h.name}{'  [installed]' if h.installed else ''}  –  {h.summary}")
        lines.append(f"      {h.cmd}")
        if h.note and h.source not in ("Flathub",):
            lines.append(f"      ({h.note})")
    for src, err in res.errors.items():
        lines.append(f"\n! {src}: {err}")
    if not res.hits and not res.errors:
        lines.append("Nothing found.")
    return "\n".join(lines).lstrip("\n")
