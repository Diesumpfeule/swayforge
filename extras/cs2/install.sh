#!/usr/bin/env bash
# Installs cs2translate (CS2 chat translator) + a watcher that runs it while CS2 runs.
# Sway starts the watcher (exec_always) – XDG autostart entries are not used by Sway.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/cs2translate"
NAME="cs2translate.py"
BIN="$HOME/.local/bin"
ARGS_FILE="$HOME/.config/swayforge/cs2.args"

src=""
for c in "$HERE/$NAME" "$DEST/$NAME" "$HOME/Downloads/$NAME" "$HOME/$NAME"; do
  [ -f "$c" ] && { src="$c"; break; }
done
if [ -z "$src" ]; then
  echo "cs2translate: $NAME not found – skipped."
  exit 0
fi
if ! python3 -m py_compile "$src" 2>/dev/null; then
  echo "cs2translate: $src has a syntax error – not installed."
  exit 1
fi

mkdir -p "$DEST" "$BIN" "$(dirname "$ARGS_FILE")" "$HOME/.cache"
[ "$src" -ef "$DEST/$NAME" ] || cp "$src" "$DEST/$NAME"
cp "$HERE/uninstall.sh" "$DEST/uninstall.sh" 2>/dev/null && chmod +x "$DEST/uninstall.sh"

# Earlier versions (German names) – replaced by this one
pkill -f "$BIN/cs2-uebersetzer-waechter" 2>/dev/null || true
pkill -f "cs2_chat_uebersetzer.py" 2>/dev/null || true
rm -f "$BIN/cs2-uebersetzer-waechter" "$BIN/cs2-uebersetzer-start" "$BIN/cs2-uebersetzer" \
      "$HOME/.config/autostart/cs2-chat-uebersetzer.desktop" "$HOME/.config/autostart/cs2translate.desktop"
rm -rf "$HOME/.local/share/cs2-chat-uebersetzer"
if [ -f "$HOME/.config/cs2_chat_uebersetzer.json" ] && [ ! -f "$HOME/.config/cs2translate.json" ]; then
  mv "$HOME/.config/cs2_chat_uebersetzer.json" "$HOME/.config/cs2translate.json"
fi
if [ -f "$ARGS_FILE" ]; then        # old German option names → English
  sed -i -e 's/--verschieben/--move/g; s/--schrift/--font-size/g; s/--ohne-original/--no-original/g' \
         -e 's/--zeilen/--lines/g; s/--dauer/--duration/g; s/--verlauf/--history/g' \
         -e 's/--breite/--width/g; s/--fenster/--window/g; s/--alles/--debug/g' "$ARGS_FILE"
fi

# Launcher: options from cs2.args, then your own (yours win)
cat > "$BIN/cs2translate" <<EOW
#!/usr/bin/env bash
extra=\$(grep -v '^[[:space:]]*#' "$ARGS_FILE" 2>/dev/null | tr '\n' ' ')
eval "set -- \$extra \"\\\$@\""
exec python3 "$DEST/$NAME" "\$@"
EOW
chmod +x "$BIN/cs2translate"

cp "$HERE/watcher.sh" "$BIN/swayforge-cs2-watcher"
chmod +x "$BIN/swayforge-cs2-watcher"

[ -f "$ARGS_FILE" ] || cat > "$ARGS_FILE" <<'EOA'
# Options for cs2translate, used by the auto-start and by the `cs2translate` command.
# One or more per line. Paths with spaces in "quotes". Examples:
#   --font-size 14
#   --no-original
#   --alpha 0.6
#   --duration 20
#   --lang en
#   --log "/run/media/you/Games/SteamLibrary/steamapps/common/Counter-Strike Global Offensive/game/csgo/console.log"
EOA

# Start the watcher right away when we're inside Sway (otherwise: next login)
if [ -n "${SWAYSOCK:-}" ] && command -v swaymsg >/dev/null; then
  swaymsg -q exec "$BIN/swayforge-cs2-watcher" || true
fi

python3 -c "import tkinter" 2>/dev/null || echo "  Note: python3-tkinter is missing:  sudo dnf install python3-tkinter"
python3 -c "import gi; gi.require_version('GtkLayerShell', '0.1'); import cairo" 2>/dev/null || \
  echo "  For a see-through overlay on Sway:  sudo dnf install gtk-layer-shell python3-gobject python3-cairo"

cat <<EOT
cs2translate installed.
  1. Steam → CS2 → Properties → Launch options:  -condebug
     (with the gaming tip:  gamemoderun mangohud %command% -condebug)
  2. In CS2 → Video: display mode "Fullscreen windowed".
  3. Once, while CS2 runs:  cs2translate --move   (drag the overlay, Esc)
  Options: ~/.config/swayforge/cs2.args   ·   Log: ~/.cache/cs2translate.log
EOT
