#!/usr/bin/env bash
# swayforge – entry point after a fresh Fedora Sway install.
#
#   ./install.sh                   installer with selection (TUI)
#   ./install.sh --yes             install the saved profile without questions
#   ./install.sh --restore FILE    restore a backup and install from it
#   ./install.sh --dry-run         only show what would happen
#   ./install.sh --update          copy the new version + apply, no installer (Settings → About)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/.local/share/swayforge/app"
BIN="$HOME/.local/bin/swayforge"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || fail "Please run as your normal user (not with sudo) – sudo is asked for when needed."
. /etc/os-release
[ "${ID:-}" = fedora ] || fail "swayforge is built for Fedora (found: ${PRETTY_NAME:-?})."
[ "${VERSION_ID%%.*}" -ge 41 ] 2>/dev/null || fail "Fedora 41 or newer is required."

RESTORE=""
UPDATE=0
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --restore) RESTORE="${2:?file missing}"; shift 2 ;;
    --update) UPDATE=1; shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

bold "swayforge – admin rights are requested once:"
sudo -v

bold "Packages swayforge itself needs …"
sudo dnf install -y --skip-unavailable python3 python3-textual python3-jinja2 python3-pillow git >/dev/null
# swayforge app's own window (optional: without it, it opens in a browser window)
sudo dnf install -y --skip-unavailable python3-gobject gtk4 webkitgtk6.0 >/dev/null 2>&1 || true

bold "Copying swayforge to $APP …"
mkdir -p "$APP" "$(dirname "$BIN")"
if [ "$HERE" != "$APP" ]; then
  # copy next to the installed version, check it, then swap – a failed copy never leaves a broken app
  rm -rf "$APP/swayforge.new" "$APP/swayforge.old"
  cp -r "$HERE/swayforge" "$APP/swayforge.new" || fail "Copying failed – the installed version is unchanged."
  python3 -m compileall -q "$APP/swayforge.new" >/dev/null || { rm -rf "$APP/swayforge.new"; fail "The new version has a syntax error – the installed version is unchanged."; }
  [ -d "$APP/swayforge" ] && mv "$APP/swayforge" "$APP/swayforge.old"
  mv "$APP/swayforge.new" "$APP/swayforge"
  rm -rf "$APP/swayforge.old"
  mkdir -p "$APP/extras"
  cp -r "$HERE/extras/." "$APP/extras/" 2>/dev/null || true
  cp "$HERE/install.sh" "$HERE/README.md" "$APP/" 2>/dev/null || true
  cp -r "$HERE/docs" "$APP/" 2>/dev/null || true
fi
# which version is installed (shown in Settings → About, used for the update check)
printf '{"commit": "%s", "date": "%s", "source": "%s"}\n' \
  "$(git -C "$HERE" rev-parse HEAD 2>/dev/null || true)" \
  "$(git -C "$HERE" log -1 --format=%cs 2>/dev/null || true)" "$HERE" > "$APP/build.json"
cat > "$BIN" <<EOF
#!/bin/sh
export PYTHONPATH="$APP\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m swayforge "\$@"
EOF
chmod +x "$BIN"
export PATH="$HOME/.local/bin:$PATH"

# keep the CS2 translator in step with swayforge (it lives in its own folder)
if [ -d "$HOME/.local/share/cs2translate" ]; then
  bold "Updating the CS2 translator …"
  sudo dnf install -y --skip-unavailable gtk-layer-shell python3-gobject python3-cairo >/dev/null 2>&1 || true
  bash "$APP/extras/cs2/install.sh" >/dev/null 2>&1 || true
fi

if [ "$UPDATE" = 1 ]; then
  bold "Applying the new version …"
  "$BIN" apply
  bold "✓ swayforge updated. Restart the settings app (Super+I) to see the new version."
  exit 0
fi

if [ -n "$RESTORE" ]; then
  bold "Restoring backup: $RESTORE"
  "$BIN" restore "$RESTORE"
  ARGS+=("--yes")
fi

# keep sudo fresh while the installer runs
( while true; do sudo -n -v 2>/dev/null; sleep 50; done ) &
KEEP=$!
trap 'kill $KEEP 2>/dev/null || true' EXIT

"$BIN" install "${ARGS[@]}"
