#!/usr/bin/env bash
# swayforge – entry point after a fresh Fedora Sway install.
#
#   ./install.sh                   installer with selection (TUI)
#   ./install.sh --yes             install the saved profile without questions
#   ./install.sh --restore FILE    restore a backup and install from it
#   ./install.sh --dry-run         only show what would happen
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
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --restore) RESTORE="${2:?file missing}"; shift 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

bold "swayforge – admin rights are requested once:"
sudo -v

bold "Packages swayforge itself needs …"
sudo dnf install -y --skip-unavailable python3 python3-textual python3-jinja2 git >/dev/null

bold "Copying swayforge to $APP …"
mkdir -p "$APP" "$(dirname "$BIN")"
if [ "$HERE" != "$APP" ]; then
  rm -rf "$APP/swayforge"
  cp -r "$HERE/swayforge" "$APP/"
  mkdir -p "$APP/extras"
  cp -r "$HERE/extras/." "$APP/extras/" 2>/dev/null || true
  cp "$HERE/install.sh" "$HERE/README.md" "$APP/" 2>/dev/null || true
  cp -r "$HERE/docs" "$APP/" 2>/dev/null || true
fi
cat > "$BIN" <<EOF
#!/bin/sh
export PYTHONPATH="$APP\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m swayforge "\$@"
EOF
chmod +x "$BIN"
export PATH="$HOME/.local/bin:$PATH"

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
