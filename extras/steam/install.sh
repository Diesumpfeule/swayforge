#!/usr/bin/env bash
# Installs steamtune (`steamtune`): explains Steam's big shader pre-cache downloads, sets an
# auto-update window, caps the shader cache per drive, moves it to another drive.
# A user service runs `steamtune prune` at login (before you start Steam); without limits it does nothing.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/steamtune"
BIN="$HOME/.local/bin"
UNITS="$HOME/.config/systemd/user"

python3 -m py_compile "$HERE/steamtune.py" || { echo "steamtune: syntax error – not installed."; exit 1; }
mkdir -p "$DEST" "$BIN" "$UNITS"
cp "$HERE/steamtune.py" "$DEST/steamtune.py"
cp "$HERE/uninstall.sh" "$DEST/uninstall.sh" 2>/dev/null && chmod +x "$DEST/uninstall.sh"
cat > "$BIN/steamtune" <<EOW
#!/usr/bin/env bash
exec python3 "$DEST/steamtune.py" "\$@"
EOW
chmod +x "$BIN/steamtune"

cat > "$UNITS/steamtune-prune.service" <<EOU
# swayforge generated – applies your Steam shader-cache limits at login
[Unit]
Description=steamtune: apply Steam shader cache limits

[Service]
Type=oneshot
ExecStart=$BIN/steamtune prune --quiet

[Install]
WantedBy=default.target
EOU
systemctl --user daemon-reload 2>/dev/null && systemctl --user enable steamtune-prune.service >/dev/null 2>&1

cat <<EOT
steamtune installed.
  steamtune                     what Steam downloaded and why · cache per drive
  steamtune window 03-06        auto-update only at night (Steam closed)
  steamtune limit 1 30G         cap the shader cache on library 1 (numbers from \`steamtune\`)
  steamtune prune [--dry]       apply the caps now (also done at every login)
  steamtune move 1 /mnt/x/sc    keep that library's shader cache on another drive
EOT
