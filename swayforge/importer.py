"""Feed in an existing Sway config: keep its behaviour, the look stays with the theme."""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import paths, render, settings

# Lines swayforge manages itself (look, bar, services) – commented out.
MANAGED = [
    r"^font\s", r"^client\.", r"^gaps\s", r"^smart_gaps", r"^smart_borders", r"^default_border",
    r"^default_floating_border", r"^hide_edge_borders", r"^titlebar_", r"^title_align",
    r"^output\s+\S+\s+(bg|background)\s", r"^seat\s+\S+\s+xcursor_theme",
    r"^include\s+/etc/sway", r"^exec(_always)?\s+.*\b(swaybg|waybar|mako|dunst|swayidle|swaync)\b",
    r"^exec(_always)?\s+.*\b(nm-applet|blueman-applet|lxqt-policykit|cliphist)\b",
    r"^exec(_always)?\s+.*\b(import-environment|dbus-update-activation-environment)\b",
    r"^bar\s",
    r"^(corner_radius|shadows|shadow_|blur|layer_effects|default_dim_inactive)",
]
_MANAGED = [re.compile(p) for p in MANAGED]


def transform(text: str) -> tuple[str, int, int]:
    """Returns (new text, lines kept, lines commented out)."""
    out, kept, dropped = [], 0, 0
    depth_skip = 0   # >0 while inside a bar { … } block
    for raw in text.splitlines():
        line = raw.strip()
        if depth_skip:
            depth_skip += line.count("{") - line.count("}")
            out.append("# [swayforge] " + raw)
            dropped += 1
            continue
        if re.match(r"^bar\s*(\S+\s*)?\{", line) or line == "bar {":
            depth_skip = line.count("{") - line.count("}")
            out.append("# [swayforge: Waybar provides the bar] " + raw)
            dropped += 1
            continue
        if line and not line.startswith("#") and any(p.search(line) for p in _MANAGED):
            out.append("# [swayforge: managed by the theme] " + raw)
            dropped += 1
            continue
        out.append(raw)
        if line and not line.startswith("#"):
            kept += 1
    return "\n".join(out) + "\n", kept, dropped


def import_sway_config(src: Path) -> str:
    if not src.is_file():
        raise ValueError(f"File not found: {src}")
    text = src.read_text(errors="replace")
    new, kept, dropped = transform(text)
    header = (f"# Imported from {src} on {time.strftime('%Y-%m-%d %H:%M')} by swayforge.\n"
              "# Lines marked [swayforge] are commented out because the theme manages them.\n"
              "# You can re-enable them – this file always wins.\n\n")
    custom = paths.SWAY_CUSTOM
    old = custom.read_text() if custom.exists() else None
    if old is not None:
        bdir = paths.BACKUP_DIR / time.strftime("%Y%m%d-%H%M%S-custom")
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "custom.conf").write_text(old)
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text(header + new)

    # Validate the whole config, roll back on error
    ctx = render.make_ctx(settings.load())
    w = render.Writer(dry=True)
    render.wallpaper(ctx, w)
    err = render.validate_sway(render.tpl("sway.conf.j2", ctx.as_dict()))
    if err:
        if old is not None:
            custom.write_text(old)
        else:
            custom.unlink()
        raise ValueError("Import cancelled – Sway reports errors:\n" + err)
    return f"Imported: {kept} lines kept, {dropped} managed by the theme (commented out)."
