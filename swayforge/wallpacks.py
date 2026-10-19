"""Optional wallpaper collections: choose folders, they are downloaded straight into the Wallpapers folder.

The pictures are not part of swayforge. The download runs on your computer (git sparse checkout of the
original repository – only the chosen folders, no history), the images land in
~/Pictures/Wallpapers/<collection>/<folder>/ and the temporary clone is removed afterwards.
"""
from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

DATA = Path(__file__).parent / "data" / "wallpapers.toml"
IMG_EXT = ("png", "jpg", "jpeg", "webp")
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SEP = "/"
STARTER = ["dharmx/abstract", "dharmx/minimal", "dharmx/mountain", "dharmx/gruvbox"]   # a small, varied first set


@dataclass(frozen=True)
class Category:
    id: str
    files: int
    mb: int


@dataclass(eq=False)
class Pack:
    id: str
    name: str
    repo: str
    branch: str
    subdir: str
    license: str
    blurb: str
    categories: list[Category] = field(default_factory=list)

    def cat(self, cid: str) -> Category | None:
        return next((c for c in self.categories if c.id == cid), None)

    @property
    def total_mb(self) -> int:
        return sum(c.mb for c in self.categories)

    @property
    def total_files(self) -> int:
        return sum(c.files for c in self.categories)


def load() -> list[Pack]:
    d = tomllib.loads(DATA.read_text())
    out = []
    for p in d["pack"]:
        out.append(Pack(p["id"], p["name"], p["repo"], p.get("branch", "main"), p.get("subdir", ""),
                        p.get("license", ""), p.get("blurb", ""),
                        [Category(c["id"], c["files"], c["mb"]) for c in p.get("category", [])]))
    return out


def get(pid: str) -> Pack | None:
    return next((p for p in load() if p.id == pid), None)


def key(pack: str, cat: str) -> str:
    return f"{pack}{SEP}{cat}"


def split_key(k: str) -> tuple[str, str]:
    p, _, c = k.partition(SEP)
    return p, c


def resolve(keys) -> dict[Pack, list[Category]]:
    """'pack/cat' keys → {pack: [categories]}; unknown or malformed keys are dropped."""
    packs = {p.id: p for p in load()}
    out: dict[Pack, list[Category]] = {}
    for k in sorted(keys):
        pid, cid = split_key(k)
        p = packs.get(pid)
        c = p.cat(cid) if p else None
        if p and c and ID_RE.match(pid) and ID_RE.match(cid):
            out.setdefault(p, []).append(c)
    return out


def total_mb(keys) -> int:
    return sum(c.mb for cs in resolve(keys).values() for c in cs)


def target_dir(pack: Pack, cat: Category, root: Path | None = None) -> Path:
    root = root or paths.WALLPAPER_DIR
    return root / pack.id if pack.subdir else root / pack.id / cat.id


def installed_count(pack: Pack, cat: Category, root: Path | None = None) -> int:
    d = target_dir(pack, cat, root)
    if not d.is_dir():
        return 0
    return sum(1 for f in d.iterdir() if f.suffix.lower().lstrip(".") in IMG_EXT)


def is_installed(pack: Pack, cat: Category, root: Path | None = None) -> bool:
    return installed_count(pack, cat, root) > 0


def script(keys, root: Path | None = None) -> str:
    """One bash script that downloads everything in `keys` (ONE string: the installer runs each
    command with its own `bash -c`). Prints progress lines; leaves nothing behind but the images."""
    root = root or paths.WALLPAPER_DIR
    chosen = resolve(keys)
    if not chosen:
        return "echo 'No wallpaper folders selected.'"
    q = shlex.quote
    ext_find = " -o ".join(f"-iname '*.{e}'" for e in IMG_EXT)
    lines = ["set -e",
             'command -v git >/dev/null || { echo "git is missing (sudo dnf install git)"; exit 1; }',
             'CACHE="${XDG_CACHE_HOME:-$HOME/.cache}"; mkdir -p "$CACHE"',
             'TMP=$(mktemp -d "$CACHE/swayforge-walls.XXXXXX")',
             'trap \'rm -rf "$TMP"\' EXIT',
             f"mkdir -p {q(str(root))}"]
    for n, (p, cats) in enumerate(chosen.items()):
        sub = p.subdir.strip("/")
        want = [(f"{sub}/{c.id}" if sub and c.id != "all" else (sub or c.id)) for c in cats]
        if sub and any(c.id == "all" for c in cats):
            want = [sub]
        mb = sum(c.mb for c in cats)
        lines += [
            f"echo '==> {p.name}: {len(cats)} folder(s), about {mb} MB'",
            f"git clone --quiet --depth 1 --filter=blob:none --sparse --branch {q(p.branch)} "
            f"{q(p.repo)} \"$TMP/{n}\"",
            f"git -C \"$TMP/{n}\" sparse-checkout set {' '.join(q(w) for w in want)}",
        ]
        for c in cats:
            src = f"{sub}/{c.id}" if sub and c.id != "all" else (sub or c.id)
            dst = target_dir(p, c, root)
            lines += [
                f"echo '    {c.id} …'",
                f"mkdir -p {q(str(dst))}",
                f"find \"$TMP/{n}/{src}\" -maxdepth 1 -type f \\( {ext_find} \\) -print0 "
                f"| xargs -0 -r -I{{}} mv -n {{}} {q(str(dst))}/",
            ]
        lines.append(f"rm -rf \"$TMP/{n}\"")
    lines.append("echo 'Done – the pictures are in " + str(root).replace("'", "") + "'")
    return "\n".join(lines)
