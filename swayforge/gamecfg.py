"""CS2 translator + Steam helper settings, shared by the terminal app and swayforge app."""
from __future__ import annotations

import importlib.util
import re
import shlex

from . import paths

CS2_DIR = paths.XDG_DATA / "cs2translate"
CS2_ARGS = paths.CONFIG_DIR / "cs2.args"
STEAMTUNE = paths.XDG_DATA / "steamtune" / "steamtune.py"
STEAMTUNE_BIN = paths.HOME / ".local/bin/steamtune"
CS2_BIN = paths.HOME / ".local/bin/cs2translate"
BLOCK_START, BLOCK_END = "# --- swayforge settings (Settings → Games) ---", "# --- end swayforge settings ---"

# option → (label, default, hint)
CS2_FIELDS = {
    "font-size": ("Font size", "12", "points"),
    "alpha": ("Background opacity", "0.7", "0.2 – 1.0"),
    "duration": ("Seconds a message stays", "15", ""),
    "lines": ("Messages shown at once", "6", ""),
    "lang": ("Translate into", "de", "language code, e.g. de, en, fr"),
}


def cs2_values() -> dict[str, str]:
    """Current values: defaults, overridden by the managed block of cs2.args."""
    vals = {k: v[1] for k, v in CS2_FIELDS.items()}
    vals["no-original"] = ""
    try:
        txt = CS2_ARGS.read_text()
    except OSError:
        return vals
    m = re.search(re.escape(BLOCK_START) + r"(.*?)" + re.escape(BLOCK_END), txt, re.S)
    for line in (m.group(1).splitlines() if m else []):
        parts = line.split()
        if parts and parts[0].startswith("--"):
            vals[parts[0][2:]] = parts[1] if len(parts) > 1 else "1"
    return vals


def cs2_save(vals: dict[str, str], hide_original: bool) -> None:
    lines = [f"--{k} {shlex.quote(v)}" for k, v in vals.items() if v]
    if hide_original:
        lines.append("--no-original")
    block = BLOCK_START + "\n" + "\n".join(lines) + "\n" + BLOCK_END
    try:
        txt = CS2_ARGS.read_text()
    except OSError:
        txt = ""
    if BLOCK_START in txt:
        txt = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), lambda _m: block, txt, flags=re.S)
    else:
        txt = txt.rstrip("\n") + ("\n\n" if txt.strip() else "") + block + "\n"
    CS2_ARGS.parent.mkdir(parents=True, exist_ok=True)
    CS2_ARGS.write_text(txt)


def steamtune_module():
    spec = importlib.util.spec_from_file_location("steamtune", STEAMTUNE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)           # type: ignore[union-attr]
    return mod
