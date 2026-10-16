#!/usr/bin/env bash
# Installs the CS2 chat translator + a watcher that runs it while CS2 runs.
# Replaces the tool's own installieren.sh (that one uses ~/.config/autostart, which Sway ignores).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/cs2-chat-uebersetzer"
NAME="cs2_chat_uebersetzer.py"
BIN="$HOME/.local/bin"
ARGS_FILE="$HOME/.config/swayforge/cs2.args"

src=""
for c in "$HERE/$NAME" "$DEST/$NAME" "$HOME/Downloads/$NAME" "$HOME/$NAME"; do
  [ -f "$c" ] && { src="$c"; break; }
done
if [ -z "$src" ]; then
  echo "CS2 chat translator: $NAME not found – skipped."
  exit 0
fi
if ! python3 -m py_compile "$src" 2>/dev/null; then
  echo "CS2 chat translator: $src has a syntax error – not installed."
  exit 1
fi

mkdir -p "$DEST" "$BIN" "$(dirname "$ARGS_FILE")" "$HOME/.cache"
[ "$src" -ef "$DEST/$NAME" ] || cp "$src" "$DEST/$NAME"
cp "$HERE/uninstall.sh" "$DEST/uninstall.sh" 2>/dev/null && chmod +x "$DEST/uninstall.sh"

# Old setup from the tool's own installer: GNOME-style autostart + watcher (replaced by ours)
pkill -f "$BIN/cs2-uebersetzer-waechter" 2>/dev/null || true
rm -f "$BIN/cs2-uebersetzer-waechter" "$BIN/cs2-uebersetzer-start" \
      "$HOME/.config/autostart/cs2-chat-uebersetzer.desktop"

# Launcher: options from cs2.args, then your own (yours win)
cat > "$BIN/cs2-uebersetzer" <<EOW
#!/usr/bin/env bash
extra=\$(grep -v '^[[:space:]]*#' "$ARGS_FILE" 2>/dev/null | tr '\n' ' ')
eval "set -- \$extra \"\\\$@\""
exec python3 "$DEST/$NAME" "\$@"
EOW
chmod +x "$BIN/cs2-uebersetzer"

cp "$HERE/watcher.sh" "$BIN/swayforge-cs2-watcher"
chmod +x "$BIN/swayforge-cs2-watcher"

[ -f "$ARGS_FILE" ] || cat > "$ARGS_FILE" <<'EOA'
# Options for the CS2 chat translator, used by the auto-start and by `cs2-uebersetzer`.
# One or more per line. Paths with spaces in "quotes". Examples:
#   --schrift 14
#   --ohne-original
#   --alpha 0.6
#   --dauer 20
#   --log "/run/media/you/Games/SteamLibrary/steamapps/common/Counter-Strike Global Offensive/game/csgo/console.log"
EOA

# Start the watcher right away when we're inside Sway (otherwise: next login)
if [ -n "${SWAYSOCK:-}" ] && command -v swaymsg >/dev/null; then
  swaymsg -q exec "$BIN/swayforge-cs2-watcher" || true
fi

python3 -c "import tkinter" 2>/dev/null || echo "  Note: python3-tkinter is missing:  sudo dnf install python3-tkinter"

cat <<EOT
CS2 chat translator installed.
  1. Steam → CS2 → Properties → Launch options:  -condebug
     (with the gaming tip:  gamemoderun mangohud %command% -condebug)
  2. In CS2 → Video: display mode "Fullscreen windowed".
  3. Once, while CS2 runs:  cs2-uebersetzer --verschieben   (drag the overlay, Esc)
  Options: ~/.config/swayforge/cs2.args   ·   Log: ~/.cache/cs2_chat_uebersetzer.log
EOT
