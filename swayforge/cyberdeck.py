"""Cyberdeck mode: swayforge for small screens and small computers (Raspberry Pi & co.).

Off by default. When it's on, the configs are generated from a *copy* of your settings with a
few values changed – your own settings stay untouched, so switching it off brings everything back:
- compact:   slim bar (24 px), smaller text, tiny gaps, thin borders, only the important bar modules,
- low power: no blur, shadows, dimming or animations, no desktop widgets (easy on a Pi's GPU),
- touch:     the Touch layout with big tap targets (for touch screens),
- scale:     one display scale for every screen (e.g. 1.5 on a tiny high-resolution panel).
"""
from __future__ import annotations

import copy

SCALES = [("Keep", 0), ("1.0", 1.0), ("1.25", 1.25), ("1.5", 1.5), ("1.75", 1.75), ("2.0", 2.0)]


def effective(s: dict) -> dict:
    """The settings the configs are made from (= yours, unless cyberdeck mode is on)."""
    cd = s.get("cyberdeck") or {}
    if not cd.get("enabled"):
        return s
    e = copy.deepcopy(s)
    if cd.get("compact", True):
        e["bar"]["height"] = min(e["bar"]["height"], 24)
        e["theme"]["font_size"] = max(8, int(e["theme"]["font_size"]) - 2)
        e["look"].update(gaps_inner=min(2, e["look"]["gaps_inner"]), gaps_outer=0,
                         border=min(1, e["look"]["border"]) if e["look"]["border"] else 0,
                         terminal_padding=min(4, e["look"]["terminal_padding"]))
        for k in ("window_title", "cpu", "memory", "temperature", "gpu", "taskmanager", "gamemode", "media"):
            e["bar"][k] = False
        e["bar"]["battery"] = True
        e["widgets"]["scale"] = min(0.8, float(e["widgets"].get("scale", 1.0)))
    if cd.get("low_power", True):
        e["look"].update(fx_blur=False, fx_shadows=False, fx_dim_inactive=0.0)
        e["theme"]["animate"] = False
        e["widgets"]["enabled"] = False
    if cd.get("touch", False):
        e["bar"]["layout"] = "touch"
    return e


def scale(s: dict) -> float:
    cd = s.get("cyberdeck") or {}
    try:
        return float(cd.get("scale", 0) or 0) if cd.get("enabled") else 0.0
    except (TypeError, ValueError):
        return 0.0
