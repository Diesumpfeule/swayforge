"""All paths in one place."""
from __future__ import annotations

import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
DATA = PKG / "data"
TEMPLATES = PKG / "templates"

HOME = Path.home()
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")

CONFIG_DIR = XDG_CONFIG / "swayforge"          # settings.toml, profile.toml, your themes
SETTINGS_FILE = CONFIG_DIR / "settings.toml"
PROFILE_FILE = CONFIG_DIR / "profile.toml"
USER_THEMES = CONFIG_DIR / "themes"
USER_CATALOG = CONFIG_DIR / "catalog.toml"

STATE_DIR = XDG_DATA / "swayforge"             # generated files, backups, Spaceship
GEN_DIR = STATE_DIR / "generated"
BACKUP_DIR = STATE_DIR / "backups"
SPACESHIP_DIR = STATE_DIR / "spaceship"
LOG_FILE = STATE_DIR / "install.log"

SWAY_CUSTOM = XDG_CONFIG / "sway" / "custom.conf"   # yours – never overwritten


def _pictures_dir() -> Path:
    """~/Pictures – or its localized name from user-dirs.dirs (e.g. ~/Bilder)."""
    try:
        for line in (XDG_CONFIG / "user-dirs.dirs").read_text().splitlines():
            if line.startswith("XDG_PICTURES_DIR="):
                return Path(line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(HOME)))
    except OSError:
        pass
    return HOME / "Pictures"


WALLPAPER_DIR = _pictures_dir() / "Wallpapers"     # drop your images here
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".gif", ".m4v")      # animated wallpapers (see livewall.py)
WALLPAPER_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg") + VIDEO_EXT


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, USER_THEMES, STATE_DIR, GEN_DIR, BACKUP_DIR, WALLPAPER_DIR):
        d.mkdir(parents=True, exist_ok=True)
